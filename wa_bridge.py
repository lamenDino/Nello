#!/usr/bin/env python3
"""Bridge HTTP interno tra il worker WhatsApp (Node/Baileys) e il motore Python.

Il worker Node gestisce la connessione WhatsApp; quando arriva un link chiama
questo bridge per scaricarlo col downloader esistente (riuso di tutti i fallback
TikTok/IG/FB/cookie) e per registrare punti/voti sullo stesso Firestore. La
sessione WhatsApp viene persistita qui (su Firestore) così non serve riscansionare
il QR a ogni deploy.

Gira su 127.0.0.1 (porta interna NON esposta da Render), quindi è raggiungibile
solo dal worker Node nello stesso container: nessuna autenticazione necessaria.

Node e Python condividono il filesystem del container: i file scaricati vengono
passati per path, e il worker li cancella dopo l'invio.

Avvio: wa_bridge.start_in_thread(ns). No-op se WHATSAPP_ENABLED non è attivo.
"""

import os
import asyncio
import logging
import threading

from aiohttp import web

import core

logger = logging.getLogger(__name__)

BRIDGE_PORT = int(os.getenv('WA_BRIDGE_PORT', '8765'))
DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', '300'))
WHATSAPP_MAX_MB = float(os.getenv('WHATSAPP_MAX_MB', '16'))
WHATSAPP_MAX_BYTES = int(WHATSAPP_MAX_MB * 1024 * 1024)
VIDEO_EXTS = core.VIDEO_EXTS

# Gli helper di formattazione e la didascalia stanno in core.py (condivisi).


def build_app(ns):
    from social_downloader import SocialMediaDownloader
    dl = SocialMediaDownloader(debug=os.getenv('SMD_DEBUG', '0') == '1')
    rs = ns.ranking_store

    async def download(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({'success': False, 'error': 'bad request'})
        url = (body.get('url') or '').strip()
        sender_name = body.get('sender_name')
        if not url:
            return web.json_response({'success': False, 'error': 'no url'})
        try:
            info = await asyncio.wait_for(dl.download_video(url), timeout=DOWNLOAD_TIMEOUT)
        except asyncio.TimeoutError:
            return web.json_response({'success': False, 'error': 'timeout'})
        except Exception as e:
            logger.warning(f"WA bridge download error ({url}): {e}")
            return web.json_response({'success': False, 'error': str(e)[:200]})

        if info and info.get('skip_long'):
            return web.json_response({'success': False, 'skip_long': True})
        if not info or not info.get('success'):
            return web.json_response({'success': False, 'error': (info or {}).get('error', 'errore')})

        if info.get('type', 'video') == 'video':
            paths = [info.get('file_path')]
        else:
            paths = list(info.get('files') or [])
        files = []
        for p in paths:
            if p and os.path.exists(p):
                files.append({'path': os.path.abspath(p),
                              'video': os.path.splitext(p)[1].lower() in VIDEO_EXTS,
                              'size': os.path.getsize(p)})
        if not files:
            return web.json_response({'success': False, 'error': 'nessun file'})

        has_video = any(f['video'] for f in files)
        has_photo = any(not f['video'] for f in files)
        label = 'Contenuto' if (has_video and has_photo) else ('Video' if has_video else 'Foto')
        caption = core.build_caption(info, url, sender_name or '', info.get('title') or 'Contenuto',
                                     dialect='whatsapp', invite=True, max_desc=1500)

        oversized = any(f['size'] > WHATSAPP_MAX_BYTES for f in files)
        if oversized:
            # WhatsApp non gradisce file troppo grandi: il worker manderà solo il link
            for f in files:
                try:
                    os.remove(f['path'])
                except Exception:
                    pass
            return web.json_response({'success': False, 'too_big': True, 'caption': caption,
                                      'max_mb': WHATSAPP_MAX_MB})

        return web.json_response({'success': True, 'type': info.get('type', 'video'),
                                  'files': files, 'caption': caption, 'label': label})

    async def sent(request):
        """Punto in classifica + creazione record voto, dopo invio riuscito."""
        try:
            b = await request.json()
        except Exception:
            return web.json_response({'achievements': []})
        out = {'achievements': []}
        try:
            uid = int(b.get('user_id'))
        except (TypeError, ValueError):
            return web.json_response(out)
        name = b.get('user_name') or 'Utente'
        key = b.get('key')
        try:
            totals = await rs.add_point(uid, name)
            already = await rs.get_earned(uid)
            for code in ns.newly_earned(totals, already):
                await rs.add_earned(uid, code)
                txt = ns.achievements.get(code, code)
                txt = txt.replace('<b>', '*').replace('</b>', '*')
                out['achievements'].append(txt)
        except Exception as e:
            logger.warning(f"WA bridge sent/point: {e}")
        if key:
            try:
                await rs.create_vote(key, uid, name, fid=None)
            except Exception:
                pass
        return web.json_response(out)

    async def react(request):
        try:
            b = await request.json()
        except Exception:
            return web.json_response({'ok': False})
        key = b.get('key')
        emoji = b.get('emoji') or ''
        try:
            uid = int(b.get('user_id'))
        except (TypeError, ValueError):
            return web.json_response({'ok': False})
        try:
            res = await rs.set_reaction(key, uid, [emoji] if emoji else [])
        except Exception as e:
            logger.debug(f"WA bridge react: {e}")
            return web.json_response({'ok': False})
        announce = None
        voter_ach = False
        if res and not res.get('self'):
            if res.get('milestone'):
                announce = f"🎉 Il post di *{res.get('name','Utente')}* ha raggiunto *{res['milestone']} voti*! 🔥"
            if res.get('added') and res.get('voter_total') == ns.voter_ach_at:
                voter_ach = (ns.achievements.get('voter', '') or '').replace('<b>', '*').replace('</b>', '*')
        return web.json_response({'ok': True, 'announce': announce, 'voter_ach': voter_ach})

    async def auth_get(request):
        try:
            blob = await rs.get_wa_auth()
        except Exception as e:
            logger.warning(f"WA bridge auth get: {e}")
            blob = None
        return web.json_response({'blob': blob})

    async def auth_put(request):
        try:
            b = await request.json()
            await rs.set_wa_auth(b.get('blob'))
        except Exception as e:
            logger.warning(f"WA bridge auth put: {e}")
            return web.json_response({'ok': False})
        return web.json_response({'ok': True})

    async def ping(request):
        return web.Response(text="OK")

    app = web.Application(client_max_size=8 * 1024 * 1024)
    app.add_routes([
        web.get('/ping', ping),
        web.post('/download', download),
        web.post('/sent', sent),
        web.post('/react', react),
        web.get('/authstate', auth_get),
        web.put('/authstate', auth_put),
    ])
    return app


def start_in_thread(ns):
    """Avvia il bridge HTTP interno in un thread col suo event loop. No-op se
    WHATSAPP_ENABLED non è attivo."""
    if os.getenv('WHATSAPP_ENABLED', '0') != '1':
        logger.info("WhatsApp: WHATSAPP_ENABLED non attivo, bridge non avviato")
        return None

    async def _run():
        app = build_app(ns)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', BRIDGE_PORT)
        await site.start()
        logger.info(f"WhatsApp: bridge interno attivo su 127.0.0.1:{BRIDGE_PORT}")
        await asyncio.Event().wait()

    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run())
        except Exception as e:
            logger.error(f"WhatsApp: bridge terminato con errore: {e}")

    t = threading.Thread(target=_runner, daemon=True, name="wa-bridge")
    t.start()
    return t

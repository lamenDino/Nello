#!/usr/bin/env python3
"""Frontend Discord di Nello.

Riusa lo stesso motore del bot Telegram: il downloader (social_downloader) e lo
store dei ranking/voti (ranking_store). Gira in un thread separato, con il suo
event loop, accanto al bot Telegram. Voti e classifiche sono CONDIVISI con
Telegram (stesso Firestore): un voto su Discord conta nella settimanale, ecc.

Dipendenze passate via `ns` (namespace) da bot.py, per non importare bot.py qui
(eviterebbe import circolari / doppia inizializzazione dello store).

Avvio: discord_bot.start_in_thread(token, ns). Se `discord` non è installato o il
token manca, non fa nulla (il bot Telegram parte comunque).
"""

import os
import time
import asyncio
import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)

# Limite upload Discord (server senza boost ~25MB). Oltre, mandiamo solo il link.
DISCORD_MAX_MB = float(os.getenv('DISCORD_MAX_MB', '25'))
DISCORD_MAX_BYTES = int(DISCORD_MAX_MB * 1024 * 1024)

# Reazioni pre-caricate sotto ogni post (un click = un voto). Stesse di Telegram.
REACTIONS = ['👍', '😂', '🔥', '😍', '😭', '🤮']
VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.flv', '.ts')
VOTER_ACH_AT = 25  # reazioni date per sbloccare "Votante attivo" (come Telegram)

# Rate limit anti-spam per utente Discord (in memoria, si azzera ai restart)
RATE_MAX_PER_HOUR = int(os.getenv('DISCORD_RATE_MAX_PER_HOUR', os.getenv('RATE_MAX_PER_HOUR', '20')))
_rate_hits = defaultdict(list)


def _rate_limited(user_id: int) -> bool:
    now = time.time()
    hits = [t for t in _rate_hits[user_id] if now - t < 3600]
    _rate_hits[user_id] = hits
    if len(hits) >= RATE_MAX_PER_HOUR:
        return True
    hits.append(now)
    return False


def _human(n) -> str:
    try:
        n = int(n)
    except (ValueError, TypeError):
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace('.0M', 'M')
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace('.0K', 'K')
    return str(n)


def _fmt_duration(sec) -> str:
    try:
        sec = int(sec)
    except (ValueError, TypeError):
        return ""
    if sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _meta_line(info: dict, title: str) -> str:
    bits = []
    d = _fmt_duration(info.get('duration'))
    if d:
        bits.append(f"⏱️ {d}")
    v = _human(info.get('view_count'))
    if v:
        bits.append(f"👁️ {v}")
    likes = _human(info.get('like_count'))
    if likes:
        bits.append(f"❤️ {likes}")
    up = info.get('uploader') or info.get('channel')
    if up and str(up).lower() not in ('sconosciuto', 'none', ''):
        if str(up).lower() not in (title or '').lower():
            bits.append(f"✍️ {str(up)[:40]}")
    return "  ".join(bits)


def _media_label(info: dict) -> str:
    if info.get('type', 'video') == 'video':
        return 'Video'
    files = info.get('files', []) or []
    has_video = any(os.path.splitext(f)[1].lower() in VIDEO_EXTS for f in files)
    has_photo = any(os.path.splitext(f)[1].lower() not in VIDEO_EXTS for f in files)
    if has_video and has_photo:
        return 'Contenuto'
    if has_video:
        return 'Video'
    return 'Foto'


def _build_caption(ns, info: dict, url: str, sender: str, label: str) -> str:
    raw_title = info.get('title') or 'Contenuto'
    # taglio descrizione: limite messaggio Discord = 2000, lasciamo margine
    if len(raw_title) > 1500:
        raw_title = raw_title[:1500].rstrip() + '…'
    clean = ns.clean_title(raw_title, info.get('uploader') or info.get('channel')) or raw_title
    plat = ns.detect_platform(url)
    inviato = 'inviata' if label == 'Foto' else 'inviato'
    lines = [
        f"📥 **{label} da:** {plat}",
        f"👤 **{label} {inviato} da:** {sender}",
        f"🔗 **Link originale:** <{url}>",
        f"📝 **Info:** {clean}",
    ]
    meta = _meta_line(info, clean)
    if meta:
        lines.append(f"📊 {meta}")
    lines.append("💬 *Reagisci con un'emoji per votare il post!*")
    return "\n".join(lines)


def _clean_files(paths):
    for p in paths or []:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def build_client(ns):
    import discord

    intents = discord.Intents.default()
    intents.message_content = True  # privilegiato: serve a leggere link/comandi
    client = discord.Client(intents=intents)

    rs = ns.ranking_store
    # Downloader DEDICATO al bot Discord (evita la race su last_fallback_title con
    # il downloader del bot Telegram quando scaricano in contemporanea).
    from social_downloader import SocialMediaDownloader
    dl = SocialMediaDownloader(debug=os.getenv('SMD_DEBUG', '0') == '1')

    download_timeout = int(os.getenv('DOWNLOAD_TIMEOUT', '300'))

    async def _announce(channel, text):
        try:
            await channel.send(text)
        except Exception:
            pass

    async def _award_point(channel, author):
        """Punto in classifica + eventuali achievement per chi posta."""
        try:
            totals = await rs.add_point(author.id, author.display_name)
        except Exception as e:
            logger.warning(f"Discord add_point fallito: {e}")
            return
        try:
            already = await rs.get_earned(author.id)
            for code in ns.newly_earned(totals, already):
                await rs.add_earned(author.id, code)
                txt = ns.achievements.get(code)
                if txt:
                    # togli i tag HTML di Telegram per Discord
                    txt = txt.replace('<b>', '**').replace('</b>', '**')
                    await _announce(channel, f"🎉 **{author.display_name}** ha sbloccato un achievement!\n{txt}")
        except Exception as e:
            logger.debug(f"Discord achievement check: {e}")

    async def _send_media(channel, info, url, author):
        """Invia video o carosello su Discord. Per replicare il layout di Telegram
        (media SOPRA, info SOTTO), manda prima il media senza testo e poi la
        didascalia come messaggio separato sotto: è su quest'ultimo che si vota,
        così le reazioni finiscono proprio sotto le info. Ritorna il messaggio su
        cui si vota, oppure None se non è stato inviato nulla."""
        import discord
        label = _media_label(info)
        caption = _build_caption(ns, info, url, author.mention, label)

        if info.get('type', 'video') == 'video':
            paths = [info.get('file_path')]
        else:
            paths = list(info.get('files', []) or [])
        paths = [p for p in paths if p and os.path.exists(p)]
        if not paths:
            _clean_files(paths)
            return None

        # File troppo grandi per Discord: manda il link in chiaro.
        small = [p for p in paths if os.path.getsize(p) <= DISCORD_MAX_BYTES]
        too_big = [p for p in paths if os.path.getsize(p) > DISCORD_MAX_BYTES]
        if too_big and not small:
            await channel.send(
                f"🐘 File troppo pesante per Discord (>{DISCORD_MAX_MB:.0f}MB).\n"
                f"{caption}"
            )
            _clean_files(paths)
            return None

        try:
            # 1) i media in cima, senza testo (Discord: max 10 allegati per messaggio)
            for i in range(0, len(small), 10):
                files = [discord.File(p) for p in small[i:i + 10]]
                await channel.send(files=files)
            # 2) le info sotto: questo è il messaggio su cui si vota
            vote_msg = await channel.send(content=caption)
        except Exception as e:
            logger.warning(f"Discord invio media fallito ({url}): {e}")
            _clean_files(paths)
            return None
        _clean_files(paths)
        return vote_msg

    async def _handle_links(message, urls):
        channel = message.channel
        author = message.author
        if _rate_limited(author.id):
            try:
                await channel.send(f"🚦 Vai piano {author.display_name}, hai raggiunto il limite orario di download.")
            except Exception:
                pass
            return

        sent_any = False
        for url in urls:
            loading = None
            try:
                loading = await channel.send(f"⏳ Download in corso...\n🔗 <{url}>")
            except Exception:
                pass
            try:
                try:
                    info = await asyncio.wait_for(dl.download_video(url), timeout=download_timeout)
                except asyncio.TimeoutError:
                    if loading:
                        await loading.edit(content=f"⏳ Ci ho messo troppo su questo link, ho mollato.\n🔗 <{url}>")
                    continue

                if info and info.get('skip_long'):
                    # YouTube troppo lungo: lascia solo il link
                    if loading:
                        try:
                            await loading.delete()
                        except Exception:
                            pass
                    continue

                if not info or not info.get('success'):
                    err = (info or {}).get('error', 'Errore sconosciuto')
                    if loading:
                        await loading.edit(content=f"😵 Non sono riuscito a scaricarlo.\n⚠️ {err}\n🔗 <{url}>")
                    continue

                vote_msg = await _send_media(channel, info, url, author)
                if loading:
                    try:
                        await loading.delete()
                    except Exception:
                        pass
                if not vote_msg:
                    continue
                sent_any = True

                # punto in classifica (solo su invio riuscito)
                await _award_point(channel, author)

                # registra il voto su quel messaggio. NON pre-carichiamo reazioni:
                # gli utenti votano con le reazioni native di Discord (qualsiasi
                # emoji = 1 voto), così non resta la "1" del bot sotto ogni post.
                try:
                    await rs.create_vote(f"discord:{vote_msg.id}", author.id, author.display_name, fid=None)
                except Exception as e:
                    logger.debug(f"Discord create_vote: {e}")

            except Exception as e:
                logger.error(f"Discord handle link error ({url}): {e}")
                if loading:
                    try:
                        await loading.edit(content=f"😵 Errore su questo link.\n🔗 <{url}>")
                    except Exception:
                        pass

        # Cancella il messaggio originale col link (come su Telegram), se almeno un
        # download è riuscito. Richiede il permesso "Gestisci messaggi".
        if sent_any:
            try:
                await message.delete()
            except Exception as e:
                logger.debug(f"Discord: impossibile cancellare il messaggio originale: {e}")

    # ---------------- Comandi (prefisso !) ----------------

    def _fmt_board(rows, title, empty):
        if not rows:
            return f"**{title}**\n{empty}"
        medals = ['🥇', '🥈', '🥉']
        out = [f"**{title}**"]
        for i, (uid, cnt, name) in enumerate(rows):
            pos = medals[i] if i < 3 else f"{i+1}."
            out.append(f"{pos} {name} — {cnt}")
        return "\n".join(out)

    async def _handle_command(message):
        content = message.content.strip()
        cmd = content[1:].split()[0].lower()
        ch = message.channel
        author = message.author
        try:
            if cmd in ('classifica', 'top'):
                rows = await rs.get_board('weekly', 10)
                await ch.send(_fmt_board(rows, '🏆 Classifica settimanale', 'Ancora nessun contenuto questa settimana!'))
            elif cmd == 'mensile':
                rows = await rs.get_board('monthly', 10)
                await ch.send(_fmt_board(rows, '📅 Classifica mensile', 'Ancora nessun contenuto questo mese!'))
            elif cmd in ('record', 'alltime'):
                rows = await rs.get_board('alltime', 10)
                await ch.send(_fmt_board(rows, '👑 Classifica all-time', 'Ancora nessun contenuto!'))
            elif cmd == 'votati':
                rows = await rs.top_voted_week(10)
                await ch.send(_fmt_board(rows, '❤️ Più votati (settimana)', 'Ancora nessun voto questa settimana!'))
            elif cmd == 'stats':
                st = await rs.get_user_stats(author.id)
                emoji, rank_title = ns.get_rank(st.get('alltime', 0))
                await ch.send(
                    f"📊 **Statistiche di {author.display_name}**\n"
                    f"{emoji} Rango: **{rank_title}**\n"
                    f"📈 Questa settimana: {st.get('weekly', 0)}\n"
                    f"📅 Questo mese: {st.get('monthly', 0)}\n"
                    f"🏅 Totale: {st.get('alltime', 0)}"
                    + (f"  (#{st['rank']})" if st.get('rank') else "")
                )
            elif cmd == 'profilo':
                p = await rs.get_profile(author.id)
                emoji, rank_title = ns.get_rank(p.get('alltime', 0))
                await ch.send(
                    f"👤 **Profilo di {author.display_name}**\n"
                    f"{emoji} Rango: **{rank_title}**\n"
                    f"🏅 Contenuti totali: {p.get('alltime', 0)}\n"
                    f"❤️ Voti ricevuti: {p.get('votes_received', 0)}\n"
                    f"🔥 Miglior post: {p.get('best_video', 0)} voti\n"
                    f"🗳️ Voti dati: {p.get('vote_given', 0)}"
                )
            elif cmd in ('help', 'aiuto', 'nello'):
                await ch.send(
                    "🤖 **Nello** — incolla un link (TikTok, Instagram, YouTube, ecc.) e te lo scarico qui.\n"
                    "Vota i post con le reazioni 👍😂🔥😍.\n"
                    "Comandi: `!classifica` `!mensile` `!record` `!votati` `!stats` `!profilo`"
                )
        except Exception as e:
            logger.warning(f"Discord comando '{cmd}' fallito: {e}")

    # ---------------- Voti via reazioni native ----------------

    async def _vote(payload, delta):
        if client.user and payload.user_id == client.user.id:
            return  # ignora le reazioni messe dal bot stesso (pre-caricamento)
        key = f"discord:{payload.message_id}"
        try:
            res = await rs.react_delta(key, payload.user_id, delta)
        except Exception as e:
            logger.debug(f"Discord react_delta: {e}")
            return
        if not res or res.get('self'):
            return
        # annuncio traguardi del post
        channel = client.get_channel(payload.channel_id)
        if channel is None:
            return
        if res.get('milestone'):
            await _announce(channel, f"🎉 Il post di **{res.get('name','Utente')}** ha raggiunto **{res['milestone']} voti**! 🔥")
        if res.get('added') and res.get('voter_total') == VOTER_ACH_AT:
            txt = ns.achievements.get('voter', '')
            txt = txt.replace('<b>', '**').replace('</b>', '**')
            await _announce(channel, f"🎉 Achievement sbloccato!\n{txt}")

    # ---------------- Eventi ----------------

    @client.event
    async def on_ready():
        logger.info(f"Discord: connesso come {client.user} (server: {len(client.guilds)})")

    @client.event
    async def on_message(message):
        if message.author.bot:
            return
        content = (message.content or '').strip()
        if not content:
            return
        if content.startswith('!'):
            await _handle_command(message)
            return
        tokens = [t.strip('<>') for t in content.split()]
        urls = [t for t in tokens if ns.is_supported_link(t)]
        if urls:
            await _handle_links(message, urls)

    @client.event
    async def on_raw_reaction_add(payload):
        await _vote(payload, +1)

    @client.event
    async def on_raw_reaction_remove(payload):
        await _vote(payload, -1)

    return client


def start_in_thread(token, ns):
    """Avvia il bot Discord in un thread dedicato col suo event loop. No-op se
    manca il token o la libreria discord non è installata."""
    if not token:
        logger.info("Discord: DISCORD_TOKEN non impostato, frontend Discord disattivato")
        return None
    try:
        import discord  # noqa: F401
    except ImportError:
        logger.warning("Discord: libreria 'discord.py' non installata, frontend Discord disattivato")
        return None

    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            client = build_client(ns)
            loop.run_until_complete(client.start(token))
        except Exception as e:
            logger.error(f"Discord: bot terminato con errore: {e}")

    t = threading.Thread(target=_runner, daemon=True, name="discord-bot")
    t.start()
    logger.info("Discord: frontend avviato in thread separato")
    return t

"""Shared Italian-only voice transcription client and chat adapters."""
import asyncio
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid
import json

import aiohttp

MAX_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 180
log = logging.getLogger(__name__)
_lock = threading.Lock()
_seen = {}
_active = 0


def claim(key):
    global _active
    with _lock:
        now = time.monotonic()
        for old, expiry in list(_seen.items()):
            if expiry < now:
                del _seen[old]
        if key in _seen or _active >= 3:
            return False
        _seen[key] = now + 1800
        _active += 1
        return True


def release():
    global _active
    with _lock:
        _active -= 1


def eligible(size, duration=0):
    if hasattr(duration, 'total_seconds'):
        duration = duration.total_seconds()
    return 0 < int(size or 0) <= MAX_BYTES and 0 <= float(duration or 0) <= MAX_SECONDS


def outcome(result):
    if result.get('success') and result.get('language') == 'it' and result.get('text'):
        return {'text': result['text']}
    reason = result.get('skipped') or result.get('reason')
    log.info('Voice result: %s', reason or 'failed')
    if reason == 'remote_rate_limit':
        return {'notice': 'Il servizio di trascrizione ha raggiunto il limite di utilizzo. Riprova più tardi; l’audio originale resta nella chat.'}
    if reason == 'remote_not_configured':
        return {'notice': 'Il servizio di trascrizione deve essere configurato dall’amministratore. L’audio originale resta nella chat.'}
    if reason == 'remote_unavailable':
        return {'notice': 'Il servizio di trascrizione non è disponibile al momento. Riprova tra poco; l’audio originale resta nella chat.'}
    if reason in ('not_italian', 'not_italian_or_uncertain'):
        return {}
    if reason in ('uncertain_language', 'no_clear_speech'):
        return {'notice': 'Non riesco a riconoscere con sicurezza le parole o la lingua di questo vocale. Prova con una frase un po\u2019 pi\u00f9 lunga e chiara: trascrivo solo l\u2019italiano.'}
    return {'notice': 'Non sono riuscito a trascrivere questo vocale. Riprova tra poco; l\u2019audio originale resta nella chat.'}


async def transcribe_file(path, on_progress=None):
    if not eligible(Path(path).stat().st_size):
        return {}
    from remote_voice import provider, transcribe
    selected = provider()
    if selected == 'groq':
        # Direct call bypasses downloader cold starts, its serial media queue,
        # Whisper CPU work and the separate Java proofreading startup.
        return outcome(await transcribe(path))
    if selected != 'local':
        return outcome({'reason': 'remote_not_configured'})
    base = os.getenv('DOWNLOADER_URL', '').rstrip('/')
    token = os.getenv('DOWNLOADER_TOKEN', '')
    if not base or not token:
        return {}
    ident = str(uuid.uuid4())
    previous_progress = None
    timeout = aiohttp.ClientTimeout(total=150, sock_connect=20)
    async with aiohttp.ClientSession(headers={'Authorization': 'Bearer ' + token}, timeout=timeout) as session:
        try:
            for _ in range(40):
                try:
                    async with session.get(base + '/healthz') as response:
                        if response.status == 200 and (await response.json()).get('status') == 'ok':
                            break
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    pass
                await asyncio.sleep(3)
            else:
                return outcome({'reason': 'unavailable'})
            with open(path, 'rb') as audio:
                async with session.post(base + '/voice-jobs/' + ident, data=audio,
                                        headers={'Content-Type': 'application/octet-stream'}) as response:
                    response.raise_for_status()
            for _ in range(600):
                async with session.get(base + '/jobs/' + ident) as response:
                    response.raise_for_status()
                    job = await response.json()
                if job.get('state') == 'done':
                    result = job.get('result', {})
                    if result.get('language') not in (None, 'it'):
                        return {}
                    return outcome(result)
                progress = job.get('progress')
                if (on_progress and isinstance(progress, dict) and progress.get('language') == 'it'
                        and progress.get('text') and progress != previous_progress):
                    previous_progress = progress
                    try:
                        await on_progress(progress)
                    except Exception as exc:
                        log.warning('Voice progress delivery failed: %s', type(exc).__name__)
                await asyncio.sleep(2)
            return outcome({'reason': 'timeout'})
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning('Voice transcription unavailable')
            return outcome({'reason': 'unavailable'})
        finally:
            try:
                async with session.delete(base + '/jobs/' + ident, timeout=aiohttp.ClientTimeout(total=10)):
                    pass
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass


def reply_parts(text, limit=3500):
    from photo_text import split_text
    return split_text('Trascrizione del vocale:\n\n' + text, limit)


def result_parts(result, limit=3500):
    if result.get('text'):
        return reply_parts(result['text'], limit)
    return [result['notice']] if result.get('notice') else []


def progress_text(progress, limit=3500):
    if progress.get('language') != 'it' or not progress.get('text'):
        return ''
    done, total = int(progress.get('completed', 0)), int(progress.get('total', 0))
    status = 'Revisione del testo in corso...' if total and done == total else f'Trascrizione in corso: {done}/{total}'
    parts = reply_parts(progress['text'], limit - 100)
    return parts[0] + ('\n...' if len(parts) > 1 else '') + '\n\n' + status


class LiveReply:
    """Edit one provisional bot reply; never touch the user's original audio."""
    def __init__(self, send, edit, limit=3500):
        self.send, self.edit, self.limit = send, edit, limit
        self.message = None

    async def start(self):
        from remote_voice import provider
        wait = ' Potrebbe richiedere alcuni minuti.' if provider() == 'local' else ''
        self.message = await self.send('Audio ricevuto. Controllo la lingua e preparo la trascrizione.' + wait + ' L’audio originale resta nella chat.')

    async def update(self, progress):
        text = progress_text(progress, self.limit)
        if not text:
            return
        if self.message is None:
            self.message = await self.send(text)
        else:
            await self.edit(self.message, text)

    async def finish(self, result):
        parts = result_parts(result, self.limit)
        if self.message is not None:
            text = parts.pop(0) if parts else 'Trascrizione non completata; l’audio originale resta nella chat.'
            try:
                await self.edit(self.message, text)
            except Exception:
                # Deliver the final text even if editing the provisional reply fails.
                await self.send(text)
        for text in parts:
            await self.send(text)


async def telegram_voice(update, context):
    message = update.effective_message
    media = message.voice or message.audio
    if not media or (message.from_user and message.from_user.is_bot):
        return
    if not eligible(media.file_size, media.duration):
        return
    key = f'tg:{message.chat_id}:{message.message_id}'
    if not claim(key):
        return
    live = LiveReply(lambda text: message.reply_text(text, parse_mode=None, do_quote=True),
                     lambda reply, text: reply.edit_text(text, parse_mode=None))
    try:
        await live.start()
        log.info('Telegram voice accepted: duration=%s', media.duration)
        with tempfile.TemporaryDirectory(prefix='voice_tg_') as directory:
            path = Path(directory) / 'input.audio'
            remote = await media.get_file()
            await remote.download_to_drive(custom_path=path)
            result = await transcribe_file(path, on_progress=live.update)
        # Reply only: never delete or replace the original audio message.
        await live.finish(result)
        log.info('Telegram voice reply delivered: transcript=%s', bool(result.get('text')))
    except Exception as exc:
        log.warning('Telegram voice failed: %s', type(exc).__name__)
        try:
            await live.finish(outcome({'reason': 'unavailable'}))
        except Exception as delivery_exc:
            log.warning('Telegram voice failure notice unavailable: %s', type(delivery_exc).__name__)
    finally:
        release()


async def discord_voice(message):
    import discord
    if message.author.bot:
        return
    for attachment in message.attachments[:1]:
        is_audio = attachment.is_voice_message() or (attachment.content_type or '').startswith('audio/')
        if not is_audio or not eligible(attachment.size, attachment.duration):
            continue
        if not claim(f'dc:{message.id}:{attachment.id}'):
            continue
        live = LiveReply(lambda text: message.reply(text, allowed_mentions=discord.AllowedMentions.none(), mention_author=False),
                         lambda reply, text: reply.edit(content=text, allowed_mentions=discord.AllowedMentions.none()), 1900)
        try:
            with tempfile.TemporaryDirectory(prefix='voice_dc_') as directory:
                path = Path(directory) / 'input.audio'
                await attachment.save(path)
                result = await transcribe_file(path, on_progress=live.update)
            await live.finish(result)
        except Exception as exc:
            log.warning('Discord voice failed: %s', type(exc).__name__)
        finally:
            release()


async def whatsapp_voice(request):
    from aiohttp import web
    key = request.headers.get('X-Voice-Key', '')
    if not key or len(key) > 300 or not claim('wa:' + key):
        return web.json_response({})
    try:
        with tempfile.TemporaryDirectory(prefix='voice_wa_') as directory:
            path = Path(directory) / 'input.audio'
            size = 0
            with path.open('wb') as output:
                async with asyncio.timeout(60):
                    async for chunk in request.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise web.HTTPRequestEntityTooLarge(max_size=MAX_BYTES, actual_size=size)
                        output.write(chunk)
            if 'application/x-ndjson' in request.headers.get('Accept', ''):
                response = web.StreamResponse(headers={'Content-Type': 'application/x-ndjson'})
                await response.prepare(request)
                async def progress(value):
                    text = progress_text(value)
                    if text:
                        await response.write((json.dumps({'type': 'progress', 'text': text}) + '\n').encode())
                result = await transcribe_file(path, on_progress=progress)
                await response.write((json.dumps({'type': 'done', 'parts': result_parts(result)}) + '\n').encode())
                await response.write_eof()
                return response
            result = await transcribe_file(path)
        return web.json_response({'parts': result_parts(result)})
    finally:
        release()

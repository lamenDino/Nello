"""Shared Italian-only voice transcription client and chat adapters."""
import asyncio
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid

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
    return 0 < int(size or 0) <= MAX_BYTES and 0 <= float(duration or 0) <= MAX_SECONDS


async def transcribe_file(path):
    if not eligible(Path(path).stat().st_size):
        return {}
    base = os.getenv('DOWNLOADER_URL', '').rstrip('/')
    token = os.getenv('DOWNLOADER_TOKEN', '')
    if not base or not token:
        return {}
    ident = str(uuid.uuid4())
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
                return {}
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
                    if result.get('success') and result.get('language') == 'it' and isinstance(result.get('text'), str):
                        return {'text': result['text']}
                    return {}
                await asyncio.sleep(2)
            return {}
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning('Voice transcription unavailable')
            return {}
        finally:
            try:
                async with session.delete(base + '/jobs/' + ident, timeout=aiohttp.ClientTimeout(total=10)):
                    pass
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass


def reply_parts(text, limit=3500):
    from photo_text import split_text
    return split_text('Trascrizione del vocale:\n' + text, limit)


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
    try:
        with tempfile.TemporaryDirectory(prefix='voice_tg_') as directory:
            path = Path(directory) / 'input.audio'
            remote = await media.get_file()
            await remote.download_to_drive(custom_path=path)
            result = await transcribe_file(path)
        for text in reply_parts(result['text']) if result.get('text') else []:
            await message.reply_text(text, parse_mode=None, do_quote=True)
    except Exception as exc:
        log.warning('Telegram voice failed: %s', type(exc).__name__)
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
        try:
            with tempfile.TemporaryDirectory(prefix='voice_dc_') as directory:
                path = Path(directory) / 'input.audio'
                await attachment.save(path)
                result = await transcribe_file(path)
            for text in reply_parts(result['text'], 1900) if result.get('text') else []:
                await message.reply(text, allowed_mentions=discord.AllowedMentions.none(), mention_author=False)
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
            result = await transcribe_file(path)
        return web.json_response({'parts': reply_parts(result['text'])} if result.get('text') else {})
    finally:
        release()

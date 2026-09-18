"""Authenticated, single-request metadata lookup; no media download or conversion."""
import asyncio
import hmac
import logging
import os
import re
from aiohttp import web
from facebook_nodes import extract_video

log = logging.getLogger(__name__)


def resolve(ident):
    from curl_cffi import requests
    response = requests.get('https://www.facebook.com/reel/' + ident,
                            impersonate='chrome99', timeout=20, stream=True)
    try:
        if response.status_code != 200:
            return None
        content = bytearray()
        for chunk in response.iter_content(128 * 1024):
            content.extend(chunk)
            if len(content) > 8 * 1024 * 1024:
                return None
        return extract_video(content.decode('utf-8', 'replace'), ident)
    finally:
        response.close()


def handler():
    lock = asyncio.Lock()

    async def get(request):
        token = os.getenv('DOWNLOADER_TOKEN', '')
        if len(token) < 32 or not hmac.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + token):
            raise web.HTTPUnauthorized()
        ident = request.match_info['ident']
        if not re.fullmatch(r'\d{5,30}', ident):
            raise web.HTTPBadRequest()
        if lock.locked():
            raise web.HTTPServiceUnavailable()
        async with lock:
            try:
                media = await asyncio.to_thread(resolve, ident)
            except Exception as exc:
                log.warning('Facebook metadata lookup failed: %s', type(exc).__name__)
                media = None
        log.info('Facebook metadata lookup: id=%s available=%s', ident, bool(media))
        return web.json_response({'id': ident, 'media': media}, headers={'Cache-Control': 'no-store'})

    return get

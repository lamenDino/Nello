"""Complete photo descriptions, bounded delivery and optional English translation."""
import asyncio
import hashlib
import logging
import re
from collections import OrderedDict
from html import unescape
from html.parser import HTMLParser

import aiohttp
from langdetect import DetectorFactory, detect_langs

DetectorFactory.seed = 0
log = logging.getLogger(__name__)
_cache = OrderedDict()


def split_text(text, limit=3500, *, encoding='utf-16-le', divisor=2):
    """Lossless split, including non-BMP emoji; prefer whitespace boundaries."""
    result = []
    while text:
        used = end = 0
        for char in text:
            cost = len(char.encode(encoding)) // divisor
            if used + cost > limit:
                break
            used += cost
            end += 1
        if end < len(text):
            boundary = max(text.rfind('\n', 0, end), text.rfind(' ', 0, end))
            if boundary > end // 2:
                end = boundary + 1
        result.append(text[:end])
        text = text[end:]
    return result


class _Plain(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.feed(value)

    def handle_data(self, value):
        self.parts.append(value)


def plain_text(caption):
    return ''.join(_Plain(caption).parts)


def telegram_parts(caption):
    plain = plain_text(caption)
    if len(plain.encode('utf-16-le')) // 2 <= 1024:
        return caption, []
    lines = caption.split('\n')
    header = '\n'.join(lines[:3])
    body = ''.join(_Plain('\n'.join(lines[3:])).parts)
    if len(''.join(_Plain(header).parts).encode('utf-16-le')) // 2 > 1024:
        return '', split_text(plain)
    return header, split_text(body)


def _is_english(text):
    sample = re.sub(r'https?://\S+|[@#]\S+', '', text)
    try:
        languages = detect_langs(sample)
        return languages[0].lang == 'en' and languages[0].prob >= 0.90
    except Exception:
        return False


async def photo_description(text):
    """Translate English only, atomically; never replace original with API errors."""
    if not text:
        return text
    key = hashlib.sha256(text.encode()).hexdigest()
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    if not await asyncio.to_thread(_is_english, text):
        return text
    try:
        translated = []
        async with asyncio.timeout(30):
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                # Preserve links, mentions, hashtags and paragraph separators literally.
                for part in re.split(r'(https?://\S+|[@#]\S+|\n+)', text):
                    if not part or re.match(r'https?://|[@#]|\n', part) or not part.strip():
                        translated.append(part)
                        continue
                    for chunk in split_text(part, 500, encoding='utf-8', divisor=1):
                        lead = chunk[:len(chunk) - len(chunk.lstrip())]
                        tail = chunk[len(chunk.rstrip()):]
                        async with session.get('https://api.mymemory.translated.net/get',
                                               params={'q': chunk.strip(), 'langpair': 'en|it'}) as response:
                            response.raise_for_status()
                            data = await response.json()
                        value = data.get('responseData', {}).get('translatedText')
                        if str(data.get('responseStatus')) != '200' or data.get('quotaFinished') or not value:
                            raise ValueError('Translation unavailable')
                        translated.append(lead + unescape(value).strip() + tail)
        result = ''.join(translated)
        _cache[key] = result
        while len(_cache) > 128:
            _cache.popitem(last=False)
        return result
    except Exception as exc:
        log.warning('Photo translation unavailable (%s); keeping complete original', type(exc).__name__)
        return text

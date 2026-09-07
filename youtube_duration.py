"""Read duration from the watch page without loading players or media formats."""
import json
import re
from urllib.parse import urlsplit, parse_qs

import requests


def video_id(url):
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    if host in ('youtu.be', 'www.youtu.be'):
        candidate = parts.path.strip('/').split('/')[0]
    elif host == 'youtube.com' or host.endswith('.youtube.com'):
        segments = parts.path.strip('/').split('/')
        candidate = (segments[1] if len(segments) >= 2 and segments[0] in ('shorts', 'embed', 'live')
                     else parse_qs(parts.query).get('v', [''])[0])
    else:
        return None
    return candidate if re.fullmatch(r'[A-Za-z0-9_-]{11}', candidate) else None


def parse_duration(page, expected_id):
    for match in re.finditer(r'(?:ytInitialPlayerResponse\s*=|"ytInitialPlayerResponse"\s*:)\s*', page):
        try:
            data, _ = json.JSONDecoder().raw_decode(page[match.end():])
            details = data.get('videoDetails', {})
            if details.get('videoId') != expected_id or details.get('isLiveContent'):
                continue
            duration = float(details['lengthSeconds'])
            if 0 < duration < float('inf'):
                return duration
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return None


def youtube_duration(url):
    ident = video_id(url)
    if not ident:
        return None
    try:
        with requests.get('https://www.youtube.com/watch', params={'v': ident},
                          headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US'},
                          stream=True, timeout=(5, 10)) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) >= 2 * 1024 * 1024:
                    break
            return parse_duration(content.decode('utf-8', errors='replace'), ident)
    except requests.RequestException:
        return None

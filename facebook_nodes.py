"""Bounded Facebook page parsers shared with the downloader implementation."""

from html.parser import HTMLParser

import json

from urllib.parse import urlsplit

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.active = dict(attrs).get('type') == 'application/json'
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.blocks.append(''.join(self.parts))
            self.parts = []
            self.active = False

def extract_video(page, ident):
    scripts = Scripts()
    scripts.feed(page)
    candidates = {}
    duration = None
    for block in scripts.blocks:
        try:
            stack = [json.loads(block)]
        except ValueError:
            continue
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
                if str(node.get('id')) != ident:
                    continue
                if node.get('length_in_second'):
                    duration = node['length_in_second']
                for data in (node, node.get('videoDeliveryLegacyFields') or {}):
                    if not isinstance(data, dict):
                        continue
                    for quality in ('sd', 'hd'):
                        uri = data.get('browser_native_' + quality + '_url')
                        if (isinstance(uri, str) and uri.startswith('https://')
                                and (urlsplit(uri).hostname or '').endswith('.fbcdn.net')):
                            candidates[quality] = uri
    uri = candidates.get('sd') or candidates.get('hd')
    return {'url': uri, 'duration': duration} if uri else None

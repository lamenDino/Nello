"""Stable media identity for duplicate detection and Telegram file caching."""
from urllib.parse import urlsplit, parse_qs


def link_key(url):
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or '').lower()
    if host in ('facebook.com', 'www.facebook.com', 'm.facebook.com'):
        if parsed.path.startswith('/share/') or '/posts/' in parsed.path or parsed.path in ('/permalink.php', '/story.php'):
            # Old entries may contain a recommended video unrelated to this post.
            return 'facebook-post-v2/' + parsed.path.strip('/') + ('?' + parsed.query if parsed.path.endswith('.php') else '')
        field = 'fbid' if parsed.path.rstrip('/') in ('/photo', '/photo.php') else None
        if field:
            ident = parse_qs(parsed.query).get(field, [''])[0]
            if ident.isdigit():
                # Different photos must never share the old facebook.com/photo key.
                return 'facebook.com/photo/' + ident
    value = url.strip().lower().split('?')[0].split('#')[0]
    value = value.replace('https://', '').replace('http://', '').replace('www.', '')
    return value.rstrip('/')

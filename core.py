#!/usr/bin/env python3
"""Nucleo condiviso dai vari frontend (Telegram / Discord / WhatsApp).

Tiene in UN SOLO posto la logica che prima era duplicata in bot.py, discord_bot.py
e wa_bridge.py: rilevamento piattaforma, helper di formattazione e — soprattutto —
la costruzione della didascalia, con un parametro `dialect` per rendere il testo
nel formato giusto (HTML per Telegram, markdown Discord, markdown WhatsApp).

Così una modifica alla didascalia si fa una volta sola. I frontend passano solo le
parti che li distinguono (mittente già renderizzato, icone, se mostrare l'invito).
"""

from html import escape as _html_escape

VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.flv', '.ts')

# Pool di icone "vivaci" pescate a caso (usate da Telegram per variare la didascalia).
ICONS_VIDEO = ["🎬", "📹", "🎥", "🍿", "📺", "🎞️", "🕹️", "📀", "🎦"]
ICONS_FOTO = ["📸", "🖼️", "📷", "🌄", "🏞️", "🎨", "🪄", "🖌️", "🌟"]
ICONS_USER = ["👤", "🙋", "😎", "🤙", "🫶", "🧑‍💻", "🦸", "🥷", "👑", "🤩"]
ICONS_LINK = ["🔗", "🌐", "📎", "🧷", "➡️", "🪢", "📡"]
ICONS_META = ["📝", "💬", "🗒️", "✨", "💭", "📌", "🧠", "🔎"]

# Icone fisse di default (Discord / WhatsApp non randomizzano).
DEFAULT_ICONS = {'main': '📥', 'user': '👤', 'link': '🔗', 'meta': '📝'}

# Dialetti di formattazione: grassetto/corsivo/escape/wrap-link per ogni frontend.
DIALECTS = {
    'html':     {'b': lambda s: f"<b>{s}</b>", 'i': lambda s: f"<i>{s}</i>",
                 'esc': _html_escape, 'wrap': lambda u: _html_escape(u)},
    'discord':  {'b': lambda s: f"**{s}**",    'i': lambda s: f"*{s}*",
                 'esc': lambda s: s,           'wrap': lambda u: f"<{u}>"},
    'whatsapp': {'b': lambda s: f"*{s}*",      'i': lambda s: f"_{s}_",
                 'esc': lambda s: s,           'wrap': lambda u: u},
}

INVITE_TEXT = "Reagisci con un'emoji per votare il post!"


def detect_platform(url: str) -> str:
    url = url.lower()
    if "tiktok" in url:
        return "TikTok"
    if "instagram" in url:
        return "Instagram"
    if "facebook" in url or "fb.watch" in url:
        return "Facebook"
    if "youtube" in url or "youtu.be" in url:
        if "/shorts/" in url:
            return "YouTube Shorts"
        return "YouTube"
    if "twitter" in url or "x.com" in url:
        return "Twitter / X"
    if "reddit" in url or "redd.it" in url:
        return "Reddit"
    if "twitch" in url:
        return "Twitch"
    return "Sconosciuta"


def media_label(info: dict) -> str:
    """Ritorna 'Video', 'Foto' o 'Contenuto' in base a cosa si sta inviando davvero."""
    import os
    if info.get("type", "video") == "video":
        return "Video"
    files = info.get("files", []) or []
    has_video = any(os.path.splitext(f)[1].lower() in VIDEO_EXTS for f in files)
    has_photo = any(os.path.splitext(f)[1].lower() not in VIDEO_EXTS for f in files)
    if has_video and has_photo:
        return "Contenuto"
    if has_video:
        return "Video"
    return "Foto"


def fmt_duration(sec) -> str:
    try:
        sec = int(sec)
    except (ValueError, TypeError):
        return ""
    if sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def human(n) -> str:
    try:
        n = int(n)
    except (ValueError, TypeError):
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace('.0M', 'M')
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace('.0K', 'K')
    return str(n)


def clean_title(raw: str, uploader: str = None) -> str:
    """Ripulisce il titolo da info ridondanti che alcune piattaforme (es. Facebook)
    incollano dentro: prefisso 'NN views · NN reactions |' e suffisso '| Autore'."""
    if not raw:
        return raw
    import re
    t = raw
    t = re.sub(r'^\s*[\d.,]+\s*[KMB]?\s*views?\b.*?\|\s*', '', t, flags=re.IGNORECASE)
    if uploader and str(uploader).lower() not in ('sconosciuto', 'none', ''):
        t = re.sub(r'\s*\|\s*' + re.escape(str(uploader)) + r'\s*$', '', t, flags=re.IGNORECASE)
    return t.strip(' |\n')


def meta_line(info: dict, title: str = '', esc=lambda s: s) -> str:
    """Riga opzionale con durata/views/like/autore, se disponibili. `esc` applica
    l'escaping del dialetto all'autore (HTML per Telegram, identità altrove)."""
    bits = []
    d = fmt_duration(info.get('duration'))
    if d:
        bits.append(f"⏱️ {d}")
    v = human(info.get('view_count'))
    if v:
        bits.append(f"👁️ {v}")
    likes = human(info.get('like_count'))
    if likes:
        bits.append(f"❤️ {likes}")
    up = info.get('uploader') or info.get('channel')
    if up and str(up).lower() not in ('sconosciuto', 'none', ''):
        if str(up).lower() not in (title or '').lower():
            bits.append(f"✍️ {esc(str(up)[:40])}")
    return "  ".join(bits)


def build_caption(info: dict, url: str, sender: str, raw_title: str, *,
                  dialect: str = 'html', icons: dict = None, invite: bool = False,
                  max_desc: int = None) -> str:
    """Didascalia unificata. `sender` è già renderizzato dal frontend (menzione
    Telegram, mention Discord, nome WhatsApp). `icons` di default sono quelle fisse;
    Telegram passa quelle casuali. `invite` aggiunge la riga "Reagisci...".
    `max_desc` tronca la descrizione (se il frontend non l'ha già fatto)."""
    cfg = DIALECTS[dialect]
    icons = icons or DEFAULT_ICONS
    label = media_label(info)
    inviato = "inviata" if label == "Foto" else "inviato"

    rt = raw_title or 'Contenuto'
    if max_desc and len(rt) > max_desc:
        rt = rt[:max_desc].rstrip() + '…'
    clean = clean_title(rt, info.get('uploader') or info.get('channel')) or rt

    lines = [
        f"{icons['main']} {cfg['b'](f'{label} da:')} {detect_platform(url)}",
        f"{icons['user']} {cfg['b'](f'{label} {inviato} da:')} {sender}",
        f"{icons['link']} {cfg['b']('Link originale:')} {cfg['wrap'](url)}",
        f"{icons['meta']} {cfg['b']('Info:')} {cfg['esc'](clean)}",
    ]
    meta = meta_line(info, clean, cfg['esc'])
    if meta:
        lines.append(f"📊 {meta}")
    if invite:
        lines.append(f"💬 {cfg['i'](INVITE_TEXT)}")
    return "\n".join(lines)

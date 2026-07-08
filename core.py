#!/usr/bin/env python3
"""Nucleo condiviso dai vari frontend (Telegram / Discord / WhatsApp).

Tiene in UN SOLO posto la logica che prima era duplicata in bot.py, discord_bot.py
e wa_bridge.py: rilevamento piattaforma, helper di formattazione e — soprattutto —
la costruzione della didascalia, con un parametro `dialect` per rendere il testo
nel formato giusto (HTML per Telegram, markdown Discord, markdown WhatsApp).

Così una modifica alla didascalia si fa una volta sola. I frontend passano solo le
parti che li distinguono (mittente già renderizzato, icone, se mostrare l'invito).
"""

import os
from urllib.parse import urlparse
from html import escape as _html_escape

VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.flv', '.ts')

# --- Link "scarica audio" servito dal web server del bot su /a/<token> ---
# Così l'audio è un semplice link accorciato che funziona su Telegram, Discord e
# WhatsApp (niente più bottone inline, che i caroselli non supportavano).
AUDIO_BASE = (os.getenv('PUBLIC_URL') or os.getenv('RENDER_EXTERNAL_URL')
              or 'https://nello-9amr.onrender.com').rstrip('/')
_LINK_BASE = f"{AUDIO_BASE}/l"
_AUDIO_BASE = f"{AUDIO_BASE}/a"
_PLAY_BASE = f"{AUDIO_BASE}/p"
_audio_links = {}      # token -> url originale
_audio_counter = [0]
_play_links = {}       # token -> url originale (stream preview audio)
_play_counter = [0]


def audio_link_for(url: str):
    """Registra l'url e ritorna il link corto '{base}/a/<token>' da mettere
    nella card. Il web server, quando lo apri, scarica e serve l'audio."""
    if not _AUDIO_BASE or not url:
        return None
    _audio_counter[0] = (_audio_counter[0] + 1) % 1_000_000
    tok = format(_audio_counter[0], 'x')
    _audio_links[tok] = url
    if len(_audio_links) > 4000:  # prune semplice
        for k in list(_audio_links)[:2000]:
            _audio_links.pop(k, None)
    return f"{_AUDIO_BASE}/{tok}"


def audio_url_by_token(tok: str):
    return _audio_links.get(tok)


def play_link_for(url: str):
    if not _PLAY_BASE or not url:
        return None
    _play_counter[0] = (_play_counter[0] + 1) % 1_000_000
    tok = format(_play_counter[0], 'x')
    _play_links[tok] = url
    if len(_play_links) > 4000:
        for k in list(_play_links)[:2000]:
            _play_links.pop(k, None)
    return f"{_PLAY_BASE}/{tok}"


def play_url_by_token(tok: str):
    return _play_links.get(tok)


# --- Accorciatore link interno: '{base}/l/<token>' -> redirect all'originale ---
# Usato su WhatsApp, dove non esistono i link con testo ("apri originale") e gli
# URL lunghi dei post intasano la card.
_short_links = {}
_short_counter = [0]


def short_link_for(url: str):
    if not _LINK_BASE or not url:
        return None
    _short_counter[0] = (_short_counter[0] + 1) % 1_000_000
    tok = format(_short_counter[0], 'x')
    _short_links[tok] = url
    if len(_short_links) > 4000:
        for k in list(_short_links)[:2000]:
            _short_links.pop(k, None)
    return f"{_LINK_BASE}/{tok}"


def link_url_by_token(tok: str):
    return _short_links.get(tok)

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
    # 'collapse': rende la descrizione lunga COMPATTA (tap per espandere). Telegram usa
    # il blockquote espandibile (collassato a ~3 righe); Discord lo spoiler. WhatsApp no.
    'html':     {'b': lambda s: f"<b>{s}</b>", 'i': lambda s: f"<i>{s}</i>",
                 'esc': _html_escape, 'wrap': lambda u: _html_escape(u),
                 'collapse': lambda s: f"<blockquote expandable>{s}</blockquote>"},
    'discord':  {'b': lambda s: f"**{s}**",    'i': lambda s: f"*{s}*",
                 'esc': lambda s: s,           'wrap': lambda u: f"<{u}>",
                 'collapse': lambda s: f"||{s}||"},
    'whatsapp': {'b': lambda s: f"*{s}*",      'i': lambda s: f"_{s}_",
                 'esc': lambda s: s,           'wrap': lambda u: u},  # niente collapse
}

INVITE_TEXT = "Reagisci con un'emoji per votare il post!"
# Sopra questa lunghezza, la descrizione di FOTO/caroselli va "collassata".
SPOILER_MIN_LEN = 120


def short_url(url: str) -> str:
    """URL corto da mostrare nella card.
    - Telegram: usa sempre il testo 'apri originale' (gestito fuori da qui).
    - Discord / WhatsApp: usa SEMPRE il redirect interno /l/<token> in stile bitly,
      così la card non mostra mai URL lunghi o parametri di tracking.
    """
    return short_link_for(url) or url


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
    incollano dentro: prefisso 'NN views · NN reactions |', suffisso '| Autore' e
    gli hashtag (#meme #sindaco... non dicono nulla, allungano solo la card)."""
    if not raw:
        return raw
    import re
    t = raw
    t = re.sub(r'^\s*[\d.,]+\s*[KMB]?\s*views?\b.*?\|\s*', '', t, flags=re.IGNORECASE)
    if uploader and str(uploader).lower() not in ('sconosciuto', 'none', ''):
        t = re.sub(r'\s*\|\s*' + re.escape(str(uploader)) + r'\s*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'#[^\s#]+', '', t)          # via gli hashtag
    t = re.sub(r'[ \t]{2,}', ' ', t)        # spazi doppi rimasti
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

    # Link accorciato: su Telegram come testo cliccabile "apri originale" (nasconde
    # l'URL lungo); su Discord/WhatsApp l'URL senza i parametri di tracking.
    if dialect == 'html':
        link_part = f'<a href="{_html_escape(url)}">apri originale</a>'
    else:
        link_part = cfg['wrap'](short_url(url))

    lines = [
        f"{icons['main']} {cfg['b'](f'{label} da:')} {detect_platform(url)}",
        f"{icons['user']} {cfg['b'](f'{label} {inviato} da:')} {sender}",
        f"{icons['link']} {cfg['b']('Link:')} {link_part}",
    ]

    # Info: descrizione lunga COMPATTA (tap per espandere) su Telegram (blockquote
    # espandibile) e Discord (spoiler); WhatsApp non ha collapse -> anteprima corta.
    collapse = cfg.get('collapse')
    if len(clean) > SPOILER_MIN_LEN:
        if collapse:
            lines.append(f"{icons['meta']} {cfg['b']('Info:')}\n{collapse(cfg['esc'](clean))}")
        else:
            preview = clean[:140].rstrip()
            lines.append(f"{icons['meta']} {cfg['b']('Info:')} {cfg['esc'](preview)}…")
    else:
        lines.append(f"{icons['meta']} {cfg['b']('Info:')} {cfg['esc'](clean)}")

    # Link "scarica audio": per i video e le slideshow TikTok (che hanno la musica).
    show_audio = (label == 'Video') or (label in ('Foto', 'Contenuto') and detect_platform(url) == 'TikTok')
    if show_audio:
        au = audio_link_for(url)
        pl = play_link_for(url)
        if au and pl:
            if dialect == 'html':
                lines.append(
                    f'🎵 <a href="{_html_escape(pl)}">▶️ ascolta</a> · '
                    f'<a href="{_html_escape(au)}">⬇️ audio</a>'
                )
            else:
                lines.append(f"🎵 ▶️ ascolta: {cfg['wrap'](pl)} · ⬇️ audio: {cfg['wrap'](au)}")

    # Niente riga 📊 (durata/views/like/autore) e niente invito: card pulita.
    return "\n".join(lines)

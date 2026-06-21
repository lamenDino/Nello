#!/usr/bin/env python3
"""
Telegram Multi-Platform Video Downloader Bot v3.4
- Retry silenzioso totale
- Supporto VIDEO + CAROSELLO FOTO (album unico via media_group)
- Ranking settimanale TOP 3 con badge
- Messaggio automatico ogni sabato ore 20:00 (Europe/Rome)
"""

import os
import logging
import threading
import asyncio
import random
import pytz
from datetime import time, datetime, timedelta
from collections import defaultdict

from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.helpers import escape
from telegram import InputMediaPhoto, InputMediaVideo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    MessageReactionHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest
from dotenv import load_dotenv
from social_downloader import SocialMediaDownloader
from ranking_store import get_ranking_store

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "8080"))

GROUP_CHAT_ID = int(os.getenv('CHAT_ID') or os.getenv('GROUP_CHAT_ID') or '214193849')

# Admin a cui mandare gli avvisi (es. cookie scaduti). Default: GROUP_CHAT_ID.
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID') or '0') or GROUP_CHAT_ID

# Credenziali Render (opzionali): abilitano /setcookies persistente e l'auto-redeploy
RENDER_API_KEY = os.getenv('RENDER_API_KEY')
RENDER_SERVICE_ID = os.getenv('RENDER_SERVICE_ID')

# Mappa piattaforma -> (attributo cookie del downloader, nome secret file su Render)
COOKIE_TARGETS = {
    'youtube': ('youtube_cookies', 'YOUTUBE_COOKIES'),
    'instagram': ('instagram_cookies', 'INSTAGRAM_COOKIES'),
    'tiktok': ('tiktok_cookies', 'TIKTOK_COOKIES'),
    'facebook': ('facebook_cookies', 'FACEBOOK_COOKIES'),
}

# Limite di upload della Bot API di Telegram (50MB per i bot standard)
TELEGRAM_MAX_BYTES = 50 * 1024 * 1024

# Timeout complessivo per un singolo download (oltre, si molla e si avvisa l'utente)
DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', '150'))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# Sicurezza: httpx logga l'URL completo delle richieste, che contiene il TOKEN del bot.
# Alzo il livello a WARNING per non scriverlo nei log.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# =========================
# RANKING
# =========================

# Storage del ranking: Firebase Firestore se configurato, altrimenti file JSON locale.
# Il path JSON e' usato solo come fallback (vedi ranking_store.py).
_RANKING_JSON_FALLBACK = os.getenv('RANKING_FILE', os.path.join(os.path.dirname(__file__), 'ranking_data.json'))
ranking_store = get_ranking_store(_RANKING_JSON_FALLBACK)

BADGES = ["🥇", "🥈", "🥉"]

AFORISMI = [
    "La costanza batte il talento quando il talento dorme.",
    "Chi fa ogni giorno qualcosa, arriva sempre lontano.",
    "Il successo è la somma di piccoli sforzi ripetuti.",
    "Non esistono scorciatoie che valgano più del percorso.",
    "La disciplina oggi è la libertà di domani.",
    "Cadi sette volte, rialzati otto.",
    "Il momento migliore per iniziare era ieri. Il secondo migliore è adesso.",
    "Le grandi imprese nascono da piccoli passi quotidiani.",
    "Non contare i giorni, fai in modo che i giorni contino.",
    "La fatica di oggi è la forza di domani.",
    "Chi smette di migliorare ha smesso di essere bravo.",
    "I sogni non funzionano se non lavori anche tu.",
    "Un po' ogni giorno batte tanto una volta sola.",
    "La motivazione ti fa partire, l'abitudine ti fa continuare.",
    "Non aspettare l'occasione perfetta: creala.",
    "Il talento apre la porta, la costanza la tiene aperta.",
    "Ogni esperto è stato prima un principiante testardo.",
    "Vinci la pigrizia una scelta alla volta."
]

FUNNY_SOURCES = [
    "https://www.tiktok.com/@stefano_cattivero",
    "https://www.tiktok.com/@funnycat_2024",
    "https://www.tiktok.com/@cat_lovers_2024",
    "https://www.tiktok.com/@cute_cats_videos"
]

NELLO_ERRORS = [
    "🐶 <b>Nello ci ha provato, ma le sue anche hanno fatto cilecca!</b>",
    "🦴 <b>Nello si è distratto a leccarsi una zampa e ha perso il link (ha 11 anni, capiscilo).</b>",
    "🐾 <b>Nello dice che è troppo vecchio per correre dietro a questo video!</b>",
    "🦿 <b>Le gambe di Nello cigolano oggi... Impossibile scaricare.</b>",
    "💊 <b>Nello deve prendere le medicine per i reni, torna dopo!</b>",
    "🐕 <b>Nello è andato dal veterinario, il download deve aspettare.</b>",
    "🚑 <b>Nello è inciampato mentre portava il file... colpa dell'artrosi!</b>",
    "😴 <b>Nello si è addormentato sulla tastiera. Vecchiaia portami via...</b>",
    "🛁 <b>Nello sta facendo i fanghi per i dolori, riprova dopo!</b>"
]

# =========================
# UTILS
# =========================

# Downloader condiviso (istanziato una sola volta: evita di ricreare l'oggetto
# e di rilanciare il log della versione yt-dlp ad ogni messaggio)
_downloader = None


def get_downloader() -> SocialMediaDownloader:
    global _downloader
    if _downloader is None:
        _downloader = SocialMediaDownloader(debug=os.getenv('SMD_DEBUG', '0') == '1')
    return _downloader


def is_supported_link(url: str) -> bool:
    is_supported = any(d in url for d in [
        "tiktok.com", "instagram.com", "facebook.com", "fb.watch",
        "youtube.com", "youtu.be", "twitter.com", "x.com",
        "reddit.com", "redd.it", "twitch.tv",
    ])

    if not is_supported:
        return False

    # YouTube: accettiamo tutti i video, ma quelli > 3 min vengono lasciati come link
    # in chat (il controllo durata è gestito nel downloader -> 'skip_long').
    return True

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

# =========================
# DIDASCALIA (caption)
# =========================

# Pool di icone "vivaci" pescate a caso a ogni invio, così la didascalia cambia sempre.
ICONS_VIDEO = ["🎬", "📹", "🎥", "🍿", "📺", "🎞️", "🕹️", "📀", "🎦"]
ICONS_FOTO = ["📸", "🖼️", "📷", "🌄", "🏞️", "🎨", "🪄", "🖌️", "🌟"]
ICONS_USER = ["👤", "🙋", "😎", "🤙", "🫶", "🧑‍💻", "🦸", "🥷", "👑", "🤩"]
ICONS_LINK = ["🔗", "🌐", "📎", "🧷", "➡️", "🪢", "📡"]
ICONS_META = ["📝", "💬", "🗒️", "✨", "💭", "📌", "🧠", "🔎"]

VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.flv', '.ts')


def media_label(info: dict) -> str:
    """Ritorna 'Video', 'Foto' o 'Contenuto' in base a cosa si sta inviando davvero."""
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


def _clean_title(raw: str, uploader: str = None) -> str:
    """Ripulisce il titolo da info ridondanti che alcune piattaforme (es. Facebook)
    incollano dentro: prefisso 'NN views · NN reactions |' e suffisso '| Autore'."""
    if not raw:
        return raw
    import re
    t = raw
    # Prefisso tipo "69K views · 832 reactions | ..." (Facebook)
    t = re.sub(r'^\s*[\d.,]+\s*[KMB]?\s*views?\b.*?\|\s*', '', t, flags=re.IGNORECASE)
    # Suffisso "| Autore" se coincide con l'uploader (evita di ripeterlo)
    if uploader and str(uploader).lower() not in ('sconosciuto', 'none', ''):
        t = re.sub(r'\s*\|\s*' + re.escape(str(uploader)) + r'\s*$', '', t, flags=re.IGNORECASE)
    return t.strip(' |\n')


def _meta_line(info: dict, title: str = '') -> str:
    """Riga opzionale con durata/views/like/autore, se disponibili.
    Salta l'autore se già presente nel titolo (per non ripeterlo)."""
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
            bits.append(f"✍️ {escape(str(up)[:40])}")
    return "  ".join(bits)


def build_caption(info: dict, url: str, sender_name: str, raw_title: str, sender_id: int = None) -> str:
    """Didascalia adattiva (Foto/Video/Contenuto) con icone casuali e accordo grammaticale."""
    label = media_label(info)
    inviato = "inviata" if label == "Foto" else "inviato"
    icon_main = random.choice(ICONS_FOTO if label == "Foto" else ICONS_VIDEO)
    # Menzione cliccabile del mittente (notifica e link al profilo)
    if sender_id:
        sender = f'<a href="tg://user?id={sender_id}">{escape(sender_name)}</a>'
    else:
        sender = escape(sender_name)
    clean_title = _clean_title(raw_title, info.get('uploader') or info.get('channel')) or raw_title
    caption = (
        f"{icon_main} <b>{label} da:</b> {detect_platform(url)}\n"
        f"{random.choice(ICONS_USER)} <b>{label} {inviato} da:</b> {sender}\n"
        f"{random.choice(ICONS_LINK)} <b>Link originale:</b> {escape(url)}\n"
        f"{random.choice(ICONS_META)} <b>Info:</b> {escape(clean_title)}"
    )
    meta = _meta_line(info, clean_title)
    if meta:
        caption += f"\n📊 {meta}"
    return caption

# =========================
# CACHE file_id (rinvio istantaneo)
# =========================

def _fid_from_msg(m):
    """Estrae (tipo, file_id) da un Message inviato."""
    if getattr(m, 'video', None):
        return ('video', m.video.file_id)
    if getattr(m, 'photo', None):
        return ('photo', m.photo[-1].file_id)
    if getattr(m, 'animation', None):
        return ('animation', m.animation.file_id)
    if getattr(m, 'document', None):
        return ('document', m.document.file_id)
    return None


def build_cache_payload(captured: list, platform: str, title: str) -> dict:
    """captured = lista di (tipo, file_id). Costruisce il payload da mettere in cache."""
    if not captured:
        return None
    if len(captured) == 1:
        t, fid = captured[0]
        return {'kind': t, 'fid': fid, 'platform': platform, 'title': title}
    return {'kind': 'carousel', 'platform': platform, 'title': title,
            'items': [{'t': t, 'fid': fid} for t, fid in captured]}


async def resend_from_cache(context, msg, cached: dict, url: str) -> bool:
    """Rinvia un media gia' caricato usando il file_id (nessun download). True se riuscito."""
    sender = f'<a href="tg://user?id={msg.from_user.id}">{escape(msg.from_user.full_name)}</a>'
    caption = (
        f"♻️ <b>Ripescato dalla cache</b> (già postato)\n"
        f"{random.choice(ICONS_USER)} <b>Rimesso da:</b> {sender}\n"
        f"{random.choice(ICONS_LINK)} <b>Link:</b> {escape(url)}"
    )
    try:
        kind = cached.get('kind')
        if kind == 'video':
            _m = await context.bot.send_video(
                chat_id=msg.chat_id, video=cached['fid'],
                caption=caption + "\n💬 <i>Reagisci con un'emoji per votarlo!</i>",
                parse_mode=ParseMode.HTML, reply_markup=audio_only_keyboard(url))
            try:
                await ranking_store.create_vote(f"{_m.chat_id}:{_m.message_id}", msg.from_user.id,
                                                msg.from_user.full_name, fid=cached['fid'])
            except Exception:
                pass
        elif kind in ('photo', 'animation', 'document'):
            send = {'photo': context.bot.send_photo, 'animation': context.bot.send_animation,
                    'document': context.bot.send_document}[kind]
            kw = {'photo': 'photo', 'animation': 'animation', 'document': 'document'}[kind]
            await send(chat_id=msg.chat_id, caption=caption, parse_mode=ParseMode.HTML,
                       **{kw: cached['fid']})
        elif kind == 'carousel':
            items = cached.get('items', [])
            media = []
            for idx, it in enumerate(items[:10]):
                cap = caption if idx == 0 else None
                if it.get('t') == 'video':
                    media.append(InputMediaVideo(media=it['fid'], caption=cap, parse_mode=ParseMode.HTML))
                else:
                    media.append(InputMediaPhoto(media=it['fid'], caption=cap, parse_mode=ParseMode.HTML))
            if not media:
                return False
            await context.bot.send_media_group(chat_id=msg.chat_id, media=media)
        else:
            return False
        return True
    except Exception as e:
        logger.warning(f"Resend da cache fallito ({url}): {e}")
        return False


# =========================
# BOTTONI INLINE (Audio / Elimina)
# =========================

# Mappa token->url per i callback (callback_data ha un limite di 64 byte, non ci
# sta un URL). In memoria, capped; se il bot riparte i vecchi bottoni scadono.
_cb_links = {}
_cb_counter = [0]


def register_cb_url(url: str) -> str:
    _cb_counter[0] = (_cb_counter[0] + 1) % 1_000_000
    token = str(_cb_counter[0])
    _cb_links[token] = url
    if len(_cb_links) > 2000:  # prune semplice
        for k in list(_cb_links.keys())[:1000]:
            _cb_links.pop(k, None)
    return token


# Reazioni disponibili (l'indice è usato nel callback_data per stare nei 64 byte).
# NB: aggiungere SOLO in coda, per non sfasare i callback dei messaggi vecchi.
REACTIONS = ['👍', '😂', '🔥', '😍', '😭', '🤮']
AUDIO_BTN_TEXT = "🎵 Scarica audio"
VOTER_ACH_AT = 25  # reazioni date per sbloccare "Votante attivo"


def new_vote_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


def _react_label(emoji: str, count: int) -> str:
    return f"{emoji} {count}" if count else emoji


def _reaction_rows(vote_id: str, counts: dict = None):
    """Bottoni reazione disposti su righe da 3 (per non stringerli troppo)."""
    counts = counts or {}
    btns = [InlineKeyboardButton(_react_label(e, counts.get(e, 0)), callback_data=f"r:{vote_id}:{i}")
            for i, e in enumerate(REACTIONS)]
    return [btns[i:i + 3] for i in range(0, len(btns), 3)]


def audio_only_keyboard(url: str) -> InlineKeyboardMarkup:
    """Solo il bottone 'Scarica audio'. Il voto avviene con le reazioni native."""
    token = register_cb_url(url)
    return InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_BTN_TEXT, callback_data=f"a:{token}")]])


def reaction_keyboard(url: str, vote_id: str, counts: dict = None) -> InlineKeyboardMarkup:
    """Tastiera sotto al video: riga Audio + righe reazioni (LEGACY, non più usata:
    ora il voto è tramite reazioni native di Telegram)."""
    token = register_cb_url(url)
    rows = [[InlineKeyboardButton(AUDIO_BTN_TEXT, callback_data=f"a:{token}")]]
    rows += _reaction_rows(vote_id, counts)
    return InlineKeyboardMarkup(rows)


def reaction_only_keyboard(vote_id: str, counts: dict = None) -> InlineKeyboardMarkup:
    """Solo reazioni (per i caroselli: i media_group non accettano bottoni inline)."""
    return InlineKeyboardMarkup(_reaction_rows(vote_id, counts))


def rebuild_reaction_markup(audio_cb: str, vote_id: str, counts: dict) -> InlineKeyboardMarkup:
    rows = []
    if audio_cb:
        rows.append([InlineKeyboardButton(AUDIO_BTN_TEXT, callback_data=audio_cb)])
    rows += _reaction_rows(vote_id, counts)
    return InlineKeyboardMarkup(rows)


async def on_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Voto tramite reazioni native di Telegram. Richiede che il bot sia admin nel
    gruppo e che message_reaction sia tra gli allowed_updates."""
    mr = update.message_reaction
    if not mr or not mr.user:   # ignora reazioni anonime / aggiornamenti di conteggio
        return
    key = f"{mr.chat.id}:{mr.message_id}"
    emojis = [getattr(rt, 'emoji', None) or '⭐' for rt in (mr.new_reaction or [])]
    try:
        res = await ranking_store.set_reaction(key, mr.user.id, emojis)
    except Exception as e:
        logger.warning(f"set_reaction fallito: {e}")
        return
    if not res or res.get('self'):
        return

    if res.get('milestone'):
        try:
            owner_m = f'<a href="tg://user?id={res["owner"]}">{escape(res["name"])}</a>'
            await context.bot.send_message(
                mr.chat.id,
                f"🔥 Il video di {owner_m} ha raggiunto <b>{res['milestone']}</b> voti! 🎉",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    if res.get('added') and res.get('voter_total') == VOTER_ACH_AT:
        try:
            await ranking_store.add_earned(mr.user.id, 'voter')
            vm = f'<a href="tg://user?id={mr.user.id}">{escape(mr.user.first_name)}</a>'
            await context.bot.send_message(
                mr.chat.id,
                f"🎉 {vm} ha sbloccato un achievement!\n{ACHIEVEMENTS.get('voter')}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""

    if data.startswith("r:"):
        try:
            _, vote_id, idx = data.split(":")
            emoji = REACTIONS[int(idx)]
        except (ValueError, IndexError):
            await q.answer()
            return
        try:
            res = await ranking_store.toggle_reaction(vote_id, q.from_user.id, emoji)
        except Exception as e:
            logger.warning(f"toggle_reaction fallito: {e}")
            await q.answer("Reazione non riuscita, riprova.", show_alert=True)
            return
        if res is None:
            await q.answer("Questo video è troppo vecchio per reagire 🙈", show_alert=True)
            return
        if res.get('self'):
            await q.answer("Non puoi votare il tuo stesso video 😄", show_alert=True)
            return
        # Aggiorna i contatori sui bottoni, mantenendo il bottone Audio
        try:
            audio_cb = None
            rows = q.message.reply_markup.inline_keyboard if (q.message and q.message.reply_markup) else []
            for row in rows:
                for b in row:
                    if b.callback_data and b.callback_data.startswith('a:'):
                        audio_cb = b.callback_data
            await q.edit_message_reply_markup(rebuild_reaction_markup(audio_cb, vote_id, res.get('counts', {})))
        except Exception:
            pass
        await q.answer("✅" if res.get('added') else "Aggiornato")

        # Notifica traguardo
        if res.get('milestone'):
            try:
                owner_m = f'<a href="tg://user?id={res["owner"]}">{escape(res["name"])}</a>'
                await context.bot.send_message(
                    q.message.chat_id,
                    f"🔥 Il video di {owner_m} ha raggiunto <b>{res['milestone']}</b> reazioni! 🎉",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

        # Achievement "Votante attivo" per chi vota tanto
        if res.get('added') and res.get('voter_total') == VOTER_ACH_AT:
            try:
                await ranking_store.add_earned(q.from_user.id, 'voter')
                voter_m = f'<a href="tg://user?id={q.from_user.id}">{escape(q.from_user.first_name)}</a>'
                await context.bot.send_message(
                    q.message.chat_id,
                    f"🎉 {voter_m} ha sbloccato un achievement!\n{ACHIEVEMENTS.get('voter')}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        return

    if data.startswith("a:"):
        url = _cb_links.get(data[2:])
        if not url:
            await q.answer("Bottone scaduto, rimanda il link 🙏", show_alert=True)
            return
        await q.answer("🎵 Estraggo l'audio, un attimo...")
        loading = await context.bot.send_message(q.message.chat_id, "🎵 Estraggo l'audio...")
        try:
            info = await get_downloader().download_audio(url)
            if info and info.get("success"):
                path = info["file_path"]
                if os.path.getsize(path) > TELEGRAM_MAX_BYTES:
                    await context.bot.send_message(q.message.chat_id, "🐘 Audio troppo grande per Telegram (>50MB).")
                else:
                    with open(path, "rb") as f:
                        await context.bot.send_audio(
                            chat_id=q.message.chat_id, audio=f,
                            title=info.get("title"), performer=info.get("uploader"),
                        )
                try:
                    os.remove(path)
                except Exception:
                    pass
            else:
                await context.bot.send_message(q.message.chat_id, "⚠️ Non riesco a estrarre l'audio da questo link.")
        except Exception as e:
            logger.warning(f"Callback audio error: {e}")
            await context.bot.send_message(q.message.chat_id, "⚠️ Errore nell'estrazione audio.")
        finally:
            try:
                await loading.delete()
            except Exception:
                pass


# =========================
# DEDUP / RATE LIMIT / ACHIEVEMENT
# =========================

def link_key(url: str) -> str:
    """Chiave normalizzata di un link (per 'gia' postato'): host+path senza query."""
    u = url.strip().lower().split('?')[0].split('#')[0]
    u = u.replace('https://', '').replace('http://', '').replace('www.', '')
    return u.rstrip('/')


# Rate limit anti-spam: max N download/ora per utente (in memoria, si azzera ai restart)
RATE_MAX_PER_HOUR = int(os.getenv('RATE_MAX_PER_HOUR', '20'))
_rate_hits = defaultdict(list)


def rate_limited(user_id: int) -> bool:
    import time as _t
    now = _t.time()
    hits = [t for t in _rate_hits[user_id] if now - t < 3600]
    _rate_hits[user_id] = hits
    if len(hits) >= RATE_MAX_PER_HOUR:
        return True
    hits.append(now)
    return False


# Achievement: codice -> (emoji+testo). I milestone numerici sono gestiti a parte.
ACHIEVEMENTS = {
    'm10': '🥉 <b>10 contenuti!</b> Ti stai scaldando.',
    'm50': '🥈 <b>50 contenuti!</b> Un veterano.',
    'm100': '🥇 <b>100 contenuti!</b> Leggenda del gruppo.',
    'm250': '🏆 <b>250 contenuti!</b> Inarrestabile.',
    'm500': '💎 <b>500 contenuti!</b> Macchina da download.',
    'm1000': '👑 <b>1000 contenuti!</b> Il Re assoluto.',
    'night': '🦉 <b>Nottambulo!</b> Download nel cuore della notte.',
    'voter': '🗳️ <b>Votante attivo!</b> Hai messo un sacco di reazioni.',
}

# Ranghi/titoli in base ai contenuti totali (all-time)
RANKS = [
    (0, '🐣', 'Novizio'),
    (10, '🎬', 'Habitué'),
    (50, '🏅', 'Veterano'),
    (100, '🔥', 'Esperto'),
    (250, '💎', 'Maestro'),
    (500, '🦅', 'Leggenda'),
    (1000, '👑', 'Re del gruppo'),
]


def get_rank(alltime: int):
    """Ritorna (emoji, titolo) del rango raggiunto."""
    emoji, title = RANKS[0][1], RANKS[0][2]
    for thr, e, t in RANKS:
        if alltime >= thr:
            emoji, title = e, t
    return emoji, title


def next_rank(alltime: int):
    """Ritorna (soglia, emoji, titolo) del prossimo rango, o None se al massimo."""
    for thr, e, t in RANKS:
        if alltime < thr:
            return thr, e, t
    return None


def newly_earned(totals: dict, already: set) -> list:
    """Ritorna i codici achievement appena sbloccati (non in `already`)."""
    earned = []
    alltime = totals.get('alltime', 0)
    for threshold, code in [(10, 'm10'), (50, 'm50'), (100, 'm100'),
                            (250, 'm250'), (500, 'm500'), (1000, 'm1000')]:
        if alltime >= threshold and code not in already:
            earned.append(code)
    hour = datetime.now(pytz.timezone('Europe/Rome')).hour if pytz else datetime.now().hour
    if 2 <= hour < 5 and 'night' not in already:
        earned.append('night')
    return earned


# Avviso admin: se una piattaforma fallisce ripetutamente, probabilmente i cookie
# sono scaduti. Conta i fallimenti consecutivi per piattaforma e avvisa l'admin
# al massimo una volta all'ora per piattaforma.
_fail_streak = defaultdict(int)
_last_alert = {}
FAIL_ALERT_THRESHOLD = 3


async def note_download_failure(platform: str, context):
    import time as _t
    _fail_streak[platform] += 1
    if _fail_streak[platform] < FAIL_ALERT_THRESHOLD:
        return
    now = _t.time()
    if now - _last_alert.get(platform, 0) < 3600:
        return
    _last_alert[platform] = now
    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=(
                f"⚠️ <b>Attenzione admin</b>\n"
                f"{platform} ha fallito {_fail_streak[platform]} download di fila.\n"
                f"Probabile causa: <b>cookie {platform} scaduti</b>. "
                f"Rigenera ed aggiorna il secret file su Render."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


def note_download_success(platform: str):
    _fail_streak[platform] = 0


# =========================
# COMMANDS
# =========================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received /start in chat {update.effective_chat.id} from {update.effective_user.id}")
    await update.message.reply_text(
        "Ciao! Mandami un link da TikTok, Instagram, Facebook, YouTube Shorts, "
        "Twitter/X, Reddit o Twitch e penso io a tutto 🔥\n\n"
        "<b>Comandi:</b>\n"
        "• /classifica — top download della settimana\n"
        "• /votati — video più amati (reazioni)\n"
        "• /mensile — top del mese\n"
        "• /record — albo d'oro all-time\n"
        "• /profilo — la tua card (rango, medaglie…)\n"
        "• /stats — le tue statistiche\n\n"
        f"Chat ID di questo gruppo: <code>{update.effective_chat.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def resolve_user_name(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    """Risolve il nome pubblico di un utente dal suo id (best effort)."""
    try:
        chat = await context.bot.get_chat(user_id)
        return chat.full_name or getattr(chat, 'first_name', None) or 'Utente'
    except Exception:
        return 'Utente'


async def _render_board(period: str, titolo: str, vuoto: str, update):
    try:
        board = await ranking_store.get_board(period, limit=10)
    except Exception as e:
        logger.warning(f"get_board fallito: {e}")
        await update.message.reply_text("⚠️ Classifica non disponibile: il database non è raggiungibile.")
        return
    if not board:
        await update.message.reply_text(vuoto)
        return
    text = f"{titolo}\n\n"
    for i, (user_id, count, name) in enumerate(board):
        badge = BADGES[i] if i < len(BADGES) else f"<b>{i + 1}.</b>"
        mention = f'<a href="tg://user?id={user_id}">{escape(name)}</a>'
        text += f"{badge} {mention} — <b>{count}</b>\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                    disable_web_page_preview=True)


async def classifica_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Classifica settimanale live (non azzera)."""
    await _render_board('weekly', "🏆 <b>CLASSIFICA SETTIMANALE</b>",
                        "📭 Nessun contenuto questa settimana. Mandane uno! 🐶", update)


async def mensile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Classifica del mese."""
    await _render_board('monthly', "📅 <b>CLASSIFICA DEL MESE</b>",
                        "📭 Nessun contenuto questo mese.", update)


async def record_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Classifica all-time."""
    await _render_board('alltime', "🏛️ <b>ALBO D'ORO (ALL-TIME)</b>",
                        "📭 Ancora nessun contenuto. La storia inizia ora!", update)


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistiche personali dell'utente."""
    u = update.effective_user
    try:
        s = await ranking_store.get_user_stats(u.id)
        earned = await ranking_store.get_earned(u.id)
    except Exception as e:
        logger.warning(f"stats fallito: {e}")
        await update.message.reply_text("⚠️ Statistiche non disponibili: il database non è raggiungibile.")
        return
    rank_txt = f"#{s['rank']} su {s['total_users']}" if s.get('rank') else "—"
    badges = " ".join(ACHIEVEMENTS.get(c, "🏅").split()[0] for c in earned) or "nessuno ancora"
    r_emoji, r_title = get_rank(s['alltime'])
    text = (
        f"📊 <b>Le tue statistiche, {escape(u.first_name)}</b>\n\n"
        f"{r_emoji} Rango: <b>{r_title}</b>\n"
        f"📆 Questa settimana: <b>{s['weekly']}</b>\n"
        f"🗓️ Questo mese: <b>{s['monthly']}</b>\n"
        f"🏛️ Totale: <b>{s['alltime']}</b>\n"
        f"🥇 Posizione all-time: <b>{rank_txt}</b>\n"
        f"🎖️ Achievement: {badges}\n\n"
        f"ℹ️ Usa /profilo per la card completa."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def profilo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Card profilo: rango, progressione, voti ricevuti, medaglie, miglior video."""
    u = update.effective_user
    try:
        p = await ranking_store.get_profile(u.id)
    except Exception as e:
        logger.warning(f"get_profile fallito: {e}")
        await update.message.reply_text("⚠️ Profilo non disponibile: il database non è raggiungibile.")
        return

    r_emoji, r_title = get_rank(p['alltime'])
    nxt = next_rank(p['alltime'])
    if nxt:
        manca = nxt[0] - p['alltime']
        prog = f"⬆️ Mancano <b>{manca}</b> contenuti per diventare {nxt[1]} <b>{nxt[2]}</b>"
    else:
        prog = "🏆 Hai raggiunto il rango massimo!"

    earned = []
    try:
        earned = await ranking_store.get_earned(u.id)
    except Exception:
        pass
    badges = " ".join(ACHIEVEMENTS.get(c, "🏅").split()[0] for c in earned) or "—"
    rank_txt = f"#{p['rank']} su {p['total_users']}" if p.get('rank') else "—"
    medals = "🏅" * min(int(p.get('medals', 0)), 10) + (f" ×{p['medals']}" if p.get('medals') else " 0")

    text = (
        f"🪪 <b>PROFILO — {escape(u.first_name)}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{r_emoji} <b>{r_title}</b>\n"
        f"{prog}\n\n"
        f"🏛️ Contenuti totali: <b>{p['alltime']}</b>  (pos. {rank_txt})\n"
        f"🗓️ Questo mese: <b>{p['monthly']}</b>   📆 Settimana: <b>{p['weekly']}</b>\n"
        f"👍 Voti ricevuti: <b>{p.get('votes_received', 0)}</b>  (🔥 miglior video: {p.get('best_video', 0)})\n"
        f"🗳️ Reazioni date: <b>{p.get('vote_given', 0)}</b>\n"
        f"🏅 Medaglie del pubblico: {medals}\n"
        f"🎖️ Achievement: {badges}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def votati_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Classifica live dei video più votati (reazioni) della settimana."""
    try:
        board = await ranking_store.top_voted_week(limit=10)
    except Exception as e:
        logger.warning(f"top_voted_week fallito: {e}")
        await update.message.reply_text("⚠️ Classifica voti non disponibile: database non raggiungibile.")
        return
    if not board:
        await update.message.reply_text("📭 Nessun voto questa settimana. Reagite ai video! 👍🔥")
        return
    text = "👍 <b>VIDEO PIÙ AMATI (settimana)</b>\n\n"
    for i, (user_id, count, name) in enumerate(board):
        badge = BADGES[i] if i < len(BADGES) else f"<b>{i + 1}.</b>"
        mention = f'<a href="tg://user?id={user_id}">{escape(name)}</a>'
        text += f"{badge} {mention} — <b>{count}</b> voti\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# =========================
# ADMIN: Render API + cookie via DM + /chats
# =========================

def _render_request(method: str, path: str, body: dict = None):
    """Chiamata all'API di Render (richiede RENDER_API_KEY)."""
    import requests
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}
    url = f"https://api.render.com/v1{path}"
    return requests.request(method, url, headers=headers, json=body, timeout=20)


def render_update_secret(secret_name: str, content: str) -> bool:
    try:
        r = _render_request("PUT", f"/services/{RENDER_SERVICE_ID}/secret-files/{secret_name}",
                            {"content": content})
        return r.status_code in (200, 201)
    except Exception as e:
        logger.warning(f"Render secret update fallito: {e}")
        return False


def render_trigger_deploy() -> bool:
    try:
        r = _render_request("POST", f"/services/{RENDER_SERVICE_ID}/deploys", {})
        return r.status_code in (200, 201)
    except Exception as e:
        logger.warning(f"Render deploy trigger fallito: {e}")
        return False


def _valid_netscape(content: str) -> bool:
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and len(line.split('\t')) >= 7:
            return True
    return False


# Stato: admin -> piattaforma in attesa del file cookie
_pending_cookies = {}


async def setcookies_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: aggiorna i cookie di una piattaforma inviando il file in DM."""
    u = update.effective_user
    if u.id != ADMIN_USER_ID:
        await update.message.reply_text("🔒 Solo l'admin può usare questo comando.")
        return
    args = context.args or []
    plat = args[0].lower() if args else ''
    if plat not in COOKIE_TARGETS:
        await update.message.reply_text(
            "Uso: /setcookies <piattaforma>\n"
            "Piattaforme: youtube, instagram, tiktok, facebook\n"
            "Poi mandami QUI in privato il file .txt dei cookie."
        )
        return
    _pending_cookies[u.id] = plat
    await update.message.reply_text(
        f"📥 Ok, ora mandami il file <b>.txt</b> dei cookie per <b>{plat}</b> (formato Netscape).",
        parse_mode=ParseMode.HTML,
    )


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve il file cookie dall'admin dopo /setcookies."""
    u = update.effective_user
    if not u or u.id != ADMIN_USER_ID or u.id not in _pending_cookies:
        return
    plat = _pending_cookies.pop(u.id)
    attr, secret_name = COOKIE_TARGETS[plat]
    try:
        doc = update.message.document
        f = await context.bot.get_file(doc.file_id)
        content = (await f.download_as_bytearray()).decode('utf-8', 'replace')
    except Exception as e:
        await update.message.reply_text(f"⚠️ Non riesco a leggere il file: {e}")
        return

    if not _valid_netscape(content):
        await update.message.reply_text("⚠️ Non sembra un file cookie Netscape valido (righe con 7 campi separati da TAB).")
        return

    # 1) Effetto immediato: sovrascrive il file cookie usato dal downloader
    immediate = False
    try:
        path = getattr(get_downloader(), attr, None)
        if path:
            with open(path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(content)
            immediate = True
    except Exception as e:
        logger.warning(f"Scrittura cookie live fallita: {e}")

    # 2) Persistenza: aggiorna il secret file su Render (se configurato)
    persisted = False
    if RENDER_API_KEY and RENDER_SERVICE_ID:
        persisted = await asyncio.to_thread(render_update_secret, secret_name, content)

    msg = f"✅ Cookie <b>{plat}</b> aggiornati."
    msg += "\n• Effetto immediato: " + ("sì 🎯" if immediate else "no")
    if RENDER_API_KEY and RENDER_SERVICE_ID:
        msg += "\n• Salvati su Render (persistenti): " + ("sì 💾" if persisted else "no ⚠️")
    else:
        msg += "\n• Persistenza su Render: non configurata (imposta RENDER_API_KEY e RENDER_SERVICE_ID per renderli permanenti)."
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def chats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: mostra in quali chat è usato il bot."""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("🔒 Solo l'admin può usare questo comando.")
        return
    try:
        chats = await ranking_store.get_chats()
    except Exception as e:
        logger.warning(f"get_chats fallito: {e}")
        await update.message.reply_text(
            "⚠️ Database non raggiungibile.\n"
            "Probabile causa: <b>Firestore non abilitato</b> nel progetto Firebase. "
            "Vai su console.firebase.google.com → progetto → <b>Firestore Database → Crea database</b>.",
            parse_mode=ParseMode.HTML,
        )
        return
    if not chats:
        await update.message.reply_text("Nessuna chat registrata ancora.")
        return
    text = f"💬 <b>Chat che usano il bot</b> ({len(chats)})\n\n"
    for c in chats[:30]:
        title = escape(str(c.get('title') or c.get('id')))
        text += f"• {title} — <b>{c.get('count', 0)}</b> download\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def sfida_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: lancia una sfida a tema per la settimana."""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("🔒 Solo l'admin può lanciare una sfida.")
        return
    theme = " ".join(context.args or []).strip()
    if not theme:
        await update.message.reply_text("Uso: <code>/sfida &lt;tema&gt;</code>\nEs: <code>/sfida il video più assurdo</code>", parse_mode=ParseMode.HTML)
        return
    try:
        await ranking_store.set_challenge(theme, update.effective_user.full_name)
    except Exception as e:
        logger.warning(f"set_challenge fallito: {e}")
        await update.message.reply_text("⚠️ Non riesco a salvare la sfida (database).")
        return
    await update.message.reply_text(
        f"🎯 <b>NUOVA SFIDA DELLA SETTIMANA!</b>\n\n«{escape(theme)}»\n\n"
        f"Postate i vostri video e fateli votare con 👍😂🔥😍 — "
        f"il più amato vince la <b>🏅 Medaglia del pubblico</b> sabato sera!",
        parse_mode=ParseMode.HTML,
    )


# =========================
# DOWNLOAD HANDLER
# =========================

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = (msg.text or "").strip()
    
    # 1. Split text into potential URLs (handle support for multiple links)
    potential_urls = text.split()
    valid_urls = [u for u in potential_urls if is_supported_link(u)]

    if not valid_urls:
        return

    # Anti-spam: limite di download/ora per utente
    if rate_limited(msg.from_user.id):
        try:
            await msg.reply_text(
                f"🚦 Ehi {escape(msg.from_user.first_name)}, vai piano! "
                f"Hai raggiunto il limite di {RATE_MAX_PER_HOUR} download nell'ultima ora. Riprova più tardi."
            )
        except Exception:
            pass
        return

    logger.info(f"Received message from {update.effective_user.id} with {len(valid_urls)} valid links")

    # Registra la chat (per /chats)
    try:
        ch = update.effective_chat
        await ranking_store.record_chat(ch.id, ch.title or ch.full_name or str(ch.id))
    except Exception:
        pass

    # Downloader condiviso (singleton)
    dl = get_downloader()

    # Per evitare spam di errori, cancelliamo messaggio originale su primo successo
    original_message_deleted = False

    for i, url in enumerate(valid_urls):
        key = link_key(url)

        # Cache file_id: se il media è già stato caricato, lo rinvio all'istante
        # (niente download, niente cookie bruciati). Nessun punto extra (anti-farm).
        try:
            cached = await ranking_store.get_cached(key)
        except Exception:
            cached = None
        if cached and await resend_from_cache(context, msg, cached, url):
            continue

        # Feedback di caricamento differenziato per link
        count_str = f"({i+1}/{len(valid_urls)})" if len(valid_urls) > 1 else ""
        loading = await context.bot.send_message(
            msg.chat_id, 
            f"⏳ Download in corso {count_str}...\n🔗 {escape(url)}",
            parse_mode=ParseMode.HTML
        )

        try:
            # Timeout complessivo: evita che un download impallato (es. YouTube via
            # Deno/bgutil che si blocca) lasci il bot appeso su "Download in corso".
            try:
                info = await asyncio.wait_for(dl.download_video(url), timeout=DOWNLOAD_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout download ({DOWNLOAD_TIMEOUT}s) per {url}")
                await note_download_failure(detect_platform(url), context)
                try:
                    await context.bot.send_message(
                        chat_id=msg.chat_id,
                        text=f"⏳ <b>Ci ho messo troppo</b> e ho mollato il colpo su questo link. Riprova tra poco.\n(Link: {escape(url)})",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
                try:
                    await loading.delete()
                except Exception:
                    pass
                continue

            # ⏭️ YouTube troppo lungo: lascia il link in chat senza dire nulla
            if info and info.get("skip_long"):
                try:
                    await loading.delete()
                except Exception:
                    pass
                continue

            # ❌ fallimento → informa l'utente e passa al prossimo
            if not info or not info.get("success"):
                nello_joke = random.choice(NELLO_ERRORS)
                specific_error = info.get('error', 'Errore sconosciuto')

                # Traccia il fallimento per avvisare l'admin se è sistematico (cookie scaduti)
                await note_download_failure(detect_platform(url), context)

                try:
                    await context.bot.send_message(
                        chat_id=msg.chat_id,
                        text=f"{nello_joke}\n\n⚠️ <i>{escape(specific_error)}</i>\n(Link: {escape(url)})",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass
                try:
                    await loading.delete()
                except Exception:
                    pass
                continue

            # Controllo dimensione: la Bot API di Telegram rifiuta gli upload > 50MB.
            # Meglio un messaggio chiaro che un errore criptico durante l'invio.
            if info.get("type", "video") == "video":
                candidate_paths = [info.get("file_path")]
            else:
                candidate_paths = info.get("files", []) or []

            oversized = next(
                (p for p in candidate_paths
                 if p and os.path.exists(p) and os.path.getsize(p) > TELEGRAM_MAX_BYTES),
                None
            )
            if oversized:
                size_mb = os.path.getsize(oversized) / (1024 * 1024)
                try:
                    await context.bot.send_message(
                        chat_id=msg.chat_id,
                        text=(
                            f"🐘 <b>Troppo pesante per Nello!</b>\n\n"
                            f"Il file ({size_mb:.0f}MB) supera il limite di 50MB di Telegram "
                            f"per i bot, non posso inviarlo.\n(Link: {escape(url)})"
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
                for p in candidate_paths:
                    try:
                        if p and os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
                try:
                    await loading.delete()
                except Exception:
                    pass
                continue

            # Il punto in classifica viene assegnato SOLO dopo un invio riuscito
            # (vedi sotto): così contiamo i video realmente consegnati nel gruppo,
            # non quelli scaricati ma poi falliti in fase di invio.
            sent_ok = False
            captured = []  # (tipo, file_id) per la cache del rinvio istantaneo
            vote_msg = None  # messaggio su cui si vota (carosello: il primo media)

            # Descrizione: per i caroselli/foto la mostriamo (quasi) tutta — è ciò che fa
            # capire il post. La didascalia Telegram è max ~1024 caratteri, quindi lasciamo
            # margine per le altre righe (piattaforma/mittente/link/info).
            raw_title = info.get('title', 'N/A') or 'Contenuto'
            max_desc = 750 if info.get('type') == 'carousel' else 500
            if len(raw_title) > max_desc:
                raw_title = raw_title[:max_desc].rstrip() + "…"

            caption = build_caption(info, url, msg.from_user.full_name, raw_title, sender_id=msg.from_user.id)

            # =========================
            # INVIO CONTENUTI
            # =========================

            # === VIDEO ===
            if info.get("type", "video") == "video":
                video_caption = caption + "\n💬 <i>Reagisci con un'emoji per votarlo!</i>"
                with open(info["file_path"], "rb") as f:
                    _m = await context.bot.send_video(
                        chat_id=msg.chat_id,
                        video=f,
                        caption=video_caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=audio_only_keyboard(url),
                    )
                sent_ok = True
                _fc = _fid_from_msg(_m)
                if _fc:
                    captured.append(_fc)
                # Rendi il messaggio votabile con le reazioni native (chiave = chat:msg_id)
                try:
                    vkey = f"{_m.chat_id}:{_m.message_id}"
                    await ranking_store.create_vote(
                        vkey, msg.from_user.id, msg.from_user.full_name,
                        fid=(_fc[1] if _fc and _fc[0] == 'video' else None))
                except Exception as e:
                    logger.warning(f"create_vote fallito: {e}")
                try:
                    os.remove(info["file_path"])
                except Exception:
                    pass

            # === CAROSELLO FOTO (ALBUM UNICO) ===
            elif info.get("type") == "carousel":
                files = info.get("files", [])
                if not files:
                    await loading.delete()
                    continue

                # L'invito a reagire va DENTRO la didascalia (niente messaggio separato).
                carousel_caption = caption + "\n💬 <i>Reagisci con un'emoji per votare il post!</i>"

                # Se è un solo file, inviamolo come media singolo
                if len(files) == 1:
                    photo_path = files[0]
                    ext = os.path.splitext(photo_path)[1].lower()
                    is_video = ext in ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.flv', '.ts')

                    try:
                        with open(photo_path, "rb") as f:
                            if is_video:
                                _m = await context.bot.send_video(
                                    chat_id=msg.chat_id,
                                    video=f,
                                    caption=carousel_caption,
                                    parse_mode=ParseMode.HTML
                                )
                            else:
                                _m = await context.bot.send_photo(
                                    chat_id=msg.chat_id,
                                    photo=f,
                                    caption=carousel_caption,
                                    parse_mode=ParseMode.HTML
                                )
                        sent_ok = True
                        vote_msg = _m
                        _fc = _fid_from_msg(_m)
                        if _fc:
                            captured.append(_fc)
                    except Exception as e:
                        err_str = str(e).lower()
                        if 'caption' in err_str and 'too long' in err_str:
                             logger.warning("Caption too long for single item, truncating...")
                             short_caption = carousel_caption[:950] + "..."
                             try:
                                 with open(photo_path, "rb") as f:
                                    if is_video:
                                        _m = await context.bot.send_video(chat_id=msg.chat_id, video=f, caption=short_caption, parse_mode=ParseMode.HTML)
                                    else:
                                        _m = await context.bot.send_photo(chat_id=msg.chat_id, photo=f, caption=short_caption, parse_mode=ParseMode.HTML)
                                 sent_ok = True
                                 vote_msg = _m
                                 _fc = _fid_from_msg(_m)
                                 if _fc:
                                     captured.append(_fc)
                             except Exception as inner_e:
                                 logger.error(f"Error sending single item matching caption retry: {inner_e}")
                                 await context.bot.send_message(msg.chat_id, "⚠️ Errore nell'invio (errore imprevisto).")
                        else:
                            logger.error(f"Error sending single carousel item: {e}")
                            await context.bot.send_message(msg.chat_id, "⚠️ Errore nell'invio del media.")
                    finally:
                         try:
                            os.remove(photo_path)
                         except:
                            pass
                
                else: 
                    # Telegram: max 10 media in un media_group
                    MAX_GROUP = 10
                    chunks = [files[i:i + MAX_GROUP] for i in range(0, len(files), MAX_GROUP)]

                    for chunk_index, chunk in enumerate(chunks):
                        media = []
                        opened = []  # teniamo i file handle aperti finché non inviamo

                        try:
                            for c_i, photo_path in enumerate(chunk):
                                f = open(photo_path, "rb")
                                opened.append((f, photo_path))

                                # Caption solo sul primo media del primo chunk
                                ext = os.path.splitext(photo_path)[1].lower()
                                is_video = ext in ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.flv', '.ts')

                                if chunk_index == 0 and c_i == 0:
                                    if is_video:
                                        media.append(InputMediaVideo(
                                            media=f,
                                            caption=carousel_caption,
                                            parse_mode=ParseMode.HTML
                                        ))
                                    else:
                                        media.append(InputMediaPhoto(
                                            media=f,
                                            caption=carousel_caption,
                                            parse_mode=ParseMode.HTML
                                        ))
                                else:
                                    if is_video:
                                        media.append(InputMediaVideo(media=f))
                                    else:
                                        media.append(InputMediaPhoto(media=f))

                            try:
                                _sent = await context.bot.send_media_group(
                                    chat_id=msg.chat_id,
                                    media=media
                                )
                                sent_ok = True
                                if chunk_index == 0 and _sent:
                                    vote_msg = _sent[0]  # si vota reagendo al primo media
                                for _sm in (_sent or []):
                                    _fc = _fid_from_msg(_sm)
                                    if _fc:
                                        captured.append(_fc)
                            except Exception as e:
                               # Handle "caption too long" specifically
                               err_str = str(e).lower()
                               if 'caption' in err_str and 'too long' in err_str:
                                   logger.warning("Caption too long, truncating and retrying...")
                                   # Truncate caption on the first item
                                   if len(media) > 0:
                                       media[0].caption = carousel_caption[:950] + "..."
                                       try:
                                           _sent = await context.bot.send_media_group(
                                                chat_id=msg.chat_id,
                                                media=media
                                           )
                                           sent_ok = True
                                           if chunk_index == 0 and _sent:
                                               vote_msg = _sent[0]
                                           for _sm in (_sent or []):
                                               _fc = _fid_from_msg(_sm)
                                               if _fc:
                                                   captured.append(_fc)
                                       except Exception as inner_e:
                                           logger.error(f"Failed retry sending media group: {inner_e}")
                                           await context.bot.send_message(msg.chat_id, "⚠️ Errore nell'invio (didascalia troppo lunga).")
                               else:
                                    logger.error(f"Send media group error: {e}")
                                    await context.bot.send_message(msg.chat_id, "⚠️ Errore nell'invio dell'album.")

                        finally:
                            # Chiudi handle e cancella file
                            for f, photo_path in opened:
                                try:
                                    f.close()
                                except Exception:
                                    pass
                                try:
                                    os.remove(photo_path)
                                except Exception:
                                    pass

            # Punto in classifica + rimozione del messaggio originale SOLO se abbiamo
            # davvero consegnato il contenuto nel gruppo (1 contenuto = 1 punto).
            if sent_ok:
                note_download_success(detect_platform(url))
                # Salva i file_id in cache per il rinvio istantaneo dei prossimi repost
                try:
                    payload = build_cache_payload(captured, detect_platform(url), raw_title)
                    if payload:
                        await ranking_store.set_cached(key, payload)
                except Exception as e:
                    logger.warning(f"Cache file_id: set fallito: {e}")
                # Caroselli/foto: il voto è sul primo media (si reagisce a quello),
                # niente messaggio separato — l'invito è già nella didascalia.
                if info.get("type") == "carousel" and vote_msg is not None:
                    try:
                        await ranking_store.create_vote(
                            f"{vote_msg.chat_id}:{vote_msg.message_id}",
                            msg.from_user.id, msg.from_user.full_name, fid=None)
                    except Exception as e:
                        logger.warning(f"Voto carosello fallito: {e}")
                try:
                    totals = await ranking_store.add_point(msg.from_user.id, msg.from_user.full_name)
                    # Registra il link per il "già postato"
                    await ranking_store.record_link(link_key(url), msg.from_user.id, msg.from_user.full_name)
                    # Achievement appena sbloccati
                    already = await ranking_store.get_earned(msg.from_user.id)
                    for code in newly_earned(totals, already):
                        await ranking_store.add_earned(msg.from_user.id, code)
                        try:
                            mention = f'<a href="tg://user?id={msg.from_user.id}">{escape(msg.from_user.first_name)}</a>'
                            await context.bot.send_message(
                                chat_id=msg.chat_id,
                                text=f"🎉 {mention} ha sbloccato un achievement!\n{ACHIEVEMENTS.get(code, code)}",
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"Ranking: add_point fallito per {msg.from_user.id}: {e}")
                if not original_message_deleted:
                    try:
                        await msg.delete()
                        original_message_deleted = True
                    except Exception:
                        pass

            await loading.delete() # Cancella "Download in corso" per questo link

        except Exception as e:
            logger.error(f"Errore critico durante loop {url}: {e}", exc_info=True)
            try:
                await context.bot.send_message(msg.chat_id, f"❌ Si è verificato un errore imprevisto su {url}.")
            except Exception:
                pass
            try:
                await loading.delete()
            except Exception:
                pass

# =========================
# HOURLY FUNNY VIDEO JOB
# =========================

async def hourly_funny_routine(context: ContextTypes.DEFAULT_TYPE):
    # Timezone check (Europe/Rome)
    try:
        tz = pytz.timezone('Europe/Rome')
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()

    # Exclude 00:00 to 09:00 (active from 09:00 to 23:59)
    if now.hour < 9:
        return

    # Log chat destination
    logger.info(f"Hourly Funny Job: Sending to GROUP_CHAT_ID={GROUP_CHAT_ID}")

    dl = get_downloader()

    # Try up to 3 sources before giving up
    for _ in range(3):
        source = random.choice(FUNNY_SOURCES)
        try:
            # Get random video url
            video_url = await dl.get_random_video_url(source)
            if not video_url:
                continue

            # Download
            info = await dl.download_video(video_url)

            if info.get("success") and info.get("type") == "video":
                # Send video ONLY (no poll)
                caption = (
                    f"🐱 <b>Gattini Divertenti!</b>\n"
                    f"👤 <b>Fonte:</b> <a href='{source}'>TikTok</a>\n"
                )

                with open(info['file_path'], 'rb') as f:
                    await context.bot.send_video(
                        chat_id=GROUP_CHAT_ID,
                        video=f,
                        caption=caption,
                        parse_mode=ParseMode.HTML
                    )

                try:
                    os.remove(info['file_path'])
                except Exception:
                    pass

                # Break loop on success
                break

        except Exception as e:
            logger.error(f"Funny video loop error on source {source}: {e}")
            continue

# =========================
# WEEKLY RANKING JOB
# =========================

async def weekly_ranking(context: ContextTypes.DEFAULT_TYPE):
    board = await ranking_store.get_board('weekly', limit=3)
    if not board:
        return

    # Usa il chat_id del job se presente (così invia solo al gruppo configurato)
    chat_id = getattr(getattr(context, 'job', None), 'chat_id', None) or GROUP_CHAT_ID

    aforisma = random.choice(AFORISMI)
    celebra = random.choice(["🎉", "🥳", "🎊", "🏅", "✨", "🔥", "👏", "🎈"])

    text = f"{celebra} <b>RANKING SETTIMANALE</b> {celebra}\n\n"

    # Mostra sempre i primi 3 posti (se mancano, mostra segnaposto)
    for i in range(3):
        badge = BADGES[i] if i < len(BADGES) else '•'
        if i < len(board):
            user_id, count, name = board[i]
            # Menzione cliccabile: notifica il vincitore (funziona anche senza username)
            mention = f'<a href="tg://user?id={user_id}">{escape(name)}</a>'
            text += f"{badge} {mention} — <b>{count}</b> video\n"
        else:
            text += f"{badge} — <b>0</b> video\n"

    # 🎯 Sfida della settimana (se impostata)
    try:
        challenge = await ranking_store.get_challenge()
    except Exception:
        challenge = None
    if challenge and challenge.get('t'):
        text += f"\n\n🎯 <b>Sfida della settimana:</b> «{escape(str(challenge['t']))}»"

    # 🏅 Medaglia del pubblico: utente con più voti ricevuti sui propri video
    try:
        voted = await ranking_store.top_voted_week(limit=1)
    except Exception:
        voted = []
    if voted:
        v_id, v_count, v_name = voted[0]
        v_mention = f'<a href="tg://user?id={v_id}">{escape(v_name)}</a>'
        text += (f"\n\n🏅 <b>Medaglia del pubblico</b>\n"
                 f"{v_mention} con <b>{v_count}</b> voti sui suoi video! 👏")
        try:
            await ranking_store.incr_medal(v_id)  # conta la medaglia nel profilo
        except Exception:
            pass

    text += f"\n\n📜 <i>{escape(aforisma)}</i>"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML
    )

    # 🏆 Video della Settimana: rimanda il video più reagito (via file_id, senza riscaricare)
    try:
        tv = await ranking_store.top_video_week()
    except Exception:
        tv = None
    if tv and tv.get('fid'):
        try:
            tv_mention = f'<a href="tg://user?id={tv["owner"]}">{escape(tv["name"])}</a>'
            reazioni = "  ".join(f"{e} {c}" for e, c in (tv.get('r') or {}).items()) or f"{tv['c']} reazioni"
            await context.bot.send_video(
                chat_id=chat_id, video=tv['fid'],
                caption=f"🏆 <b>VIDEO DELLA SETTIMANA</b>\nDi {tv_mention} — {reazioni} 🎉",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Video della settimana non inviato: {e}")

    await ranking_store.reset_weekly()


async def monthly_oscar(context: ContextTypes.DEFAULT_TYPE):
    """Premiazione di fine mese. Job giornaliero che scatta solo l'ultimo giorno del mese
    (così i dati del mese corrente sono ancora intatti)."""
    now = datetime.now(pytz.timezone('Europe/Rome')) if pytz else datetime.now()
    domani = now + timedelta(days=1)
    if domani.day != 1:
        return  # non è l'ultimo giorno del mese

    try:
        dl_board = await ranking_store.get_board('monthly', limit=3)
    except Exception:
        dl_board = []
    try:
        vote_board = await ranking_store.top_voted_month(limit=3)
    except Exception:
        vote_board = []
    if not dl_board and not vote_board:
        return

    text = "🏆🎬 <b>GLI OSCAR DEL MESE</b> 🎬🏆\n"
    if dl_board:
        text += "\n📥 <b>Più attivo</b>\n"
        for i, (uid, c, n) in enumerate(dl_board):
            badge = BADGES[i] if i < len(BADGES) else '•'
            text += f"{badge} <a href='tg://user?id={uid}'>{escape(n)}</a> — <b>{c}</b> contenuti\n"
    if vote_board:
        text += "\n👑 <b>Più amato</b>\n"
        for i, (uid, c, n) in enumerate(vote_board):
            badge = BADGES[i] if i < len(BADGES) else '•'
            text += f"{badge} <a href='tg://user?id={uid}'>{escape(n)}</a> — <b>{c}</b> voti\n"
    text += "\n👏 Complimenti a tutti, ci vediamo il mese prossimo!"
    try:
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"Oscar mensile non inviato: {e}")


async def monthly_wrapped(context: ContextTypes.DEFAULT_TYPE):
    """Recap personale di fine mese, inviato in DM a chi è stato attivo.
    Job giornaliero che agisce solo l'ultimo giorno del mese."""
    now = datetime.now(pytz.timezone('Europe/Rome')) if pytz else datetime.now()
    if (now + timedelta(days=1)).day != 1:
        return
    try:
        users = await ranking_store.monthly_active_users()
    except Exception:
        users = []
    mese = now.strftime('%B').capitalize()
    sent = 0
    for uid in users:
        try:
            p = await ranking_store.get_profile(uid)
        except Exception:
            continue
        r_emoji, r_title = get_rank(p['alltime'])
        best = f"\n🔥 Il tuo video più amato: <b>{p['best_video']}</b> reazioni" if p.get('best_video') else ""
        text = (
            f"🎁 <b>IL TUO {mese.upper()} su Nello!</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🗓️ Contenuti del mese: <b>{p['monthly']}</b>\n"
            f"👍 Voti ricevuti nel mese: <b>{p.get('votes_received_month', 0)}</b>{best}\n"
            f"🏛️ Totale all-time: <b>{p['alltime']}</b>\n"
            f"{r_emoji} Rango: <b>{r_title}</b>\n\n"
            f"Grazie per aver animato il gruppo! Ci vediamo il mese prossimo 🚀"
        )
        try:
            await context.bot.send_message(chat_id=int(uid), text=text, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            pass  # l'utente non ha mai avviato il bot in privato
    logger.info(f"Wrapped mensile inviato a {sent}/{len(users)} utenti")


async def weekly_redeploy(context: ContextTypes.DEFAULT_TYPE):
    """Redeploy settimanale: ribuilda l'immagine -> yt-dlp e plugin freschi.
    Sicuro: se il build fallisce, Render tiene live la versione attuale.
    Attivo solo se RENDER_API_KEY e RENDER_SERVICE_ID sono configurati."""
    if not (RENDER_API_KEY and RENDER_SERVICE_ID):
        return
    ok = await asyncio.to_thread(render_trigger_deploy)
    logger.info(f"Auto-redeploy settimanale: {'avviato' if ok else 'fallito'}")

# =========================
# WEB SERVER (RENDER)
# =========================

async def health(request):
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.add_routes([web.get("/", health)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    await asyncio.Event().wait()

def start_webserver():
    asyncio.run(run_web())

# =========================
# DIAGNOSTICA po_token (bgutil)
# =========================

def potoken_selftest():
    """All'avvio: verifica che il server bgutil risponda e che yt-dlp usi il po_token."""
    import time as _t
    import urllib.request

    # 1) Attendi che il server bgutil sia pronto (max ~15s) e pinga
    server_ok = False
    for _ in range(15):
        try:
            with urllib.request.urlopen('http://127.0.0.1:4416/ping', timeout=3) as r:
                body = r.read().decode('utf-8', 'replace')[:200]
                logger.info(f"[POT] bgutil /ping OK: {body}")
                server_ok = True
                break
        except Exception:
            _t.sleep(1)
    if not server_ok:
        logger.warning("[POT] bgutil /ping NON raggiungibile dopo 15s")

    # 2) Plugin caricato da yt-dlp?
    try:
        import yt_dlp_plugins  # noqa: F401
        logger.info(f"[POT] yt_dlp_plugins presente: {list(getattr(yt_dlp_plugins, '__path__', []))}")
    except Exception as e:
        logger.warning(f"[POT] yt_dlp_plugins NON importabile: {e}")

    # 3) Estrazione di prova verbose: cattura le righe relative a plugin / po_token
    captured = []
    try:
        import shutil
        import yt_dlp

        class _L:
            def debug(self, m): captured.append(str(m))
            def info(self, m): captured.append(str(m))
            def warning(self, m): captured.append(str(m))
            def error(self, m): captured.append(str(m))

        # Copia i cookie in posizione scrivibile (/etc/secrets e' read-only)
        cookie_copy = None
        try:
            if os.path.exists('/etc/secrets/YOUTUBE_COOKIES'):
                cookie_copy = '/tmp/yt_selftest_cookies.txt'
                shutil.copyfile('/etc/secrets/YOUTUBE_COOKIES', cookie_copy)
        except Exception as e:
            logger.warning(f"[POT] copia cookie fallita: {e}")
            cookie_copy = None

        ydl_opts = {
            'quiet': True, 'no_warnings': True, 'skip_download': True,
            'verbose': True, 'logger': _L(),
            'js_runtimes': {'deno': {}},
            'extractor_args': {'youtube': {'player_client': ['tv', 'web', 'mweb']}},
        }
        if cookie_copy:
            ydl_opts['cookiefile'] = cookie_copy

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info('https://www.youtube.com/watch?v=dQw4w9WgXcQ', download=False)
                nfmt = len(info.get('formats') or []) if info else 0
                logger.info(f"[POT] estrazione di prova: {nfmt} formati trovati")
            except Exception as e:
                logger.warning(f"[POT] estrazione di prova fallita: {str(e)[:160]}")
    except Exception as e:
        logger.warning(f"[POT] selftest fallito: {e}")
    finally:
        # Stampa le righe rilevanti dei log verbose (anche se l'estrazione e' fallita)
        kws = ('pot token', 'po_token', 'potoken', 'bgutil', 'pot provider', 'gvs',
               'plugin', 'fetching', 'visitor', 'player', 'sign in', 'format')
        rel = [m for m in captured if any(k in m.lower() for k in kws)]
        for m in rel[:30]:
            logger.info(f"[POT] {m[:220]}")
        if not rel:
            logger.info("[POT] nessuna riga rilevante nei log verbose")

# =========================
# ERROR HANDLER
# =========================

async def error_handler(update, context):
    """Gestisce gli errori globali. Silenzia il Conflict transitorio dei deploy
    (due istanze in polling per pochi secondi) che altrimenti sporca i log."""
    from telegram.error import Conflict
    err = context.error
    if isinstance(err, Conflict):
        logger.info("getUpdates Conflict transitorio (cambio istanza al deploy), ignoro.")
        return
    logger.error(f"Errore non gestito: {err}", exc_info=err)


# =========================
# MAIN
# =========================

def main():
    # Diagnostica po_token disattivata di default (aggiunge ~20s allo startup).
    # Riattivabile impostando POT_SELFTEST=1 su Render quando serve indagare.
    if os.getenv('POT_SELFTEST', '0') == '1':
        try:
            potoken_selftest()
        except Exception as e:
            logger.warning(f"potoken_selftest error: {e}")

    # Webhook mode (useful on Render) controlled by USE_WEBHOOK and WEBHOOK_URL
    USE_WEBHOOK = os.getenv('USE_WEBHOOK', '0') == '1'
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')
    WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/')

    print("Building application...")
    # Increase default timeouts to handle large file uploads/downloads
    request_settings = HTTPXRequest(
        connection_pool_size=10,
        read_timeout=120.0,
        write_timeout=120.0,
        connect_timeout=60.0,
        pool_timeout=60.0
    )
    application = Application.builder().token(TOKEN).request(request_settings).build()
    print("Application built.")

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("classifica", classifica_cmd))
    application.add_handler(CommandHandler("mensile", mensile_cmd))
    application.add_handler(CommandHandler("record", record_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("profilo", profilo_cmd))
    application.add_handler(CommandHandler("votati", votati_cmd))
    application.add_handler(CommandHandler("setcookies", setcookies_cmd))
    application.add_handler(CommandHandler("chats", chats_cmd))
    application.add_handler(CommandHandler("sfida", sfida_cmd))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageReactionHandler(on_reaction))
    # File inviato dall'admin per /setcookies
    application.add_handler(MessageHandler(filters.Document.ALL, on_document))
    # Log all text messages first to verify visibility
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler))
    application.add_error_handler(error_handler)
    print("Handlers added.")

    # Frontend Discord (opzionale): gira in un thread separato accanto a Telegram,
    # condividendo downloader e store (voti/classifiche condivisi). Si attiva solo
    # se DISCORD_TOKEN è impostato.
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    if DISCORD_TOKEN:
        try:
            import discord_bot
            from types import SimpleNamespace
            ns = SimpleNamespace(
                ranking_store=ranking_store,
                is_supported_link=is_supported_link,
                detect_platform=detect_platform,
                clean_title=_clean_title,
                newly_earned=newly_earned,
                get_rank=get_rank,
                achievements=ACHIEVEMENTS,
            )
            discord_bot.start_in_thread(DISCORD_TOKEN, ns)
        except Exception as e:
            logger.error(f"Avvio frontend Discord fallito: {e}")

    application.job_queue.run_daily(
        weekly_ranking,
        time=time(hour=20, minute=0),
        days=(6,),
        chat_id=GROUP_CHAT_ID
    )

    # Oscar di fine mese: job giornaliero alle 21:00 che agisce solo l'ultimo giorno del mese.
    application.job_queue.run_daily(
        monthly_oscar,
        time=time(hour=21, minute=0),
        chat_id=GROUP_CHAT_ID
    )

    # Wrapped personale di fine mese (DM): job giornaliero alle 21:30, agisce solo l'ultimo giorno.
    application.job_queue.run_daily(
        monthly_wrapped,
        time=time(hour=21, minute=30),
    )

    # Post divertente giornaliero: DISATTIVATO di default (riattivabile con FUNNY_DAILY=1).
    if os.getenv('FUNNY_DAILY', '0') == '1':
        try:
            funny_hour = int(os.getenv('FUNNY_HOUR', '13'))
        except ValueError:
            funny_hour = 13
        application.job_queue.run_daily(
            hourly_funny_routine,
            time=time(hour=funny_hour, minute=0),
            chat_id=GROUP_CHAT_ID
        )

    # Redeploy automatico settimanale (yt-dlp/plugin freschi). Solo se Render configurato.
    if RENDER_API_KEY and RENDER_SERVICE_ID:
        application.job_queue.run_daily(
            weekly_redeploy,
            time=time(hour=5, minute=0),
            days=(0,),  # lunedì
        )

    if USE_WEBHOOK and WEBHOOK_URL:
        # Run webhook server (python-telegram-bot will bind to PORT)
        # WEBHOOK_PATH should be the path portion (e.g. '/webhook') or '/' for root
        # Example: set USE_WEBHOOK=1 and WEBHOOK_URL=https://your-app.onrender.com/<path>
        try:
            application.run_webhook(
                listen='0.0.0.0',
                port=PORT,
                url_path=WEBHOOK_PATH,
                webhook_url=WEBHOOK_URL,
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,  # include le reazioni native
            )
        except Exception as e:
            logger.error(f"Failed to start webhook mode: {e}")
    else:
        # Start a minimal health webserver for Render and run polling
        threading.Thread(target=start_webserver, daemon=True).start()
        logger.info("Starting polling...")
        # allowed_updates=ALL_TYPES: necessario per ricevere le reazioni (message_reaction)
        application.run_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("FATAL ERROR IN MAIN LOOP")
        raise e

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
from datetime import time, datetime
from collections import defaultdict

from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.helpers import escape
from telegram import InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
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

# Limite di upload della Bot API di Telegram (50MB per i bot standard)
TELEGRAM_MAX_BYTES = 50 * 1024 * 1024

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

    # Restrict YouTube to Shorts only
    if "youtube.com" in url or "youtu.be" in url:
        return "/shorts/" in url

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


def _meta_line(info: dict) -> str:
    """Riga opzionale con durata/views/like/autore, se disponibili."""
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
    caption = (
        f"{icon_main} <b>{label} da:</b> {detect_platform(url)}\n"
        f"{random.choice(ICONS_USER)} <b>{label} {inviato} da:</b> {sender}\n"
        f"{random.choice(ICONS_LINK)} <b>Link originale:</b> {escape(url)}\n"
        f"{random.choice(ICONS_META)} <b>Info:</b> {escape(raw_title)}"
    )
    meta = _meta_line(info)
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
            await context.bot.send_video(chat_id=msg.chat_id, video=cached['fid'],
                                         caption=caption, parse_mode=ParseMode.HTML)
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
}


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
        "• /classifica — top della settimana\n"
        "• /mensile — top del mese\n"
        "• /record — albo d'oro all-time\n"
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
    board = await ranking_store.get_board(period, limit=10)
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
    s = await ranking_store.get_user_stats(u.id)
    earned = await ranking_store.get_earned(u.id)
    rank_txt = f"#{s['rank']} su {s['total_users']}" if s.get('rank') else "—"
    badges = " ".join(ACHIEVEMENTS.get(c, "🏅").split()[0] for c in earned) or "nessuno ancora"
    text = (
        f"📊 <b>Le tue statistiche, {escape(u.first_name)}</b>\n\n"
        f"📆 Questa settimana: <b>{s['weekly']}</b>\n"
        f"🗓️ Questo mese: <b>{s['monthly']}</b>\n"
        f"🏛️ Totale: <b>{s['alltime']}</b>\n"
        f"🥇 Posizione all-time: <b>{rank_txt}</b>\n"
        f"🎖️ Achievement: {badges}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

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
            info = await dl.download_video(url)

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

            # Truncate title to 3 lines max
            raw_title = info.get('title', 'N/A')
            if raw_title:
                 # Split lines, take first 3
                 lines = raw_title.split('\n')
                 if len(lines) > 3:
                     raw_title = '\n'.join(lines[:3]) + "..."
                 # Also strict char limit just in case
                 if len(raw_title) > 300:
                     raw_title = raw_title[:300] + "..."

            caption = build_caption(info, url, msg.from_user.full_name, raw_title, sender_id=msg.from_user.id)

            # =========================
            # INVIO CONTENUTI
            # =========================

            # === VIDEO ===
            if info.get("type", "video") == "video":
                with open(info["file_path"], "rb") as f:
                    _m = await context.bot.send_video(
                        chat_id=msg.chat_id,
                        video=f,
                        caption=caption,
                        parse_mode=ParseMode.HTML
                    )
                sent_ok = True
                _fc = _fid_from_msg(_m)
                if _fc:
                    captured.append(_fc)
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
                                    caption=caption,
                                    parse_mode=ParseMode.HTML
                                )
                            else:
                                _m = await context.bot.send_photo(
                                    chat_id=msg.chat_id,
                                    photo=f,
                                    caption=caption,
                                    parse_mode=ParseMode.HTML
                                )
                        sent_ok = True
                        _fc = _fid_from_msg(_m)
                        if _fc:
                            captured.append(_fc)
                    except Exception as e:
                        err_str = str(e).lower()
                        if 'caption' in err_str and 'too long' in err_str:
                             logger.warning("Caption too long for single item, truncating...")
                             short_caption = caption[:950] + "..."
                             try:
                                 with open(photo_path, "rb") as f:
                                    if is_video:
                                        _m = await context.bot.send_video(chat_id=msg.chat_id, video=f, caption=short_caption, parse_mode=ParseMode.HTML)
                                    else:
                                        _m = await context.bot.send_photo(chat_id=msg.chat_id, photo=f, caption=short_caption, parse_mode=ParseMode.HTML)
                                 sent_ok = True
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
                                            caption=caption,
                                            parse_mode=ParseMode.HTML
                                        ))
                                    else:
                                        media.append(InputMediaPhoto(
                                            media=f,
                                            caption=caption,
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
                                       media[0].caption = caption[:950] + "..."
                                       try:
                                           _sent = await context.bot.send_media_group(
                                                chat_id=msg.chat_id,
                                                media=media
                                           )
                                           sent_ok = True
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

    text += f"\n📜 <i>{escape(aforisma)}</i>"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML
    )

    await ranking_store.reset_weekly()

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
    # Log all text messages first to verify visibility
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler))
    application.add_error_handler(error_handler)
    print("Handlers added.")

    application.job_queue.run_daily(
        weekly_ranking,
        time=time(hour=20, minute=0),
        days=(6,),
        chat_id=GROUP_CHAT_ID
    )

    # Post divertente giornaliero (orario configurabile via FUNNY_HOUR, default 13:00).
    # Disattivabile con FUNNY_DAILY=0.
    if os.getenv('FUNNY_DAILY', '1') == '1':
        try:
            funny_hour = int(os.getenv('FUNNY_HOUR', '13'))
        except ValueError:
            funny_hour = 13
        application.job_queue.run_daily(
            hourly_funny_routine,
            time=time(hour=funny_hour, minute=0),
            chat_id=GROUP_CHAT_ID
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
            )
        except Exception as e:
            logger.error(f"Failed to start webhook mode: {e}")
    else:
        # Start a minimal health webserver for Render and run polling
        threading.Thread(target=start_webserver, daemon=True).start()
        logger.info("Starting polling...")
        application.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("FATAL ERROR IN MAIN LOOP")
        raise e

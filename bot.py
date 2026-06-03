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

# Limite di upload della Bot API di Telegram (50MB per i bot standard)
TELEGRAM_MAX_BYTES = 50 * 1024 * 1024

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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
        "tiktok.com", "instagram.com", "facebook.com",
        "youtube.com", "youtu.be", "twitter.com", "x.com"
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
    if "facebook" in url:
        return "Facebook"
    if "youtube" in url or "youtu.be" in url:
        if "/shorts/" in url:
             return "YouTube Shorts"
        return "YouTube"
    if "twitter" in url or "x.com" in url:
        return "Twitter / X"
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


def build_caption(info: dict, url: str, sender_name: str, raw_title: str) -> str:
    """Didascalia adattiva (Foto/Video/Contenuto) con icone casuali e accordo grammaticale."""
    label = media_label(info)
    inviato = "inviata" if label == "Foto" else "inviato"
    icon_main = random.choice(ICONS_FOTO if label == "Foto" else ICONS_VIDEO)
    return (
        f"{icon_main} <b>{label} da:</b> {detect_platform(url)}\n"
        f"{random.choice(ICONS_USER)} <b>{label} {inviato} da:</b> {escape(sender_name)}\n"
        f"{random.choice(ICONS_LINK)} <b>Link originale:</b> {escape(url)}\n"
        f"{random.choice(ICONS_META)} <b>Info:</b> {escape(raw_title)}"
    )

# =========================
# COMMANDS
# =========================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received /start in chat {update.effective_chat.id} from {update.effective_user.id}")
    await update.message.reply_text(f"Ciao! Il Chat ID di questo gruppo è: <code>{update.effective_chat.id}</code>\nMandami un link video e penso io a tutto 🔥", parse_mode=ParseMode.HTML)


async def resolve_user_name(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    """Risolve il nome pubblico di un utente dal suo id (best effort)."""
    try:
        chat = await context.bot.get_chat(user_id)
        return chat.full_name or getattr(chat, 'first_name', None) or 'Utente'
    except Exception:
        return 'Utente'


async def classifica_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra la classifica corrente (live) senza azzerarla."""
    data = await ranking_store.get_all()
    if not data:
        await update.message.reply_text(
            "📭 Nessun video in classifica questa settimana. Mandane uno! 🐶"
        )
        return

    sorted_users = sorted(data.items(), key=lambda x: x[1], reverse=True)

    text = "🏆 <b>CLASSIFICA ATTUALE</b>\n\n"
    for i, (user_id, count) in enumerate(sorted_users[:10]):
        badge = BADGES[i] if i < len(BADGES) else f"<b>{i + 1}.</b>"
        name = await resolve_user_name(context, user_id)
        text += f"{badge} {escape(name)} — <b>{count}</b> video\n"

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

    logger.info(f"Received message from {update.effective_user.id} with {len(valid_urls)} valid links")

    # Downloader condiviso (singleton)
    dl = get_downloader()

    # Per evitare spam di errori, cancelliamo messaggio originale su primo successo
    original_message_deleted = False

    for i, url in enumerate(valid_urls):
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

            caption = build_caption(info, url, msg.from_user.full_name, raw_title)

            # =========================
            # INVIO CONTENUTI
            # =========================

            # === VIDEO ===
            if info.get("type", "video") == "video":
                with open(info["file_path"], "rb") as f:
                    await context.bot.send_video(
                        chat_id=msg.chat_id,
                        video=f,
                        caption=caption,
                        parse_mode=ParseMode.HTML
                    )
                sent_ok = True
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
                                await context.bot.send_video(
                                    chat_id=msg.chat_id,
                                    video=f,
                                    caption=caption,
                                    parse_mode=ParseMode.HTML
                                )
                            else:
                                await context.bot.send_photo(
                                    chat_id=msg.chat_id,
                                    photo=f,
                                    caption=caption,
                                    parse_mode=ParseMode.HTML
                                )
                        sent_ok = True
                    except Exception as e:
                        err_str = str(e).lower()
                        if 'caption' in err_str and 'too long' in err_str:
                             logger.warning("Caption too long for single item, truncating...")
                             short_caption = caption[:950] + "..."
                             try:
                                 with open(photo_path, "rb") as f:
                                    if is_video:
                                        await context.bot.send_video(chat_id=msg.chat_id, video=f, caption=short_caption, parse_mode=ParseMode.HTML)
                                    else:
                                        await context.bot.send_photo(chat_id=msg.chat_id, photo=f, caption=short_caption, parse_mode=ParseMode.HTML)
                                 sent_ok = True
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
                                await context.bot.send_media_group(
                                    chat_id=msg.chat_id,
                                    media=media
                                )
                                sent_ok = True
                            except Exception as e:
                               # Handle "caption too long" specifically
                               err_str = str(e).lower()
                               if 'caption' in err_str and 'too long' in err_str:
                                   logger.warning("Caption too long, truncating and retrying...")
                                   # Truncate caption on the first item
                                   if len(media) > 0:
                                       media[0].caption = caption[:950] + "..."
                                       try:
                                           await context.bot.send_media_group(
                                                chat_id=msg.chat_id,
                                                media=media
                                           )
                                           sent_ok = True
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
                try:
                    await ranking_store.add_point(msg.from_user.id)
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
    data = await ranking_store.get_all()
    if not data:
        return

    # Usa il chat_id del job se presente (così invia solo al gruppo configurato)
    chat_id = getattr(getattr(context, 'job', None), 'chat_id', None) or GROUP_CHAT_ID

    sorted_users = sorted(
        data.items(),
        key=lambda x: x[1],
        reverse=True
    )

    aforisma = random.choice(AFORISMI)
    celebra = random.choice(["🎉", "🥳", "🎊", "🏅", "✨", "🔥", "👏", "🎈"])

    text = f"{celebra} <b>RANKING SETTIMANALE</b> {celebra}\n\n"

    # Mostra sempre i primi 3 posti (se mancano, mostra segnaposto)
    for i in range(3):
        badge = BADGES[i] if i < len(BADGES) else '•'
        if i < len(sorted_users):
            user_id, count = sorted_users[i]
            name = await resolve_user_name(context, user_id)
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

    await ranking_store.reset()

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
# MAIN
# =========================

def main():
    if os.getenv('POT_SELFTEST', '1') == '1':
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
    # Log all text messages first to verify visibility
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler))
    print("Handlers added.")

    application.job_queue.run_daily(
        weekly_ranking,
        time=time(hour=20, minute=0),
        days=(6,),
        chat_id=GROUP_CHAT_ID
    )

    # application.job_queue.run_repeating(
    #     hourly_funny_routine,
    #     interval=3600,
    #     first=60,
    #     chat_id=GROUP_CHAT_ID
    # )

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

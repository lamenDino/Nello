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
from datetime import time
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
from dotenv import load_dotenv
from social_downloader import SocialMediaDownloader

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "8080"))

GROUP_CHAT_ID = int(os.getenv('CHAT_ID') or os.getenv('GROUP_CHAT_ID') or '214193849')

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# RANKING
# =========================

video_ranking = defaultdict(int)

BADGES = ["🥇", "🥈", "🥉"]

AFORISMI = [
    "La costanza batte il talento quando il talento dorme.",
    "Chi fa ogni giorno qualcosa, arriva sempre lontano.",
    "Il successo è la somma di piccoli sforzi ripetuti.",
    "Non esistono scorciatoie che valgano più del percorso.",
    "La disciplina oggi è la libertà di domani."
]

# =========================
# UTILS
# =========================

def is_supported_link(url: str) -> bool:
    return any(d in url for d in [
        "tiktok.com", "instagram.com", "facebook.com",
        "youtube.com", "youtu.be", "twitter.com", "x.com"
    ])

def detect_platform(url: str) -> str:
    url = url.lower()
    if "tiktok" in url:
        return "TikTok"
    if "instagram" in url:
        return "Instagram"
    if "facebook" in url:
        return "Facebook"
    if "youtube" in url:
        return "YouTube"
    if "twitter" in url or "x.com" in url:
        return "Twitter / X"
    return "Sconosciuta"

# =========================
# COMMANDS
# =========================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Mandami un link video e penso io a tutto 🔥")

# =========================
# DOWNLOAD HANDLER
# =========================

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    url = msg.text.strip()

    if not is_supported_link(url):
        return

    loading = await context.bot.send_message(msg.chat_id, "⏳ Download in corso...")

    dl = SocialMediaDownloader(debug=os.getenv('SMD_DEBUG', '0') == '1')

    try:
        info = await dl.download_video(url)

        # ❌ fallimento → silenzio totale
        if not info or not info.get("success"):
            await loading.delete()
            return

        try:
            await msg.delete()
        except Exception:
            pass

        # incrementa ranking (1 contenuto = 1 punto, sia video che carosello)
        video_ranking[msg.from_user.id] += 1

        caption = (
            f"🎵 <b>Video da :</b> {detect_platform(url)}\n"
            f"👤 <b>Video inviato da :</b> {escape(msg.from_user.full_name)}\n"
            f"🔗 <b>Link originale :</b> {escape(url)}\n"
            f"📝 <b>Meta info video :</b> {escape(info.get('title', 'N/A'))}"
        )

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
            try:
                os.remove(info["file_path"])
            except Exception:
                pass

        # === CAROSELLO FOTO (ALBUM UNICO) ===
        elif info.get("type") == "carousel":
            files = info.get("files", [])
            if not files:
                await loading.delete()
                return

            # Telegram: max 10 media in un media_group
            # Se vuoi, puoi aumentare spezzando in più album.
            MAX_GROUP = 10
            chunks = [files[i:i + MAX_GROUP] for i in range(0, len(files), MAX_GROUP)]

            for chunk_index, chunk in enumerate(chunks):
                media = []
                opened = []  # teniamo i file handle aperti finché non inviamo

                try:
                    for i, photo_path in enumerate(chunk):
                        f = open(photo_path, "rb")
                        opened.append((f, photo_path))

                        # Caption solo sul primo media del primo chunk
                        ext = os.path.splitext(photo_path)[1].lower()
                        is_video = ext in ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.flv', '.ts')

                        if chunk_index == 0 and i == 0:
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

                    await context.bot.send_media_group(
                        chat_id=msg.chat_id,
                        media=media
                    )

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

        await loading.delete()

    except Exception as e:
        logger.error(f"Errore critico: {e}")
        try:
            await loading.delete()
        except Exception:
            pass

# =========================
# WEEKLY RANKING JOB
# =========================

async def weekly_ranking(context: ContextTypes.DEFAULT_TYPE):
    if not video_ranking:
        return

    # Usa il chat_id del job se presente (così invia solo al gruppo configurato)
    chat_id = getattr(getattr(context, 'job', None), 'chat_id', None) or GROUP_CHAT_ID

    sorted_users = sorted(
        video_ranking.items(),
        key=lambda x: x[1],
        reverse=True
    )

    aforisma = random.choice(AFORISMI)

    text = "🏆 <b>RANKING SETTIMANALE</b>\n\n"

    # Mostra sempre i primi 3 posti (se mancano, mostra segnaposto)
    for i in range(3):
        badge = BADGES[i] if i < len(BADGES) else '•'
        if i < len(sorted_users):
            user_id, count = sorted_users[i]
            # Prova a risolvere il nome pubblico dell'utente
            try:
                chat = await context.bot.get_chat(user_id)
                name = chat.full_name or getattr(chat, 'first_name', None) or 'Utente'
            except Exception:
                name = 'Utente'

            text += f"{badge} [{escape(name)}] — <b>{count}</b> video\n"
        else:
            text += f"{badge} [—] — <b>0</b> video\n"

    text += f"\n📜 [{escape(aforisma)}]"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML
    )

    video_ranking.clear()

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
# MAIN
# =========================

def main():
    # Webhook mode (useful on Render) controlled by USE_WEBHOOK and WEBHOOK_URL
    USE_WEBHOOK = os.getenv('USE_WEBHOOK', '0') == '1'
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')
    WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/')

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler)
    )

    application.job_queue.run_daily(
        weekly_ranking,
        time=time(hour=20, minute=0),
        days=(6,),
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
                webhook_url_path=WEBHOOK_PATH,
                webhook_url=WEBHOOK_URL,
                drop_pending_updates=True,
            )
        except Exception as e:
            logger.error(f"Failed to start webhook mode: {e}")
    else:
        # Start a minimal health webserver for Render and run polling
        threading.Thread(target=start_webserver, daemon=True).start()
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

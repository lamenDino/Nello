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

GROUP_CHAT_ID = 214193849

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

    sorted_users = sorted(
        video_ranking.items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]

    aforisma = random.choice(AFORISMI)

    text = "🏆 <b>RANKING SETTIMANALE</b>\n\n"

    for i, (user_id, count) in enumerate(sorted_users):
        badge = BADGES[i]
        text += f"{badge} <a href='tg://user?id={user_id}'>Utente</a> — <b>{count}</b> video\n"

    text += f"\n📜 <i>{aforisma}</i>"

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
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
    threading.Thread(target=start_webserver, daemon=True).start()

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

    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

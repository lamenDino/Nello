#!/usr/bin/env python3
"""
Telegram Multi-Platform Video Downloader Bot v3.1
+ Retry silenzioso se estrazione fallisce
+ Ranking settimanale automatico (sabato ore 20)
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

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
PORT = int(os.getenv('PORT', '8080'))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# RANKING SETTIMANALE
# =========================

video_ranking = defaultdict(int)

AFORISMI = [
    "La vita è come un video: se non la vivi, non la puoi scaricare.",
    "Chi semina costanza raccoglie risultati.",
    "Non conta quanto vai veloce, ma che tu non ti fermi.",
    "Ogni giorno è una nuova occasione per fare meglio.",
    "La disciplina batte il talento quando il talento non si allena."
]

# Emoji per piattaforme
PLATFORM_EMOJI = {
    'tiktok': '🎵',
    'instagram': '📷',
    'facebook': '👍',
    'youtube': '▶️',
    'twitter': '🐦',
}

def is_supported_link(url: str) -> bool:
    domains = [
        'tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com',
        'instagram.com', 'ig.tv',
        'facebook.com', 'fb.watch',
        'youtube.com', 'youtu.be',
        'twitter.com', 'x.com'
    ]
    return any(d in url for d in domains)

def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if 'tiktok' in url_lower:
        return 'TikTok'
    if 'instagram' in url_lower:
        return 'Instagram'
    if 'facebook' in url_lower:
        return 'Facebook'
    if 'youtube' in url_lower:
        return 'YouTube'
    if 'twitter' in url_lower or 'x.com' in url_lower:
        return 'Twitter'
    return 'Sconosciuta'

# =========================
# COMANDI
# =========================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Inviami un link video (TikTok, Instagram, Facebook, YouTube Shorts, Twitter)"
    )

# =========================
# HANDLER DOWNLOAD
# =========================

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    url = msg.text.strip()

    if not is_supported_link(url):
        return

    loading = await context.bot.send_message(
        msg.chat_id,
        "⏳ Download in corso..."
    )

    dl = SocialMediaDownloader()

    try:
        info = await dl.download_video(url)

        # ❌ FALLIMENTO → SILENZIO ASSOLUTO
        if not info.get('success'):
            await loading.delete()
            return

        # ✅ SUCCESSO
        try:
            await msg.delete()
        except:
            pass

        # Ranking
        user_id = msg.from_user.id
        video_ranking[user_id] += 1

        platform = detect_platform(url)
        emoji = PLATFORM_EMOJI.get(platform.lower(), '📱')

        caption = (
            f"{emoji} <b>Video da: {platform}</b>\n"
            f"👤 Inviato da: <b>{escape(msg.from_user.full_name)}</b>\n"
            f"🔗 {escape(url)}"
        )

        with open(info['file_path'], 'rb') as f:
            await context.bot.send_video(
                chat_id=msg.chat_id,
                video=f,
                caption=caption,
                parse_mode=ParseMode.HTML
            )

        await loading.delete()
        os.remove(info['file_path'])

    except Exception as e:
        logger.error(f"Errore grave: {e}")
        await loading.delete()

# =========================
# RANKING JOB
# =========================

async def weekly_ranking(context: ContextTypes.DEFAULT_TYPE):
    if not video_ranking:
        return

    winner_id = max(video_ranking, key=video_ranking.get)
    count = video_ranking[winner_id]
    aforisma = random.choice(AFORISMI)

    text = (
        f"🏆 <b>Ranking settimanale</b>\n\n"
        f"👏 Complimenti <a href='tg://user?id={winner_id}'>campione</a>!\n"
        f"Hai inviato <b>{count} video</b> questa settimana.\n\n"
        f"📜 <i>{aforisma}</i>"
    )

    await context.bot.send_message(
        chat_id=context.job.chat_id,
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
    app.add_routes([web.get('/', health)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
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

    application.add_handler(CommandHandler('start', start_cmd))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler)
    )

    # JOB SETTIMANALE – SABATO ORE 20:00
    application.job_queue.run_weekly(
        weekly_ranking,
        time=time(hour=20, minute=0),
        days=(5,),  # Sabato
        chat_id=-100  # ← ID DEL GRUPPO (CAMBIALO!)
    )

    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

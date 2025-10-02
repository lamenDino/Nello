#!/usr/bin/env python3
"""
Bot Telegram per scaricare video da TikTok, Instagram e Facebook
Autore: Il tuo nome
Descrizione: Usa yt-dlp per scaricare video e inviarli in chat.
"""
import os
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from tiktok_downloader import TikTokDownloader

# Carica variabili ambiente
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_USER_ID', '0'))
PORT = int(os.getenv('PORT', '8080'))

# Config logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def is_supported_link(url: str) -> bool:
    domains = [
        'tiktok.com','vm.tiktok.com','vt.tiktok.com','m.tiktok.com',
        'instagram.com','ig.tv','facebook.com','fb.watch','fb.com'
    ]
    return any(d in url for d in domains)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Ciao {user.first_name}! Inviami un link TikTok, Instagram o Facebook e ti invio il video."
    )

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    url = msg.text.strip()
    if not is_supported_link(url):
        return
    try:
        await msg.delete()
    except:
        pass
    loading = await context.bot.send_message(msg.chat_id, "⏳ Download in corso...")
    dl = TikTokDownloader()
    try:
        info = await dl.download_video(url)
        if info['success']:
            source = (
                'TikTok' if 'tiktok' in url else
                'Instagram' if 'instagram' in url else
                'Facebook'
            )
            author = info.get('uploader','')
            caption = f"🎬 Video da {source}"
            if author:
                caption += f" di {author}"
            with open(info['file_path'], 'rb') as f:
                await context.bot.send_video(
                    chat_id=msg.chat_id,
                    video=f,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            await loading.delete()
            os.remove(info['file_path'])
        else:
            await loading.edit_text("❌ Contenuto non disponibile o richiede login.")
    except Exception as e:
        logger.error(f"Download error: {e}")
        err = str(e).lower()
        if 'login required' in err or 'cookie' in err:
            txt = ("❌ Impossibile scaricare: contenuto privato o limitato. "
                   "Assicurati che il post sia pubblico.")
        else:
            txt = "❌ Errore durante il download del video."
        await loading.edit_text(txt)

async def health(request):
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.add_routes([web.get('/', health)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Web server started on port {PORT}")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler))
    application.job_queue.run_once(lambda _: asyncio.create_task(run_web()), 0)
    logger.info("Bot avviato...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
import os
import logging
import threading
import asyncio
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.helpers import escape
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from tiktok_downloader import TikTokDownloader

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
PORT = int(os.getenv('PORT', '8080'))
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def is_supported_link(url: str) -> bool:
    domains = [
        'tiktok.com','vm.tiktok.com','vt.tiktok.com','m.tiktok.com',
        'instagram.com','ig.tv','facebook.com','fb.watch','fb.com'
    ]
    return any(d in url for d in domains)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"👋 Ciao {user.first_name}! Inviami un link TikTok, Instagram o Facebook per ricevere il video o le immagini.")

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    url = msg.text.strip()
    if not is_supported_link(url):
        return

    loading = await context.bot.send_message(msg.chat_id, "⏳ Download in corso...")
    dl = TikTokDownloader()
    try:
        info = await dl.download_video(url)
        if info['success']:
            try: await msg.delete()
            except: pass

            source = ('TikTok' if 'tiktok' in url else
                      'Instagram' if 'instagram' in url else
                      'Facebook')
            user_sender = escape(msg.from_user.full_name)
            title = escape(info.get('title') or "Post scaricato da bot multi-social!")
            orig_link = escape(url)
            caption = (
                f"Post da: {source}\n"
                f"Inviato da: {user_sender}\n"
                f"Link originale: {orig_link}\n"
                f"{title}"
            )

            sent_first = False
            for file_path in info["files"]:
                with open(file_path, 'rb') as f:
                    if file_path.endswith(('.jpg','.jpeg','.png','.webp')):
                        await context.bot.send_photo(
                            chat_id=msg.chat_id,
                            photo=f,
                            caption=caption if not sent_first else None,
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        await context.bot.send_video(
                            chat_id=msg.chat_id,
                            video=f,
                            caption=caption if not sent_first else None,
                            parse_mode=ParseMode.HTML
                        )
                os.remove(file_path)
                sent_first = True
            await loading.delete()
        else:
            await loading.edit_text(
                "❌ Errore: il contenuto non può essere scaricato. Il link rimane qui."
            )
    except Exception as e:
        logger.error(f"Download error: {e}")
        txt = "❌ Errore durante il download del contenuto."
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
    await asyncio.Event().wait()

def start_webserver():
    asyncio.run(run_web())

def main():
    thread = threading.Thread(target=start_webserver, daemon=True)
    thread.start()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_handler))
    logger.info("Bot avviato...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

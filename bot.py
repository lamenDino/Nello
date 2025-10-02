#!/usr/bin/env python3
"""
Bot Telegram per scaricare video da TikTok, Instagram e Facebook
Autore: Il tuo nome
Descrizione: Bot che usa yt-dlp per scaricare video e inviarli nel gruppo Telegram.
"""
import os
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from dotenv import load_dotenv
from tiktok_downloader import TikTokDownloader
import config

# Carica le variabili d'ambiente
load_dotenv()

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MultiPlatformBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.admin_id = int(os.getenv('ADMIN_USER_ID', 0))
        self.downloader = TikTokDownloader()
        if not self.token:
            raise ValueError("Token Telegram non trovato! Controlla le env vars")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"👋 Ciao {user.first_name}! Inviami un link TikTok, Instagram o Facebook e ti invio il video."
        )

    def is_supported_video_link(self, url: str) -> bool:
        domains = [
            'tiktok.com','vm.tiktok.com','vt.tiktok.com','m.tiktok.com',
            'instagram.com','ig.tv','facebook.com','fb.watch','fb.com'
        ]
        return any(d in url for d in domains)

    async def media_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        url = msg.text.strip()
        # Ignora messaggi non link supportati
        if not self.is_supported_video_link(url):
            return
        try:
            await msg.delete()
        except:
            pass
        # Download video
        loading = await context.bot.send_message(msg.chat_id, "⏳ Download in corso...")
        try:
            info = await self.downloader.download_video(url)
            if info['success']:
                with open(info['file_path'], 'rb') as f:
                    caption = f"🎬 Video da {info.get('uploader','')}"
                    await context.bot.send_video(
                        chat_id=msg.chat_id,
                        video=f,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                await loading.delete()
                os.remove(info['file_path'])
            else:
                await loading.edit_text(f"❌ Errore: {info['error']}")
        except Exception as e:
            logger.error(f"Download error: {e}")
            await loading.edit_text("❌ Errore durante il download.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Uso: invia link da TikTok, Instagram o Facebook per scaricare il video."
        )

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Error update {update}: {context.error}")

    def run(self):
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.media_handler))
        app.add_error_handler(self.error_handler)

        # Start webserver for health check
        loop = asyncio.get_event_loop()
        loop.create_task(self.start_webserver())
        app.run_polling(drop_pending_updates=True)

    async def start_webserver(self):
        port = int(os.getenv('PORT', '8080'))
        server = web.Application()
        server.add_routes([web.get('/', lambda r: web.Response(text="OK"))])
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()

if __name__ == '__main__':
    MultiPlatformBot().run()
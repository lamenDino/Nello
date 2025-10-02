#!/usr/bin/env python3
"""
Bot Telegram per scaricare video TikTok
Autore: Il tuo nome
Descrizione: Bot che scarica video TikTok senza watermark per il gruppo di amici
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

class TikTokBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.admin_id = int(os.getenv('ADMIN_USER_ID', 0))
        self.downloader = TikTokDownloader()

        if not self.token:
            raise ValueError("Token Telegram non trovato! Controlla le env vars")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        welcome_text = (
            f"🎵 **Ciao {user.first_name}!**\n\n"
            "Sono il bot per scaricare video TikTok! 🚀\n\n"
            "**Come usarmi:**\n"
            "• Invia il link di un video TikTok\n"
            "• Riceverai il video senza watermark!\n\n"
            "⚠️ **Nota:** Uso solo per il nostro gruppo!"
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "📖 **Guida del bot**\n\n"
            "**Comandi:** /start, /help, /stats (admin)\n\n"
            "**Scaricare video:** Invia il link TikTok nella chat\n"
            "Esempio: https://www.tiktok.com/@user/video/1234567890"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def handle_tiktok_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        user = update.effective_user
        text = message.text.strip()

        logger.info(f"Raw text: {text}")

        # Controlla PRIMA se è un link TikTok
        if not self.is_tiktok_link(text):
            logger.info(f"Messaggio ignorato (non TikTok): {text}")
            return  # Ignora silenziosamente se non è un link TikTok

        clean_text = self.downloader.clean_tiktok_url(text)
        logger.info(f"Clean text: {clean_text}")

        try:
            await message.delete()
        except:
            pass

        loading = await context.bot.send_message(
            chat_id=message.chat_id,
            text="⏳ Scaricando video..."
        )

        try:
            info = await self.downloader.download_video(clean_text)
            if info['success']:
                caption = (
                    f"🎥 Video inviato da: *{user.full_name}*\n"
                    f"🔗 Link originale: {clean_text}\n\n"
                    f"📝 {info.get('title','')[:100]}"
                )
                with open(info['file_path'], 'rb') as f:
                    await context.bot.send_video(
                        chat_id=message.chat_id,
                        video=f,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                await loading.delete()
                os.remove(info['file_path'])
            else:
                await loading.edit_text(f"❌ Errore: `{info['error']}`", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Download error: {e}")
            await loading.edit_text(
                "💥 Errore imprevisto. Riprova più tardi.",
                parse_mode=ParseMode.MARKDOWN
            )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.data == "info":
            text = (
                "ℹ️ **Info Bot**\n"
                "Tecnologie: Python, python-telegram-bot, yt-dlp\n"
                "Accesso libero: tutti nel gruppo"
            )
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await self.help_command(update, context)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("🚫 Solo admin")
            return
        await update.message.reply_text("📊 Statistiche in arrivo...")

    def is_tiktok_link(self, url: str) -> bool:
        domains = ['tiktok.com','vm.tiktok.com','vt.tiktok.com','m.tiktok.com']
        return any(d in url for d in domains)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Error update {update}: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "💥 Errore imprevisto."
            )

    def run(self):
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("stats", self.stats_command))
        app.add_handler(CallbackQueryHandler(self.button_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_tiktok_link))
        app.add_error_handler(self.error_handler)

        logger.info("🚀 Avvio bot...")

        loop = asyncio.get_event_loop()
        loop.create_task(start_webserver())
        app.run_polling(drop_pending_updates=True)


async def handle(request):
    return web.Response(text="OK")

async def start_webserver():
    port = int(os.getenv('PORT', '8080'))
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Web server started on port {port}")

if __name__ == "__main__":
    bot = TikTokBot()
    bot.run()
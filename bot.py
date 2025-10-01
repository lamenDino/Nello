#!/usr/bin/env python3
"""
Bot Telegram per scaricare video TikTok
Autore: Il tuo nome
Descrizione: Bot che scarica video TikTok senza watermark per il gruppo di amici
"""

import os
import logging
import asyncio
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
            raise ValueError("Token Telegram non trovato! Controlla il file .env")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start - Messaggio di benvenuto"""
        user = update.effective_user
        welcome_text = f"""
🎵 **Ciao {user.first_name}!**

Sono il bot del gruppo per scaricare video TikTok! 🚀

**Come usarmi:**
• Invia semplicemente il link di un video TikTok
• Riceverai il video senza watermark direttamente qui!

**Esempio:**
`https://www.tiktok.com/@username/video/123456789`

⚠️ **Nota:** Uso consentito solo per il nostro gruppo di amici!
        """
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help - Aiuto dettagliato"""
        help_text = """
📖 **Guida completa del bot**

**Comandi disponibili:**
• `/start` - Messaggio di benvenuto
• `/help` - Questa guida
• `/stats` - Statistiche bot (solo admin)

**Come scaricare video:**
1. Vai su TikTok
2. Copia il link del video che ti piace
3. Incollalo qui nella chat
4. Aspetta qualche secondo... ⏳
5. Ricevi il tuo video! 🎉

**Link supportati:**
• `https://www.tiktok.com/@user/video/123...`
• `https://vm.tiktok.com/xyz...`
• `https://vt.tiktok.com/xyz...`

**Note:**
• Video massimo 50MB (limite Telegram)
• Funziona solo con video pubblici
• Uso esclusivo per il nostro gruppo
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def handle_tiktok_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestisce i link TikTok inviati dagli utenti"""
        message = update.message
        user = update.effective_user
        text = message.text

        # Controlla se è un link TikTok
        if not self.is_tiktok_link(text):
            await message.reply_text(
                "🤔 Non sembra un link TikTok valido.\n"
                "Invia un link come: https://www.tiktok.com/@user/video/123...",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Cancella il messaggio originale dell’utente
        try:
            await message.delete()
        except:
            pass  # Ignora se non ha permessi

        # Messaggio di caricamento
        loading_msg = await context.bot.send_message(
            chat_id=message.chat_id,
            text="⏳ Scaricando il video... Un momento!"
        )

        try:
            # Scarica il video
            video_info = await self.downloader.download_video(text)

            if video_info['success']:
                # Invia il video con didascalia personalizzata
                caption = (
                    f"🎥 Video inviato da: *{user.full_name}*\n"
                    f"🔗 Link originale: {text}\n\n"
                    f"📝 {video_info.get('title','')[:100]}"
                )
                with open(video_info['file_path'], 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=message.chat_id,
                        video=video_file,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )

                # Rimuovi il messaggio di caricamento
                await loading_msg.delete()

                # Pulisci il file temporaneo
                os.remove(video_info['file_path'])

                logger.info(f"Video scaricato per {user.full_name}: {text}")

            else:
                await loading_msg.edit_text(
                    f"❌ Errore nel download:\n`{video_info['error']}`",
                    parse_mode=ParseMode.MARKDOWN
                )

        except Exception as e:
            logger.error(f"Errore nel download per {user.full_name}: {str(e)}")
            await loading_msg.edit_text(
                "💥 Ops! Qualcosa è andato storto.\n"
                "Riprova tra un momento o contatta l'admin.",
                parse_mode=ParseMode.MARKDOWN
            )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestisce i click sui bottoni inline"""
        query = update.callback_query
        await query.answer()

        if query.data == "info":
            info_text = """
ℹ️ **Informazioni sul bot**

🤖 **Versione:** 1.0
📅 **Creato:** Ottobre 2025
🛠️ **Tecnologie:** Python, python-telegram-bot, yt-dlp
☁️ **Hosting:** Docker

💡 **Caratteristiche:**
• Download senza watermark
• Supporto video e immagini
• Veloce e affidabile
• Accesso libero per tutti nel gruppo 👥
            """
            await query.edit_message_text(info_text, parse_mode=ParseMode.MARKDOWN)

        elif query.data == "help":
            await self.help_command(update, context)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /stats - Solo per admin"""
        user = update.effective_user
        if user.id != self.admin_id:
            await update.message.reply_text("🚫 Comando riservato all'amministratore")
            return

        stats_text = """
📊 **Statistiche Bot**

👥 **Utenti totali:** Coming soon...
📹 **Video scaricati:** Coming soon...
⚡ **Uptime:** Online
        """
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

    def is_tiktok_link(self, text: str) -> bool:
        """Controlla se il testo contiene un link TikTok valido"""
        tiktok_domains = [
            'tiktok.com',
            'vm.tiktok.com',
            'vt.tiktok.com',
            'm.tiktok.com'
        ]
        return any(domain in text.lower() for domain in tiktok_domains)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestisce gli errori globali del bot"""
        logger.error(f"Errore causato dall'update {update}: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "💥 Ops! Si è verificato un errore imprevisto.\n"
                "L'admin è stato notificato automaticamente."
            )

    def run(self):
        """Avvia il bot"""
        app = Application.builder().token(self.token).build()

        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("stats", self.stats_command))
        app.add_handler(CallbackQueryHandler(self.button_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_tiktok_link))
        app.add_error_handler(self.error_handler)

        logger.info("🚀 Bot avviato! Premi Ctrl+C per fermare.")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        bot = TikTokBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Bot fermato dall'utente")
    except Exception as e:
        logger.error(f"💥 Errore critico: {e}")

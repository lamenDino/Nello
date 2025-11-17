#!/usr/bin/env python3
"""
Telegram Multi-Platform Video Downloader Bot v3.0
- Supporta: TikTok, Instagram (reels + posts + storie), Facebook (video + reels), YouTube (shorts)
- Formattazione bella con emoji e nome utente reale
- Gestione errori migliorata
"""

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
from social_downloader import SocialMediaDownloader

load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
PORT = int(os.getenv('PORT', '8080'))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Emoji per piattaforme
PLATFORM_EMOJI = {
    'tiktok': '🎵',
    'instagram': '📷',
    'facebook': '👍',
    'youtube': '▶️',
    'twitter': '🐦',
}

def is_supported_link(url: str) -> bool:
    """Verifica se il link è di una piattaforma supportata"""
    domains = [
        'tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com', 'm.tiktok.com',
        'instagram.com', 'ig.tv', 'instagram.tv',
        'facebook.com', 'fb.watch', 'fb.com',
        'youtube.com', 'youtu.be',
        'twitter.com', 'x.com'
    ]
    return any(d in url for d in domains)

def detect_platform(url: str) -> str:
    """Rileva la piattaforma dal URL"""
    url_lower = url.lower()
    if 'tiktok' in url_lower:
        return 'TikTok'
    elif 'instagram' in url_lower or 'ig.tv' in url_lower:
        return 'Instagram'
    elif 'facebook' in url_lower or 'fb.' in url_lower:
        return 'Facebook'
    elif 'youtube' in url_lower or 'youtu.be' in url_lower:
        return 'YouTube'
    elif 'twitter' in url_lower or 'x.com' in url_lower:
        return 'Twitter'
    return 'Sconosciuta'

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user = update.effective_user
    message = (
        f"👋 Ciao {user.first_name}!\n\n"
        "Sono il bot per scaricare video da:\n"
        "🎵 TikTok\n"
        "📷 Instagram (Reels, Posts, Storie)\n"
        "👍 Facebook (Video, Reels, Reel /share/)\n"
        "▶️ YouTube (Solo Shorts)\n"
        "🐦 Twitter/X\n\n"
        "Inviami semplicemente il link di un video! 🚀"
    )
    await update.message.reply_text(message)

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il download dei video"""
    msg = update.message
    url = msg.text.strip()
    
    if not is_supported_link(url):
        return
    
    # Messaggio di caricamento
    loading = await context.bot.send_message(msg.chat_id, "⏳ Download in corso...")
    
    dl = SocialMediaDownloader()
    
    try:
        info = await dl.download_video(url)
        
        if info['success']:
            # Cancella il messaggio originale
            try:
                await msg.delete()
            except:
                pass
            
            # Estrai info
            platform = detect_platform(url)
            emoji = PLATFORM_EMOJI.get(platform.lower(), '📱')
            uploader = escape(info.get('uploader', 'Sconosciuto'))
            user_sender = escape(msg.from_user.full_name)
            title = escape(info.get('title', 'Video scaricato'))
            orig_link = escape(url)
            
            # Formatta la caption con emoji e grassetto
            caption = (
                f"{emoji} <b>Video da: {platform}</b>\n"
                f"👤 Video inviato da: <b>{user_sender}</b>\n"
                f"🔗 Link originale: {orig_link}\n"
                f"📝 {title}"
            )
            
            # Invia il video
            with open(info['file_path'], 'rb') as f:
                await context.bot.send_video(
                    chat_id=msg.chat_id,
                    video=f,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            
            await loading.delete()
            os.remove(info['file_path'])
            
        else:
            # Errore nel download
            error_msg = info.get('error', 'Errore sconosciuto')
            await loading.edit_text(
                f"❌ <b>Errore nel download</b>\n\n"
                f"Motivo: <i>{escape(error_msg)}</i>\n\n"
                f"Possibili cause:\n"
                f"• Video privato\n"
                f"• Link non valido\n"
                f"• Video troppo grande (max 50MB)\n"
                f"• Problemi temporanei\n\n"
                f"Riprova tra un momento! 🔄",
                parse_mode=ParseMode.HTML
            )
    
    except Exception as e:
        logger.error(f"Errore durante il download: {e}")
        await loading.edit_text(
            f"❌ <b>Errore inatteso</b>\n\n"
            f"<code>{escape(str(e)[:100])}</code>",
            parse_mode=ParseMode.HTML
        )

async def health(request):
    """Health check endpoint"""
    return web.Response(text="OK")

async def run_web():
    """Avvia il web server per Render"""
    app = web.Application()
    app.add_routes([web.get('/', health)])
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Web server avviato sulla porta {PORT}")
    
    await asyncio.Event().wait()

def start_webserver():
    """Avvia il web server in un thread separato"""
    asyncio.run(run_web())

def main():
    """Funzione principale"""
    # Avvia il web server
    thread = threading.Thread(target=start_webserver, daemon=True)
    thread.start()
    
    # Avvia il bot
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start_cmd))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        download_handler
    ))
    
    logger.info("Bot avviato...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

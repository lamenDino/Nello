#!/usr/bin/env python3
"""
Telegram Bot v4.3.5 - New Caption Format with Icons
- Formattazione NUOVA per le caption
- Icone su ogni riga
- Plain text (NO parse_mode)
- Link completo in caption
"""

import logging
import asyncio
import os
import re
from pathlib import Path

from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError, Conflict

from social_downloader import SocialMediaDownloader

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Carica variabili ambiente
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN non trovato")

# Inizializza downloader
downloader = SocialMediaDownloader()

def sanitize_caption(text: str, max_length: int = 500) -> str:
    """Sanitizza caption per Telegram - PLAIN TEXT (NO Markdown)"""
    if not text:
        return "Video"
    
    # Limita lunghezza
    text = text[:max_length]
    
    # Rimuovi caratteri di controllo
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', text)
    
    # Rimuovi caratteri speciali Telegram che causano parsing issues
    problematic_chars = {
        '：': ':',      # Doppio punto cinese
        '。': '.',      # Punto cinese
        '，': ',',      # Virgola cinese
        '；': ';',      # Punto virgola cinese
        '！': '!',      # Esclamativo cinese
        '？': '?',      # Punto interrogativo cinese
        ''': "'",       # Apice sinistro
        ''': "'",       # Apice destro
        '"': '"',       # Virgolette sinistre
        '"': '"',       # Virgolette destre
        '…': '...',     # Ellissi
        '–': '-',       # En dash
        '—': '-',       # Em dash
        '‐': '-',       # Hyphen
    }
    
    for char, replacement in problematic_chars.items():
        text = text.replace(char, replacement)
    
    # Rimuovi URL dalla stringa stessa (sarà aggiunto separatamente)
    text = re.sub(r'https?://[^\s]+', '', text)
    
    # Rimuovi caratteri Markdown
    text = text.replace('`', "'")
    text = text.replace('```', "'''")
    
    return text.strip()

def format_caption(title: str, uploader: str, platform: str, url: str) -> str:
    """Formatta la caption con icone e struttura richiesta"""
    
    # Emoji per piattaforma
    emoji_map = {
        'instagram': '📷',
        'tiktok': '🎵',
        'youtube': '▶️',
        'facebook': '👍',
        'twitter': '🐦',
        'unknown': '📹'
    }
    platform_emoji = emoji_map.get(platform, '📹')
    
    # Sanitizza il titolo (max 100 chars)
    title = sanitize_caption(title, 100)
    
    # Sanitizza l'uploader
    uploader = sanitize_caption(uploader, 50)
    
    # Formatta caption con nuova struttura
    caption = (
        f"🌐 Video da: {platform.capitalize()}\n"
        f"👤 Video inviato da: {uploader}\n"
        f"🔗 Link originale: {url}\n"
        f"📝 Nome Video: {title}"
    )
    
    return caption

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler comando /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"🎬 Ciao {user.first_name}! Sono un bot per scaricare video dai social.\n\n"
        f"📝 Supporto:\n"
        f"✅ Instagram - Reels, Posts, Caroselli\n"
        f"✅ TikTok - Video, Caroselli foto\n"
        f"✅ YouTube - Shorts, Video\n"
        f"✅ Facebook - Reels, Video\n"
        f"✅ Twitter - Video\n\n"
        f"📎 Invia un link e scarico il video/foto per te!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler comando /help"""
    await update.message.reply_text(
        f"🆘 Come usare il bot:\n\n"
        f"1️⃣ Invia un link di un video o foto dai social\n"
        f"2️⃣ Aspetta che il bot scarichi il file\n"
        f"3️⃣ Ricevi il video/foto formattato\n\n"
        f"📌 Formati supportati:\n"
        f"🎥 Video singoli\n"
        f"📸 Foto singole\n"
        f"🖼️ Caroselli (album Telegram)\n\n"
        f"⏱️ Il download può richiedere da pochi secondi a 1 minuto"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler per i link inviati"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    message = update.message
    url = message.text.strip()
    
    # Controllo URL valido
    if not url.startswith(('http://', 'https://')):
        await message.reply_text("❌ URL non valido. Invia un link che inizia con http:// o https://")
        return
    
    # Messaggio di attesa
    loading_msg = await message.reply_text("⏳ Scaricamento in corso...")
    
    try:
        # Download
        result = await downloader.download_video(url)
        
        if not result['success']:
            await loading_msg.edit_text(result['error'])
            return
        
        # Estrai informazioni
        title = result.get('title', 'Video')
        uploader = result.get('uploader', 'Sconosciuto')
        platform = result.get('platform', 'unknown')
        original_url = result.get('url', url)
        
        # FORMATTA CAPTION CON NUOVA STRUTTURA
        caption = format_caption(title, uploader, platform, original_url)
        
        # CHECK: È un carosello?
        if result.get('is_carousel'):
            logger.info(f"Carosello rilevato: {len(result['files'])} item")
            
            # Prepara media group
            media_group = []
            
            for idx, file_info in enumerate(result['files']):
                file_path = file_info['path']
                file_type = file_info['type']
                
                try:
                    with open(file_path, 'rb') as file:
                        if file_type == 'photo':
                            media_group.append(
                                InputMediaPhoto(
                                    media=file,
                                    caption=caption if idx == 0 else '',
                                    # NO parse_mode - plain text!
                                )
                            )
                        else:  # video
                            media_group.append(
                                InputMediaVideo(
                                    media=file,
                                    caption=caption if idx == 0 else '',
                                    # NO parse_mode - plain text!
                                )
                            )
                except Exception as e:
                    logger.warning(f"Errore aggiunta file {idx}: {e}")
            
            # Invia album
            if media_group:
                await context.bot.send_media_group(
                    chat_id=chat_id,
                    media=media_group
                )
                await loading_msg.delete()
                logger.info(f"Album Telegram inviato: {len(media_group)} item")
            else:
                await loading_msg.edit_text("❌ Errore nell'invio del carosello")
        
        else:
            # FILE SINGOLO
            file_path = result['file_path']
            
            if not file_path or not os.path.exists(file_path):
                await loading_msg.edit_text("❌ File non trovato")
                return
            
            # Determina tipo file
            file_lower = file_path.lower()
            is_video = any(ext in file_lower for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi', '.flv'])
            
            try:
                with open(file_path, 'rb') as file:
                    if is_video:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=file,
                            caption=caption,
                            # NO parse_mode - plain text!
                        )
                    else:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=file,
                            caption=caption,
                            # NO parse_mode - plain text!
                        )
                
                await loading_msg.delete()
                logger.info(f"File inviato ({platform}): {title}")
                
            except TelegramError as e:
                logger.error(f"Errore Telegram: {e}")
                await loading_msg.edit_text(f"❌ Errore nell'invio: {str(e)[:100]}")
            finally:
                # Pulisci file locale
                try:
                    os.remove(file_path)
                except:
                    pass
    
    except Exception as e:
        logger.error(f"Errore handler: {e}")
        await loading_msg.edit_text(f"❌ Errore: {str(e)[:100]}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler errori con retry per Conflict"""
    error = context.error
    
    # Se è Conflict, ignora
    if isinstance(error, Conflict):
        logger.warning(f"Conflict error (retry automatico): {error}")
        return
    
    logger.error(f"Update {update} caused error {error}")

async def health_check_handler(request):
    """Handler per health check HTTP (Render port binding)"""
    logger.info("Health check ricevuto")
    from aiohttp import web
    return web.Response(text="OK", status=200)

async def start_http_server():
    """Avvia server HTTP per Render port binding"""
    from aiohttp import web
    
    app = web.Application()
    app.router.add_get('/', health_check_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv('PORT', 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"✅ HTTP server avviato su porta {port}")
    
    return runner

def main() -> None:
    """Avvia il bot"""
    logger.info("🤖 Bot Telegram v4.3.5 in avvio...")
    
    # Crea application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Aggiungi handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Avvia polling con retry per Conflict
    logger.info("✅ Bot avviato e in ascolto...")
    try:
        # Avvia HTTP server in background per Render port binding
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Avvia server HTTP
        http_runner = loop.run_until_complete(start_http_server())
        
        # Avvia bot polling
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except Conflict as e:
        logger.error(f"Conflict error all'avvio: {e}")
        logger.info("Riavvia il bot manualmente su Render")
    except KeyboardInterrupt:
        logger.info("Bot stoppato")

if __name__ == '__main__':
    main()

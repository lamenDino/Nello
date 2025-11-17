#!/usr/bin/env python3
"""
Telegram Bot v4.0 - Social Media Downloader
- Supporto caroselli Instagram/TikTok
- Album Telegram per caroselli
- Formattazione con emoji + nome utente
- Video/foto da tutti i social
"""

import logging
import asyncio
import os
from pathlib import Path

from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

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
    raise ValueError("BOT_TOKEN non trovato nelle variabili ambiente")

# Inizializza downloader
downloader = SocialMediaDownloader()

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
        
        # Formattazione messaggio
        caption = (
            f"{platform_emoji} **Video da: {platform.capitalize()}**\n"
            f"👤 Video inviato da: **{uploader}**\n"
            f"🔗 Link originale: {url}\n"
            f"📝 Titolo: {title[:100]}"
        )
        
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
                            # Aggiungi caption solo al primo item
                            media_group.append(
                                InputMediaPhoto(
                                    media=file,
                                    caption=caption if idx == 0 else '',
                                    parse_mode='Markdown'
                                )
                            )
                        else:  # video
                            media_group.append(
                                InputMediaVideo(
                                    media=file,
                                    caption=caption if idx == 0 else '',
                                    parse_mode='Markdown'
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
                            parse_mode='Markdown'
                        )
                    else:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=file,
                            caption=caption,
                            parse_mode='Markdown'
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
    """Handler errori"""
    logger.error(f"Update {update} caused error {context.error}")

def main() -> None:
    """Avvia il bot"""
    logger.info("🤖 Bot Telegram v4.0 in avvio...")
    
    # Crea application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Aggiungi handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Avvia polling
    logger.info("✅ Bot avviato e in ascolto...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

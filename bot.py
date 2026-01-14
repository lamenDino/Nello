#!/usr/bin/env python3
"""
NELLO BOT v5.0 - COMPLETO
✅ Cancella messaggio utente
✅ Icone e metadata nel video
✅ Cancellazione errori automatica (silenzioso)
✅ 3 retry automatici (già in social_downloader)
✅ Ranking settimanale (sabato 20:30)
✅ Senza job_queue (usa APScheduler nativo di PTB)
"""

import os
import sys
import logging
import asyncio
import threading
from datetime import datetime, time
from aiohttp import web
from telegram import Update, ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import config e downloader
sys.path.insert(0, os.path.dirname(__file__))
from config import TOKEN, PORT, CHAT_ID, RANKING_ENABLED
from social_downloader import SocialMediaDownloader

# Inizializza downloader
downloader = SocialMediaDownloader()

# Variabile globale per il tracking dei download
download_stats = {
    'youtube': 0,
    'tiktok': 0,
    'instagram': 0,
    'facebook': 0,
    'twitter': 0,
    'unknown': 0
}

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    await update.message.reply_text(
        "🎬 Benvenuto! Invia un link da:\n"
        "• YouTube\n"
        "• TikTok\n"
        "• Instagram\n"
        "• Facebook\n\n"
        "Ti invierò il video scaricato! 🚀"
    )

async def send_weekly_ranking(context: ContextTypes.DEFAULT_TYPE):
    """Invia il ranking settimanale"""
    try:
        if not RANKING_ENABLED or not CHAT_ID:
            return
        
        # Calcola il ranking
        total = sum(download_stats.values())
        if total == 0:
            return
        
        ranking_text = (
            f"📊 <b>RANKING SETTIMANALE</b>\n\n"
            f"🎬 <b>YouTube:</b> {download_stats['youtube']}\n"
            f"🎵 <b>TikTok:</b> {download_stats['tiktok']}\n"
            f"📸 <b>Instagram:</b> {download_stats['instagram']}\n"
            f"👥 <b>Facebook:</b> {download_stats['facebook']}\n"
            f"𝕏 <b>Twitter:</b> {download_stats['twitter']}\n\n"
            f"📈 <b>TOTALE:</b> {total} download\n\n"
            f"🏆 La piattaforma più scaricata: <b>{max(download_stats, key=download_stats.get).upper()}</b>"
        )
        
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=ranking_text,
            parse_mode=ParseMode.HTML
        )
        
        # Resetta i contatori
        for key in download_stats:
            download_stats[key] = 0
        
        logger.info("✅ Ranking settimanale inviato")
    
    except Exception as e:
        logger.error(f"Errore invio ranking: {e}")

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i link mandati dagli utenti"""
    
    if not update.message or not update.message.text:
        return
    
    url = update.message.text.strip()
    
    # Valida URL
    if not any(x in url.lower() for x in ['youtube', 'youtu.be', 'tiktok', 'instagram', 'facebook', 'ig.tv', 'fb.', 'twitter', 'x.com']):
        # Cancella messaggio silenziosamente
        try:
            await update.message.delete()
        except:
            pass
        return
    
    # Cancella il messaggio dell'utente (il link)
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Non posso cancellare: {e}")
    
    # Invia messaggio "sto scaricando"
    status_msg = await update.message.reply_text("⏳ Sto scaricando... attendi un momento")
    
    try:
        # Scarica il video con retry (retry già incluso in social_downloader)
        result = await downloader.download_video(url)
        
        if not result.get('success'):
            # Cancella messaggio di errore silenziosamente dopo 3 secondi
            try:
                await asyncio.sleep(3)
                await status_msg.delete()
            except:
                pass
            return
        
        # Estrai info
        file_path = result.get('file_path')
        title = result.get('title', 'Video').strip()
        uploader = result.get('uploader', 'Sconosciuto').strip()
        duration = result.get('duration', 0)
        platform = result.get('platform', 'unknown').lower()
        original_url = result.get('url', url)
        
        # Incrementa statistiche
        if platform in download_stats:
            download_stats[platform] += 1
        
        # Formatta durata
        if duration:
            mins = int(duration) // 60
            secs = int(duration) % 60
            duration_str = f"{mins}:{secs:02d}"
        else:
            duration_str = "N/A"
        
        # Crea caption con icone
        caption = (
            f"🎬 <b>{title}</b>\n\n"
            f"📺 <b>Canale:</b> {uploader}\n"
            f"⏱️ <b>Durata:</b> {duration_str}\n"
            f"🔗 <b>Piattaforma:</b> {platform.upper()}\n\n"
            f"🔗 <a href=\"{original_url}\">Link Originale</a>"
        )
        
        # Invia il video
        if os.path.exists(file_path):
            with open(file_path, 'rb') as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            
            # Cancella il messaggio di status
            try:
                await status_msg.delete()
            except:
                pass
            
            # Pulisci file temporaneo
            try:
                os.remove(file_path)
            except:
                pass
        else:
            # File non trovato - cancella status silenziosamente
            try:
                await asyncio.sleep(2)
                await status_msg.delete()
            except:
                pass
    
    except Exception as e:
        logger.error(f"Errore download: {str(e)[:200]}")
        # Cancella il messaggio di status silenziosamente
        try:
            await asyncio.sleep(2)
            await status_msg.delete()
        except:
            pass

# Web server per health check
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
    # Avvia web server
    thread = threading.Thread(target=start_webserver, daemon=True)
    thread.start()
    logger.info("Web server avviato in background")
    
    # Avvia bot
    application = Application.builder().token(TOKEN).build()
    
    # Handler
    application.add_handler(CommandHandler('start', start_cmd))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        download_handler
    ))
    
    # Job queue per ranking settimanale
    if RANKING_ENABLED and CHAT_ID:
        try:
            job_queue = application.job_queue
            
            # Schedula ranking ogni sabato alle 20:30
            job_queue.run_daily(
                callback=send_weekly_ranking,
                time=time(hour=20, minute=30),
                days=(5,),  # 5 = sabato
                name='weekly_ranking'
            )
            logger.info("✅ Ranking settimanale pianificato (sabato 20:30)")
        except Exception as e:
            logger.warning(f"⚠️ Job queue disabilitato: {e}")
    else:
        logger.info("⚠️ Ranking disabilitato (manca CHAT_ID)")
    
    logger.info("✅ Web server avviato sulla porta 8080")
    logger.info("🤖 Bot Telegram avviato...")
    
    # Polling
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=[]
    )

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Bot Telegram - Downloader Video Social Media
Con retry automatici, pulizia messaggi errore, e ranking settimanale

Features:
- Download da YouTube, TikTok, Instagram, Facebook, Twitter
- Retry automatici (3 tentativi) con backoff esponenziale
- Cancellazione automatica messaggi di errore intermedi
- Ranking settimanale (ogni sabato 20:30) con top 3 utenti
"""

import os
import logging
import asyncio
import threading
from datetime import datetime, time, timedelta
from collections import defaultdict
from html import escape
from aiohttp import web

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import TOKEN, CHAT_ID
from social_downloader import SocialMediaDownloader

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get('PORT', 8443))

# ===== DATABASE IN MEMORIA PER RANKING =====
user_downloads = defaultdict(int)  # {user_id: count}
user_names = {}  # {user_id: username}

# Aforismi sulla vita
AFORISMI = [
    "La vita è 10% ciò che ti accade e 90% come reagisci. 💪",
    "Il successo è la somma di piccoli sforzi ripetuti. 🎯",
    "Non attendere il momento perfetto, agisci nel momento presente. ⚡",
    "La perfezione è il nemico del bene. Inizia oggi! 🚀",
    "Ogni grande viaggio inizia con un primo passo. 👣",
    "Il tuo unico limite sei tu stesso. 🌟",
    "La dedizione è ciò che trasforma i sogni in realtà. 💎",
    "Non è il fine che nobilita i mezzi, ma sono i mezzi che nobilitano il fine. ✨",
    "La vera ricchezza è avere tempo per le cose che ami. ❤️",
    "La motivazione ti mette in movimento, l'abitudine ti tiene in movimento. 🔥",
    "Sii il cambiamento che vuoi vedere nel mondo. 🌍",
    "La felicità non è una destinazione, è il percorso. 🛤️",
    "Ogni giorno è una nuova opportunità di essere migliore. 📈",
    "Il coraggio è affrontare le cose che hai paura di fare. 🦁",
    "La pazienza è la virtù di chi sa attendere il giusto momento. ⏳"
]


# ===== FUNZIONI DI UTILITY =====

async def safe_delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int, delay: int = 2):
    """Cancella un messaggio dopo un breve delay"""
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=message_id
        )
        logger.debug(f"Messaggio {message_id} cancellato")
    except Exception as e:
        logger.debug(f"Impossibile cancellare messaggio {message_id}: {str(e)}")


def get_random_aforisma() -> str:
    """Ritorna un aforisma casuale"""
    import random
    return random.choice(AFORISMI)


async def track_download(update: Update, user_id: int = None):
    """Traccia i download per l'utente"""
    if user_id is None:
        user_id = update.effective_user.id
    
    user_downloads[user_id] += 1
    if user_id not in user_names:
        user_names[user_id] = update.effective_user.username or update.effective_user.first_name
    
    logger.info(f"Download tracciato: {user_names[user_id]} (totale: {user_downloads[user_id]})")


async def get_top_3_users() -> list:
    """Ritorna i top 3 utenti per numero di download"""
    sorted_users = sorted(user_downloads.items(), key=lambda x: x[1], reverse=True)
    return sorted_users[:3]


async def send_weekly_ranking(context: ContextTypes.DEFAULT_TYPE):
    """Invia il ranking settimanale ogni sabato alle 20:30"""
    try:
        logger.info("Invio ranking settimanale...")
        
        if not user_downloads:
            logger.info("Nessun download questa settimana")
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text="📊 <b>RANKING SETTIMANALE</b>\n\n"
                     "Nessun download questa settimana. 😴\n\n"
                     "Incoraggia i tuoi amici a mandare link! 🚀",
                parse_mode=ParseMode.HTML
            )
            return
        
        top_3 = await get_top_3_users()
        
        # Costruisci il messaggio
        medals = ["🥇", "🥈", "🥉"]
        message = "<b>🏆 RANKING SETTIMANALE 🏆</b>\n\n"
        message += "Ecco i 3 downloader più attivi della settimana:\n\n"
        
        for idx, (user_id, count) in enumerate(top_3):
            username = user_names.get(user_id, f"Utente {user_id}")
            medal = medals[idx]
            message += f"{medal} <b>{username}</b> - <code>{count} download</code>\n"
        
        # Aggiungi aforisma per il vincitore
        if top_3:
            winner_id = top_3[0][0]
            winner_name = user_names.get(winner_id, f"Utente {winner_id}")
            aforisma = get_random_aforisma()
            
            message += f"\n{'='*50}\n\n"
            message += f"🎉 <b>Congratulazioni a @{winner_name}!</b>\n"
            message += f"Sei il downloader più attivo della settimana!\n\n"
            message += f"<i>{aforisma}</i>\n\n"
            message += f"Continua così! 💪"
        
        # Invia il messaggio
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML
        )
        
        # Azzera i contatori per la prossima settimana
        user_downloads.clear()
        user_names.clear()
        logger.info("Ranking inviato. Contatori azzerati.")
        
    except Exception as e:
        logger.error(f"Errore nell'invio ranking: {str(e)}")


async def schedule_weekly_ranking(application: Application):
    """Pianifica l'invio del ranking ogni sabato alle 20:30"""
    while True:
        try:
            now = datetime.now()
            
            # Calcola il prossimo sabato alle 20:30
            # 0=lunedì, 5=sabato
            days_until_saturday = (5 - now.weekday()) % 7
            
            if days_until_saturday == 0:
                # Oggi è sabato
                target_time = time(20, 30, 0)
                if now.time() < target_time:
                    # Non è ancora passata l'ora oggi
                    target_datetime = datetime.combine(now.date(), target_time)
                else:
                    # È già passata, attendi al prossimo sabato
                    target_datetime = datetime.combine(
                        now.date() + timedelta(days=7),
                        target_time
                    )
            else:
                # Calcola il prossimo sabato
                target_datetime = datetime.combine(
                    now.date() + timedelta(days=days_until_saturday),
                    time(20, 30, 0)
                )
            
            wait_seconds = (target_datetime - now).total_seconds()
            hours_wait = wait_seconds / 3600
            logger.info(f"Prossimo ranking tra {hours_wait:.1f} ore ({target_datetime})")
            
            await asyncio.sleep(wait_seconds)
            
            # Invia il ranking
            await send_weekly_ranking(application)
            
            # Attendi un minuto per evitare duplicati
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Errore scheduling ranking: {str(e)}")
            await asyncio.sleep(3600)  # Riprova tra 1 ora


# ===== COMMAND HANDLERS =====

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    message = """
👋 <b>Benvenuto nel Bot Downloader Video!</b>

Semplicemente invia un link da una di queste piattaforme:
🎬 YouTube / YouTube Shorts
🎵 TikTok
📸 Instagram Reels
👍 Facebook Reels
𝕏 Twitter / X

Il bot scaricherà il video e te lo invierà!

<i>Funzioni speciali:</i>
• ♻️ Retry automatici (3 tentativi)
• 🗑️ Pulizia automatica messaggi di errore
• 🏆 Ranking settimanale (ogni sabato 20:30)
"""
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    logger.info(f"Nuovo utente: {update.effective_user.first_name}")


async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principale per i download con retry e pulizia messaggi"""
    user_message = update.message.text.strip()
    user_id = update.effective_user.id
    
    try:
        # Valida URL
        valid_platforms = ['youtube', 'tiktok', 'instagram', 'facebook', 'twitter', 'youtu.be', 'x.com']
        if not any(platform in user_message.lower() for platform in valid_platforms):
            error_msg = await update.message.reply_text(
                "❌ <b>URL non valido.</b> Invia un link da:\n\n"
                "🎬 YouTube / YouTube Shorts\n"
                "🎵 TikTok\n"
                "📸 Instagram Reels\n"
                "👍 Facebook Reels\n"
                "𝕏 Twitter / X",
                parse_mode=ParseMode.HTML,
                reply_to_message_id=update.message.message_id
            )
            # Cancella messaggio di errore dopo 8 secondi
            asyncio.create_task(safe_delete_message(update, context, error_msg.message_id, delay=8))
            return

        # Messaggio di caricamento
        loading_msg = await update.message.reply_text(
            "⏳ <b>Sto scaricando il video...</b>",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id
        )

        # ===== RETRY LOOP =====
        downloader = SocialMediaDownloader()
        result = None
        last_error = None
        
        for attempt in range(3):  # 3 tentativi
            try:
                logger.info(f"Tentativo {attempt + 1}/3 per: {user_message[:60]}")
                
                # Aggiorna messaggio status
                await loading_msg.edit_text(
                    f"⏳ <b>Sto scaricando il video...</b>\n"
                    f"<i>Tentativo {attempt + 1}/3</i>",
                    parse_mode=ParseMode.HTML
                )
                
                # Chiama il downloader
                result = await downloader.download_video(user_message)
                
                # Se successo, esci dal loop
                if result.get('success'):
                    logger.info(f"✅ Download riuscito al tentativo {attempt + 1}")
                    break
                else:
                    last_error = result.get('error', 'Errore sconosciuto')
                    logger.warning(f"Tentativo {attempt + 1} fallito: {last_error}")
                    
                    # Non è l'ultimo tentativo, attendi prima di riprovare
                    if attempt < 2:  # 0, 1 → ci sono ancora tentativi
                        wait_time = 2 * (2 ** attempt)  # 2, 4, 8 secondi
                        logger.info(f"Attesa {wait_time}s prima del tentativo {attempt + 2}")
                        await asyncio.sleep(wait_time)
            
            except Exception as e:
                logger.error(f"Tentativo {attempt + 1} eccezione: {str(e)[:200]}")
                last_error = str(e)[:150]
                if attempt < 2:
                    wait_time = 2 * (2 ** attempt)
                    await asyncio.sleep(wait_time)
        
        # ===== GESTIONE RISULTATO =====
        if result and result.get('success'):
            # ✅ Successo - cancella messaggio di caricamento
            try:
                await loading_msg.delete()
            except:
                pass
            
            # Invia il video
            file_path = result.get('file_path')
            title = result.get('title', 'Video')
            uploader = result.get('uploader', 'Sconosciuto')
            platform = result.get('platform', 'sconosciuto').upper()
            
            caption = f"<b>{title[:100]}</b>\n\n" \
                     f"📱 <b>Piattaforma:</b> {platform}\n" \
                     f"👤 <b>Autore:</b> {uploader[:50]}"
            
            try:
                with open(file_path, 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=update.message.message_id
                    )
                
                # Pulisci file
                try:
                    os.remove(file_path)
                except:
                    pass
                
                logger.info(f"✅ Video inviato con successo")
                
                # Traccia il download
                await track_download(update, user_id)
            
            except Exception as e:
                error_msg = await update.message.reply_text(
                    f"❌ <b>Errore nell'invio del video:</b>\n\n<code>{escape(str(e)[:200])}</code>",
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=update.message.message_id
                )
                asyncio.create_task(safe_delete_message(update, context, error_msg.message_id, delay=12))
        
        else:
            # ❌ Fallimento dopo tutti i tentativi - cancella messaggio di caricamento
            try:
                await loading_msg.delete()
            except:
                pass
            
            error_message = result.get('error', last_error) if result else last_error
            
            # Invia messaggio di errore FINALE
            error_msg = await update.message.reply_text(
                f"❌ <b>Download fallito:</b>\n\n{error_message}",
                parse_mode=ParseMode.HTML,
                reply_to_message_id=update.message.message_id
            )
            
            # Cancella il messaggio di errore dopo 12 secondi
            asyncio.create_task(safe_delete_message(update, context, error_msg.message_id, delay=12))
    
    except Exception as e:
        logger.error(f"Errore handler: {str(e)}")
        try:
            await loading_msg.delete()
        except:
            pass


# ===== HEALTH CHECK =====

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


# ===== MAIN =====

def main():
    """Funzione principale"""
    # Avvia il web server
    thread = threading.Thread(target=start_webserver, daemon=True)
    thread.start()
    logger.info("Web server avviato in background")

    # Avvia il bot
    application = Application.builder().token(TOKEN).build()
    
    # Aggiungi command handler
    application.add_handler(CommandHandler('start', start_cmd))
    
    # Aggiungi message handler per i link
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        download_handler
    ))
    
    # Pianifica il ranking settimanale
    application.post_init = lambda app: asyncio.create_task(schedule_weekly_ranking(app))
    
    logger.info("🤖 Bot Telegram avviato...")
    logger.info("⏰ Ranking settimanale pianificato per ogni sabato alle 20:30")
    
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()

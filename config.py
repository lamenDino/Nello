"""
File di configurazione per il bot TikTok
"""

import os
from dotenv import load_dotenv

# Carica le variabili d'ambiente
load_dotenv()

# Configurazioni bot
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))

# Configurazioni TikTok downloader
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (limite Telegram)
MAX_VIDEO_DURATION = 600  # 10 minuti massimo
TEMP_DIR = os.getenv('TEMP_DIR', '/tmp')

# Configurazioni logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'bot.log')

# Lista degli utenti autorizzati (IDs Telegram)
# Lascia vuoto [] per permettere a tutti, oppure aggiungi gli ID degli amici
AUTHORIZED_USERS = [
    # 123456789,  # ID Telegram del primo amico
    # 987654321,  # ID Telegram del secondo amico
    # Aggiungi altri ID qui...
]

# Se la lista è vuota, il bot sarà accessibile a tutti
ALLOW_ALL_USERS = len(AUTHORIZED_USERS) == 0

# Configurazioni rate limiting
MAX_DOWNLOADS_PER_USER_PER_HOUR = 10
RATE_LIMIT_ENABLED = True

# Messaggi personalizzati
WELCOME_MESSAGE = """
🎵 **Ciao {name}!** 

Sono il bot del gruppo per scaricare video TikTok! 🚀

**Come usarmi:**
• Invia semplicemente il link di un video TikTok
• Riceverai il video senza watermark direttamente qui!

⚠️ **Nota:** Uso consentito solo per il nostro gruppo di amici!
"""

UNAUTHORIZED_MESSAGE = """
🚫 **Accesso negato**

Questo bot è riservato solo al nostro gruppo di amici.
Se pensi che ci sia un errore, contatta l'amministratore.
"""

ERROR_MESSAGE = """
💥 Ops! Qualcosa è andato storto.

Possibili cause:
• Video privato o non disponibile
• Link non valido
• Video troppo grande (max 50MB)
• Problemi temporanei di rete

Riprova tra un momento! 🔄
"""

# Configurazioni deployment
PORT = int(os.getenv('PORT', 8080))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
USE_WEBHOOK = bool(WEBHOOK_URL)

# Configurazioni database (opzionale, per statistiche future)
DATABASE_URL = os.getenv('DATABASE_URL', '')
USE_DATABASE = bool(DATABASE_URL)

def validate_config():
    """Valida la configurazione all'avvio"""
    errors = []
    
    if not BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN mancante")
    
    if not ADMIN_USER_ID:
        errors.append("ADMIN_USER_ID mancante")
    
    if errors:
        raise ValueError(f"Errori di configurazione: {', '.join(errors)}")
    
    return True
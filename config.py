#!/usr/bin/env python3
"""
Configurazione Bot Telegram Downloader Video - VERSIONE RENDER COMPATIBLE

Compatibile con le variabili d'ambiente di Render:
- TELEGRAM_BOT_TOKEN
- ADMIN_USER_ID (facoltativo, per admin)
- PORT (facoltativo, default 8443)
- CHAT_ID (per ranking settimanale)
"""

import os
from dotenv import load_dotenv

# Carica variabili da .env (per testing locale)
load_dotenv()

# ===== CONFIGURAZIONI TELEGRAM =====
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))

# CHAT_ID dove inviare il ranking (se non impostato, disabilita ranking)
CHAT_ID = os.getenv('CHAT_ID', '')
if CHAT_ID:
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        CHAT_ID = None
        print("⚠️ CHAT_ID non è un numero valido. Ranking disabilitato.")
else:
    CHAT_ID = None
    print("⚠️ CHAT_ID non configurato. Ranking disabilitato.")

# Validazione token
if not TOKEN:
    print("⚠️ AVVISO: TELEGRAM_BOT_TOKEN non configurato!")
    print("   Imposta la variabile d'ambiente TELEGRAM_BOT_TOKEN")
    # Non lanciare errore, permetti comunque l'avvio per debugging

# ===== CONFIGURAZIONI PORT =====
PORT = int(os.getenv('PORT', 8443))

# ===== CONFIGURAZIONI DOWNLOAD =====
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_VIDEO_DURATION = 600  # 10 minuti
TIMEOUT_DOWNLOAD = 120  # 120 secondi

# ===== CONFIGURAZIONI RETRY =====
MAX_RETRIES = 3
RETRY_DELAY = 2

# ===== CONFIGURAZIONI RANKING SETTIMANALE =====
RANKING_ENABLED = bool(CHAT_ID)  # Abilita solo se CHAT_ID è configurato
RANKING_DAY = 5  # 0=lunedì, 5=sabato
RANKING_TIME = (20, 30)  # Ore, minuti

# ===== CONFIGURAZIONI LOGGING =====
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'bot.log')

# ===== DIRECTORY TEMPORANEA =====
TEMP_DIR = os.getenv('TEMP_DIR', '/tmp')
os.makedirs(TEMP_DIR, exist_ok=True)

# ===== AUTORIZZAZIONE UTENTI =====
# Lascia vuoto per permettere a TUTTI
# Oppure aggiungi gli ID dei tuoi amici per uso ristretto
AUTHORIZED_USERS = [
    # Esempi:
    # 123456789,
    # 987654321,
]
ALLOW_ALL_USERS = len(AUTHORIZED_USERS) == 0

# ===== RATE LIMITING =====
MAX_DOWNLOADS_PER_USER_PER_HOUR = 20  # 20 download per utente/ora
RATE_LIMIT_ENABLED = False  # Disabilitato di default

# ===== MESSAGGI PERSONALIZZATI =====
WELCOME_MESSAGE = """
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

UNAUTHORIZED_MESSAGE = """
🚫 <b>Accesso negato</b>

Questo bot è riservato solo a utenti autorizzati.

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

# ===== FUNZIONI UTILITÀ =====

def validate_config():
    """Valida la configurazione all'avvio"""
    errors = []
    
    if not TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN mancante")
        print("❌ ERRORE: TELEGRAM_BOT_TOKEN non configurato!")
        print("   Su Render.com: Aggiungi la variabile d'ambiente TELEGRAM_BOT_TOKEN")
    
    if not RANKING_ENABLED:
        print("⚠️  AVVISO: Ranking settimanale DISABILITATO (CHAT_ID non configurato)")
        print("   Per abilitarlo, aggiungi CHAT_ID nelle variabili d'ambiente di Render")
    
    if errors:
        raise ValueError(f"Configurazione incompleta: {', '.join(errors)}")
    
    return True


def print_config():
    """Stampa la configurazione attuale (per debugging)"""
    print("\n" + "="*60)
    print("📋 CONFIGURAZIONE CARICATA")
    print("="*60)
    print(f"✅ TOKEN: {'✓ Configurato' if TOKEN else '✗ NON configurato'}")
    print(f"✅ CHAT_ID: {CHAT_ID if CHAT_ID else '✗ NON configurato (ranking disabilitato)'}")
    print(f"✅ ADMIN_USER_ID: {ADMIN_USER_ID if ADMIN_USER_ID else '✗ Non impostato'}")
    print(f"✅ PORT: {PORT}")
    print(f"✅ MAX_RETRIES: {MAX_RETRIES}")
    print(f"✅ RETRY_DELAY: {RETRY_DELAY}s")
    print(f"✅ RANKING: {'✓ Abilitato' if RANKING_ENABLED else '✗ Disabilitato'}")
    print(f"✅ LOG_LEVEL: {LOG_LEVEL}")
    print(f"✅ ALLOW_ALL_USERS: {ALLOW_ALL_USERS}")
    print("="*60 + "\n")


# ===== ESECUZIONE ALL'IMPORT =====
if __name__ == '__main__':
    print_config()
    try:
        validate_config()
        print("✅ Configurazione valida!")
    except ValueError as e:
        print(f"❌ {e}")
        exit(1)

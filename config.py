#!/usr/bin/env python3
"""
File di configurazione per NELLO BOT v5.0
Variabili d'ambiente + configurazioni locali
"""

import os
from dotenv import load_dotenv

# Carica le variabili d'ambiente
load_dotenv()

# ============================================
# CONFIGURAZIONI BOT TELEGRAM
# ============================================

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TOKEN')
PORT = int(os.getenv('PORT', 8080))

# ID chat per ranking settimanale (es: il tuo ID chat privata)
CHAT_ID = os.getenv('CHAT_ID')
if CHAT_ID:
    try:
        CHAT_ID = int(CHAT_ID)
    except:
        CHAT_ID = None

# Abilita ranking settimanale (richiede CHAT_ID)
RANKING_ENABLED = bool(CHAT_ID and os.getenv('RANKING_ENABLED', 'true').lower() in ['true', '1', 'yes'])

# ============================================
# CONFIGURAZIONI DOWNLOADER
# ============================================

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (limite Telegram)
MAX_VIDEO_DURATION = 600  # 10 minuti massimo
TEMP_DIR = os.getenv('TEMP_DIR', '/tmp')

# Max retry per download (3 tentativi)
MAX_RETRIES = 3

# ============================================
# CONFIGURAZIONI LOGGING
# ============================================

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'bot.log')

# ============================================
# VALIDAZIONE CONFIG
# ============================================

def validate_config():
    """Valida la configurazione all'avvio"""
    errors = []
    
    if not TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN mancante")
    
    if errors:
        raise ValueError(f"Errori di configurazione: {', '.join(errors)}")
    
    return True

# Valida al caricamento
validate_config()

# Log stato
import logging
logger = logging.getLogger(__name__)

if RANKING_ENABLED:
    logger.info(f"✅ Ranking settimanale ABILITATO (chat: {CHAT_ID})")
else:
    logger.info("⚠️ Ranking disabilitato")

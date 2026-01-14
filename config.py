#!/usr/bin/env python3
"""
Configurazione Bot Telegram Downloader Video

IMPORTANTE: Impostare queste variabili prima di avviare il bot!
"""

import os
from dotenv import load_dotenv

# Carica variabili da .env
load_dotenv()

# ===== TELEGRAM BOT TOKEN =====
# Ottieni da @BotFather su Telegram
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

if not TOKEN:
    raise ValueError(
        "❌ TELEGRAM_BOT_TOKEN non configurato!\n"
        "Crea un file .env con:\n"
        "TELEGRAM_BOT_TOKEN=il_tuo_token_qui\n"
        "CHAT_ID=id_della_chat"
    )

# ===== CHAT ID (dove inviare il ranking) =====
# Ottieni con @userinfobot
CHAT_ID = os.getenv('CHAT_ID', '')

if not CHAT_ID:
    raise ValueError(
        "❌ CHAT_ID non configurato!\n"
        "Ottieni il tuo ID con @userinfobot e aggiungi a .env:\n"
        "CHAT_ID=il_tuo_id_numerico"
    )

try:
    CHAT_ID = int(CHAT_ID)
except ValueError:
    raise ValueError("❌ CHAT_ID deve essere un numero intero!")

# ===== CONFIGURAZIONE LOGGING =====
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ===== CONFIGURAZIONE DOWNLOAD =====
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
TIMEOUT_DOWNLOAD = 120  # secondi

# ===== CONFIGURAZIONE RETRY =====
MAX_RETRIES = 3  # Numero massimo di tentativi
RETRY_DELAY = 2  # Delay iniziale in secondi (backoff: 2, 4, 8)

# ===== CONFIGURAZIONE RANKING SETTIMANALE =====
RANKING_DAY = 5  # 0=lunedì, 5=sabato
RANKING_TIME = (20, 30)  # Ore, minuti (20:30)

# ===== DIRECTORIES =====
TEMP_DIR = os.path.join(os.path.expanduser('~'), '.social_downloader_temp')
os.makedirs(TEMP_DIR, exist_ok=True)

# Crea .env di esempio se non esiste
def create_env_template():
    """Crea un file .env.example con le variabili necessarie"""
    env_example = """# Bot Telegram Downloader Video - Configurazione
# Copia questo file a .env e riempilo con i tuoi dati

# Token del bot (ottieni da @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh

# ID della chat dove inviare il ranking (ottieni da @userinfobot)
CHAT_ID=1234567890

# Livello di logging
LOG_LEVEL=INFO

# Porta per web server (usato da Render)
PORT=8443
"""
    
    if not os.path.exists('.env.example'):
        with open('.env.example', 'w') as f:
            f.write(env_example)
        print("✅ File .env.example creato. Copia a .env e riempi i dati!")

if __name__ == '__main__':
    create_env_template()
    print(f"✅ Configurazione caricata:")
    print(f"   TOKEN: {'✓ configurato' if TOKEN else '✗ NON configurato'}")
    print(f"   CHAT_ID: {CHAT_ID}")
    print(f"   MAX_RETRIES: {MAX_RETRIES}")
    print(f"   RANKING: Ogni {'sabato' if RANKING_DAY == 5 else 'altro giorno'} alle {RANKING_TIME[0]:02d}:{RANKING_TIME[1]:02d}")

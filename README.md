# 🤖 Bot Telegram - Downloader Video Social Media

## ✨ Funzionalità Principali

✅ **Download da Multiple Piattaforme**
- 🎬 YouTube / YouTube Shorts
- 🎵 TikTok
- 📸 Instagram Reels
- 👍 Facebook Reels
- 𝕏 Twitter / X

✅ **Sistema di Retry Intelligente**
- 3 tentativi automatici se il primo fallisce
- Backoff esponenziale: 2s → 4s → 8s
- Cancellazione automatica messaggi di errore intermedi
- Chat pulita con solo messaggio finale visibile

✅ **Ranking Settimanale**
- Ogni sabato alle 20:30
- Top 3 utenti che hanno inviato più video
- Congratulazioni personalizzate con aforismi motivazionali
- Tagging automatico dei vincitori

## 🚀 Setup Iniziale

### 1. **Prerequisiti**
- Python 3.8+
- pip
- Bot Telegram (crea con @BotFather)

### 2. **Clona il Progetto**
```bash
git clone <repo>
cd social-downloader-bot
```

### 3. **Installa Dipendenze**
```bash
pip install -r requirements.txt
```

### 4. **Configurazione**

#### A. Copia il file config
```bash
cp config_updated.py config.py
```

#### B. Crea file `.env`
```bash
cp .env.example .env
```

#### C. Modifica `.env` con i tuoi dati
```env
# Ottieni da @BotFather su Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh

# Ottieni il tuo ID con @userinfobot
CHAT_ID=1234567890

# Porta per web server
PORT=8443

# Livello logging
LOG_LEVEL=INFO
```

#### D. Prepara i Cookies (Opzionale ma Consigliato)

**Per YouTube:**
1. Visita https://youtube.com
2. Apri DevTools (F12) → Application → Cookies
3. Salva tutti i cookies in `youtube_cookies.txt` in formato Netscape
4. Formato: una linea per cookie con tab-separation

**Per Instagram:**
1. Visita https://instagram.com
2. Login con il tuo account
3. Salva i cookies in `cookies.txt` in formato Netscape

### 5. **Avvia il Bot**

```bash
python bot_updated.py
```

Dovresti vedere:
```
2026-01-14 20:32:15 - bot - INFO - Web server avviato sulla porta 8443
2026-01-14 20:32:16 - bot - INFO - 🤖 Bot Telegram avviato...
2026-01-14 20:32:16 - bot - INFO - ⏰ Ranking settimanale pianificato per ogni sabato alle 20:30
```

## 📝 Utilizzo

1. **Invia un link** a una delle piattaforme supportate
2. **Bot mostra "⏳ Sto scaricando..."**
3. Se primo tentativo fallisce:
   - Riprova automaticamente (fino a 3 volte)
   - Mostra il numero del tentativo
4. Se successo:
   - Cancella il messaggio di caricamento
   - Invia il video con info (titolo, autore, piattaforma)
5. Se tutti i tentativi falliscono:
   - Mostra il messaggio di errore
   - Viene cancellato automaticamente dopo 12 secondi

## 🏆 Ranking Settimanale

**Ogni sabato alle 20:30:**
1. Bot calcola chi ha inviato più link
2. Mostra top 3 con medaglie (🥇 🥈 🥉)
3. Taglia il vincitore con aforisma motivazionale
4. Messaggi di congratulazioni personalizzati
5. Contatori vengono azzerati

Esempio di messaggio:
```
🏆 RANKING SETTIMANALE 🏆

Ecco i 3 downloader più attivi della settimana:

🥇 Marco - 15 download
🥈 Giulia - 12 download
🥉 Antonio - 8 download

==================================================

🎉 Congratulazioni a @Marco!
Sei il downloader più attivo della settimana!

"La dedizione è ciò che trasforma i sogni in realtà. 💎"

Continua così! 💪
```

## ⚙️ Configurazione Avanzata

### Modificare il numero di retry
In `social_downloader.py`:
```python
self.max_retries = 3  # Aumenta a 4 o 5 per più insistenza
self.retry_delay = 2  # Delay iniziale (backoff: 2, 4, 8)
```

### Modificare il giorno/ora del ranking
In `bot_updated.py`:
```python
# Modificare in schedule_weekly_ranking()
target_time = time(20, 30, 0)  # Cambia a orario desiderato
days_until_saturday = (5 - now.weekday()) % 7  # 5=sabato, modifica per altri giorni
```

### Aggiungere più aforismi
In `bot_updated.py`:
```python
AFORISMI = [
    "Tuo aforisma qui... 💪",
    # Aggiungi altri...
]
```

### Modificare tempo cancellazione messaggi
In `bot_updated.py`:
```python
# Nel download_handler
asyncio.create_task(safe_delete_message(update, context, error_msg.message_id, delay=12))
# Cambia delay (in secondi): delay=5, delay=15, etc.
```

## 📊 File Structure

```
.
├── bot_updated.py              # Bot principale (rename a bot.py)
├── social_downloader.py        # Downloader module
├── config_updated.py           # Config (rename a config.py)
├── config.py                   # File config (non committare!)
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (non committare!)
├── .env.example                # Template .env
├── .gitignore                  # Git ignore
├── cookies.txt                 # Instagram cookies (opzionale)
├── youtube_cookies.txt         # YouTube cookies (opzionale)
├── Dockerfile                  # Docker setup (per deploy)
├── render.yaml                 # Render.com config
└── README.md                   # Questo file
```

## 🐳 Deploy su Render.com

1. Crea un account su https://render.com
2. Crea un nuovo "Web Service"
3. Connetti il tuo repository GitHub
4. Imposta Root Directory: `./`
5. Imposta Build Command: `pip install -r requirements.txt`
6. Imposta Start Command: `python bot_updated.py`
7. Aggiungi Environment Variables:
   - `TELEGRAM_BOT_TOKEN`: il tuo token
   - `CHAT_ID`: il tuo ID chat
8. Deploy!

## 🔧 Troubleshooting

### "TELEGRAM_BOT_TOKEN non configurato"
→ Controlla che il file `.env` esista e abbia `TELEGRAM_BOT_TOKEN=...`

### "CHAT_ID non configurato"
→ Ottieni il tuo ID con @userinfobot, aggiungilo a `.env`

### "Download fallito dopo 3 tentativi"
→ Possibili cause:
- Video privato/eliminato
- YouTube richiede autenticazione (usa cookies)
- Server social bloccato (attendi, usano rate limiting)
- Connessione internet lenta

### "Messaggi di errore non vengono cancellati"
→ Controlla che il bot abbia permessi di cancellazione nel chat

### "Ranking non viene inviato"
→ Controlla:
1. Che CHAT_ID sia corretto
2. Che il bot sia nel chat
3. Che il bot abbia permessi di inviare messaggi

## 📞 Support

Se hai problemi:
1. Controlla i log (`logger.info()` mostra tutto)
2. Verifica la configurazione in `config.py`
3. Prova con un URL diverso
4. Riavvia il bot

## 📜 License

Libero per uso personale e privato.

## 🎯 Versione

Bot v3.3 - Social Media Downloader
Aggiornamento: Gennaio 2026

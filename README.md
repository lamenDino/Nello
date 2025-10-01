# Bot Telegram per Scaricare Video TikTok 🎵

Un bot Telegram semplice e veloce per scaricare video TikTok senza watermark, pensato per l'uso privato nel tuo gruppo di amici.

## ✨ Caratteristiche

- 🚀 **Semplice da usare**: Invia un link TikTok e ricevi il video
- 🎥 **Senza watermark**: Video puliti senza il logo TikTok
- ⚡ **Veloce**: Download rapido e affidabile
- 👥 **Per amici**: Controllo accessi per uso privato
- 🛡️ **Sicuro**: Codice open source e trasparente
- 📱 **Completo**: Supporta tutti i formati di link TikTok

## 🚀 Come Iniziare

### 1. Crea il Bot Telegram

1. Su Telegram, cerca **@BotFather**
2. Invia `/newbot` e segui le istruzioni
3. Scegli un nome per il bot (es. "TikTok Downloader del nostro gruppo")
4. Scegli un username (es. `mio_gruppo_tiktok_bot`)
5. Copia il **token** che ti viene fornito

### 2. Ottieni il tuo ID Telegram

1. Su Telegram, cerca **@userinfobot**
2. Invia `/start`
3. Il bot ti dirà il tuo ID (es. `123456789`)

### 3. Installa il Bot

```bash
# Clona il repository
git clone https://github.com/tuousername/tiktok-telegram-bot.git
cd tiktok-telegram-bot

# Installa le dipendenze
pip install -r requirements.txt

# Copia il file di configurazione
cp .env.example .env
```

### 4. Configura il Bot

Modifica il file `.env`:

```env
TELEGRAM_BOT_TOKEN=il_token_del_tuo_bot_qui
ADMIN_USER_ID=il_tuo_id_telegram_qui
```

### 5. Avvia il Bot

```bash
python bot.py
```

Il bot sarà ora attivo! 🎉

## 📖 Come Usare il Bot

1. **Avvia una chat** con il tuo bot su Telegram
2. **Invia `/start`** per vedere il messaggio di benvenuto
3. **Incolla un link TikTok**, ad esempio:
   - `https://www.tiktok.com/@username/video/1234567890`
   - `https://vm.tiktok.com/ZMxyz123/`
4. **Aspetta qualche secondo** e riceverai il video!

### Comandi Disponibili

- `/start` - Messaggio di benvenuto e istruzioni
- `/help` - Guida dettagliata
- `/stats` - Statistiche del bot (solo admin)

## 🌐 Deploy su GitHub + Render (Gratis!)

Per tenere il bot sempre attivo 24/7:

### 1. Carica su GitHub

```bash
# Inizializza git (se non l'hai già fatto)
git init
git add .
git commit -m "Initial commit"

# Crea un nuovo repository su GitHub, poi:
git remote add origin https://github.com/tuousername/tiktok-telegram-bot.git
git push -u origin main
```

### 2. Deploy su Render

1. Vai su [render.com](https://render.com) e registrati gratuitamente
2. Clicca su "New" → "Web Service"
3. Connetti il tuo repository GitHub
4. Usa queste impostazioni:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
5. Aggiungi le variabili d'ambiente:
   - `TELEGRAM_BOT_TOKEN`: il token del tuo bot
   - `ADMIN_USER_ID`: il tuo ID Telegram
6. Clicca "Deploy"

Il tuo bot sarà online 24/7! 🚀

## ⚙️ Configurazione Avanzata

### Limitare l'Accesso agli Amici

Modifica `config.py` e aggiungi gli ID Telegram dei tuoi amici:

```python
AUTHORIZED_USERS = [
    123456789,  # Il tuo ID
    987654321,  # ID del primo amico
    456789123,  # ID del secondo amico
    # Aggiungi altri ID qui...
]
```

### Personalizzare i Messaggi

Modifica i messaggi in `config.py`:

```python
WELCOME_MESSAGE = """
🎵 Ciao {name}! 
Benvenuto nel bot del nostro gruppo! 
Invia un link TikTok per iniziare.
"""
```

## 🛠️ Struttura del Progetto

```
tiktok-telegram-bot/
├── bot.py                 # File principale del bot
├── tiktok_downloader.py   # Modulo per scaricare video
├── config.py             # Configurazioni
├── requirements.txt       # Dipendenze Python
├── .env                  # Variabili d'ambiente (non commitare!)
├── .gitignore           # File da ignorare
└── README.md            # Questa guida
```

## 🔧 Risoluzione Problemi

### Il bot non risponde
- Controlla che il token sia corretto
- Verifica che il bot sia avviato
- Controlla i log per errori

### "Errore nel download"
- Il video potrebbe essere privato
- Link non valido o scaduto
- Video troppo grande (max 50MB)

### "Accesso negato" 
- Il tuo ID non è nella lista `AUTHORIZED_USERS`
- Controlla di aver impostato correttamente `ADMIN_USER_ID`

## 📝 Requisiti Tecnici

- **Python 3.8+**
- **Dipendenze**: vedi `requirements.txt`
- **Memoria**: ~100MB RAM
- **Storage**: Minimo per file temporanei

## ⚖️ Note Legali

- ✅ **Solo per uso personale** tra amici
- ✅ **Rispetta i diritti d'autore** dei creatori
- ✅ **Non usare per scopi commerciali**
- ✅ **Scarica solo contenuti pubblici**

## 🤝 Contribuire

Hai idee per migliorare il bot? 

1. Fai un fork del repository
2. Crea un branch per la tua feature
3. Fai le modifiche
4. Invia una pull request

## 📞 Supporto

Hai problemi? 

- **Issues**: Apri un issue su GitHub
- **Email**: Contatta l'admin del tuo gruppo
- **Telegram**: Scrivi all'admin del bot

## 🆕 Prossime Funzionalità

- [ ] Database per statistiche
- [ ] Download batch (più video insieme)  
- [ ] Supporto Instagram Reels
- [ ] Interfaccia web admin
- [ ] Bot inline mode

## 📄 Licenza

MIT License - Vedi file `LICENSE` per dettagli.

---

**Fatto con ❤️ per il nostro gruppo di amici!**

*Se il bot ti è utile, lascia una ⭐ su GitHub!*
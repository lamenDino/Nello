# Telegram TikTok Video Downloader Bot

Bot Telegram per scaricare video TikTok senza watermark, realizzato con python-telegram-bot e yt-dlp.

---

## Requisiti

- Python 3.11 o superiore  
- Le dipendenze sono gestite in `requirements.txt`:
  ```
  python-telegram-bot==20.8
  requests==2.31.0
  python-dotenv==1.0.0
  aiohttp>=3.9.0
  ```
- `yt-dlp` installato via Dockerfile o manualmente:
  ```bash
  pip install --upgrade yt-dlp
  ```

---

## 🚀 Deploy su Render.com

### Tipo di Servizio

- Utilizza un **Web Service** (NON un Background Worker) perché il bot avvia un piccolo server web parallelo su porta 8080.

### 🔌 Porte

- Porta HTTP esposta: **8080**  
- Impostata nel Dockerfile con:  
  ```dockerfile
  EXPOSE 8080
  ```
- Puoi modificare la porta con la variabile d’ambiente `PORT` (default 8080).

### 🔑 Variabili d’ambiente

Definisci queste variabili nel pannello ambienti di Render:

| Key                 | Valore                   | Descrizione                   |
|---------------------|--------------------------|------------------------------|
| `TELEGRAM_BOT_TOKEN` | Token del bot Telegram   | Da @BotFather                |
| `ADMIN_USER_ID`      | ID Telegram admin        | ID amministratore del bot     |
| `PORT`               | `8080` (facoltativa)     | Porta per server web aiohttp  |

### 🐳 Dockerfile

Assicurati che il Dockerfile:

- Esponga la porta 8080:  
  ```dockerfile
  EXPOSE 8080
  ```
- Installi tutte le dipendenze comprese `yt-dlp` e `aiohttp`.

---

## ⚙️ Avvio

- **Start command** in Render:
  ```
  python bot.py
  ```

---

## 🔄 Come funziona

- Il bot usa **long polling** per ricevere messaggi Telegram.  
- Parallelamente avvia un server web **aiohttp** sulla porta 8080 per soddisfare la scansione porte di Render.  
- Quando un utente invia un link TikTok, il bot:
  1. Pulisce il link (rimuovendo parametri e redirezionamenti).  
  2. Scarica il video senza watermark.  
  3. Cancella il messaggio originale.  
  4. Invia il video con didascalia:
     ```
     🎥 Video inviato da: [utente]
     🔗 Link originale: [link]
     ```

---

## ⚠️ Note importanti

- Assicurati che **solo un’istanza** del bot sia attiva per evitare conflitti Telegram.  
- Per usare webhook è necessaria una configurazione specifica (SSL, URL pubblico), non trattata qui.  
- Controlla periodicamente la versione di `yt-dlp` per il supporto ai nuovi formati TikTok.

---

## 📬 Contatti

Per problemi o contributi, apri una issue su GitHub o contattami direttamente.
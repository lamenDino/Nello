# Telegram MultiPlatform Video Downloader Bot

Bot Telegram per scaricare video da TikTok, Instagram e Facebook usando `yt-dlp`.

## Setup

1. Crea file `.env`:
   ```
   TELEGRAM_BOT_TOKEN=il_tuo_token_bot
   ADMIN_USER_ID=il_tuo_id_telegram
   PORT=8080
   ```

2. Installa dipendenze:
   ```bash
   pip install -r requirements.txt
   ```

## Deploy su Render

- Tipo di servizio: Web Service
- Espone porta definita da `PORT`
- Start command:
  ```
  python bot.py
  ```

## Uso

Invia un link da TikTok, Instagram o Facebook al bot. Verrà cancellato il messaggio originale, scaricato il video e inviato con didascalia che include la piattaforma di origine.

# Telegram Multi-Platform Video Downloader Bot (Video + Caroselli)

Bot Telegram che scarica contenuti da più piattaforme usando `yt-dlp` e li ripubblica nel gruppo con un formato fisso.

Supporta:
- TikTok
- Instagram (Reels + caroselli foto quando estraibili)
- Facebook (Video/Reels + link share)
- YouTube (Shorts)
- Twitter / X

Include inoltre:
- Retry “silenzioso”: se fallisce, riprova e NON invia messaggi d’errore
- Ranking settimanale TOP 3 con badge 🥇🥈🥉 (ogni sabato alle 20:00 Europe/Rome)
- Deploy pronto per Render via Docker

---

## Formato messaggio in uscita

Il bot pubblica:

🎵 Video da :  
👤 Video inviato da :  
🔗 Link originale :  
📝 Meta info video :

---

## Configurazione

Variabili d’ambiente (Render → Environment):

- `TELEGRAM_BOT_TOKEN` (obbligatoria)
- `PORT` (default 8080)

Esempio `.env.example`:

```env
TELEGRAM_BOT_TOKEN=
PORT=8080
LOG_LEVEL=INFO
TEMP_DIR=/tmp

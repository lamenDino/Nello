# Telegram Multi-Platform Video Downloader Bot v3.0

Bot Telegram per scaricare video da TikTok, Instagram, Facebook, YouTube e Twitter.

## ✨ Caratteristiche

✅ **TikTok** - Tutti i video
✅ **Instagram** - Reels, Posts, Storie (con autenticazione)
✅ **Facebook** - Video, Reels, Reels /share/ (automaticamente convertiti)
✅ **YouTube** - SOLO Shorts (video <= 60 secondi)
✅ **Twitter/X** - Video
✅ **Formattazione Bella** - Emoji, grassetto, nome utente reale
✅ **Gestione Errori** - Messaggi di errore chiari e utili

## 📋 Setup

### 1. Crea file `.env`

```env
TELEGRAM_BOT_TOKEN=il_tuo_token_bot
ADMIN_USER_ID=il_tuo_id_telegram
PORT=8080
```

### 2. Installa dipendenze

```bash
pip install -r requirements.txt
```

### 3. Aggiungi cookies Instagram (opzionale)

Per scaricare da Instagram:
1. Installa "Get cookies.txt LOCALLY" nel browser
2. Esporta i cookies da Instagram
3. Salva come `cookies.txt` nella root del progetto

## 🚀 Utilizzo Locale

```bash
python bot.py
```

## 🌐 Deploy su Render

1. Carica su GitHub
2. Connetti repo a Render
3. New → Web Service
4. Render usa automaticamente il `Dockerfile`
5. Deploy!

## 📝 Modifiche v3.0

- ✨ **Supporto completo Instagram** - Reels, Posts, Storie
- ✨ **YouTube Shorts Only** - Video > 60 sec rifiutati
- ✨ **Formattazione migliorata** - Emoji + grassetto + nome reale uploader
- ✨ **Facebook /share/ fix** - Conversione automatica URL
- ✨ **Messaggi di errore chiari** - Spiegazioni dettagliate
- ✨ **social_downloader.py** - Downloader dedicato e robusto

## 🔧 File Principali

| File | Descrizione |
|------|-------------|
| `bot.py` | Bot Telegram principale |
| `social_downloader.py` | Logica di download (v3.0) |
| `requirements.txt` | Dipendenze aggiornate |
| `Dockerfile` | Containerizzazione |
| `cookies.txt` | Cookies Instagram (opzionale) |

## 🎯 Prossime Feature

- [ ] Statistiche di download
- [ ] Supporto audio-only
- [ ] Conversione formato video
- [ ] Cache video

## ⚠️ Note Importanti

- **Instagram cookies**: Scadono ogni ~30 giorni
- **YouTube Shorts**: Solo video <= 60 secondi
- **Limite Telegram**: Max 50MB per video
- **Facebook /share/**: Convertiti automaticamente

## 📞 Supporto

Errori comuni e soluzioni in `TROUBLESHOOTING.md`

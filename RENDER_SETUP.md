# Guida Completa: Deploy su Render

## 📋 Prerequisiti

- Account GitHub con il repository
- Account Render (gratuito)
- File `instagram_cookies.txt` (opzionale per Instagram)

## 🚀 Step-by-Step Setup

### 1. Prepara il Repository GitHub

```bash
# Assicurati di avere questi file nella root del repo:
main.py
requirements.txt
Procfile
runtime.txt
.gitignore
README.md
instagram_cookies.txt  # FACOLTATIVO - aggiungi solo se vuoi Instagram
```

### 2. Aggiungi il file .gitignore per proteggere i cookies

Nel tuo `.gitignore`, assicurati che ci sia:
```
instagram_cookies.txt
*.txt
.env
.env.local
```

**IMPORTANTE**: Non fare il push dei cookies su GitHub!

### 3. Crea il Web Service su Render

1. Vai su https://render.com
2. Fai login con GitHub
3. Clicca "New" → "Web Service"
4. Seleziona il tuo repository
5. Configura come segue:

| Campo | Valore |
|-------|--------|
| **Name** | social-media-downloader |
| **Environment** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT` |
| **Plan** | Free (o pagato se vuoi sempre attivo) |

### 4. Aggiungi Variabili d'Ambiente (Opzionale)

1. Nella dashboard di Render, vai su "Environment"
2. Aggiungi:
   - `PYTHONUNBUFFERED` = `1`
   - `PORT` = `8000`

### 5. Aggiungi i Cookies (Se vuoi Instagram)

**METODO SICURO (Consigliato)**:

1. Dopo il primo deploy, vai alla shell del servizio
2. Esegui:
```bash
# Nella shell Render
cat > instagram_cookies.txt << 'EOF'
# Incolla qui il contenuto del tuo file instagram_cookies.txt
# ... (copia il contenuto del file che hai esportato)
EOF
```

3. Salva il file: Ctrl+D

Oppure **via variabili d'ambiente**:

1. Aggiungi una variabile: `INSTAGRAM_COOKIES_B64` con il contenuto base64 codificato
2. Nel `main.py`, modifica all'inizio:
```python
import base64
import os

if os.getenv('INSTAGRAM_COOKIES_B64'):
    cookies_b64 = os.getenv('INSTAGRAM_COOKIES_B64')
    cookies_content = base64.b64decode(cookies_b64).decode()
    with open('instagram_cookies.txt', 'w') as f:
        f.write(cookies_content)
```

### 6. Deploy

1. Clicca "Deploy"
2. Aspetta che finisca (2-3 minuti)
3. Quando vedi "Live", il servizio è online!
4. L'URL sarà qualcosa come: `https://social-media-downloader.onrender.com`

## ✅ Verifica il Deploy

```bash
# Health check
curl https://social-media-downloader.onrender.com/health

# Status
curl https://social-media-downloader.onrender.com/status

# Prova download
curl "https://social-media-downloader.onrender.com/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## 🔧 Troubleshooting

### Errore: "yt-dlp: command not found"
- Verifica che `yt-dlp>=2025.11.0` sia in `requirements.txt`
- Clicca "Manual Deploy" → "Deploy"

### Errore: "Instagram cookies not found"
- Aggiungi il file `instagram_cookies.txt` tramite la shell
- Oppure usa le variabili d'ambiente

### Errore: "Port already in use"
- Render lo gestisce automaticamente, non preoccuparti
- La variabile `$PORT` viene impostata da Render

### Il servizio va in sleep (Free tier)
- Su Render Free, i servizi vanno in sleep dopo 15 minuti
- Usa il tier pagato per evitarlo
- Oppure mantieni il servizio attivo con un ping cron job

### Facebook Reels /share/ ancora non funzionano
- Verifica l'URL formato: `https://www.facebook.com/share/r/1H5M3S7Wra/`
- Prova con l'URL diretto al reel: `https://www.facebook.com/reel/1234567890/`

## 📊 Monitoring

Nella dashboard Render puoi vedere:
- **Logs** - Tutti i messaggi dell'app
- **Metrics** - CPU, RAM, richieste
- **Deployments** - Storico dei deploy

## 🔄 Aggiornamenti Futuri

Per aggiornare il codice:

```bash
# Nel tuo computer
git add .
git commit -m "Update: fixed Instagram download"
git push origin main

# Render auto-deploy se hai abilitato "Auto-Deploy from Git"
```

## 💾 Backup dei Logs

I logs rimangono visibili per 24 ore. Per salvarli:

```bash
# Nella shell Render
tail -f /var/log/render.log > logs.txt
```

## 🎯 Best Practices

1. ✅ **Proteggi i cookies**: Mai commitarli su GitHub
2. ✅ **Monitora le rate limits**: Aggiungi delay tra i download
3. ✅ **Log tutto**: Utile per il debugging
4. ✅ **Aggiorna yt-dlp**: Fai update regolarmente in requirements.txt
5. ✅ **Testa localmente**: Prima di pushare

## 📞 Supporto Render

- Docs: https://render.com/docs
- Status: https://status.render.com
- Support: support@render.com
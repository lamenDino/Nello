# Social Media Downloader API

Una API FastAPI per il download di video e contenuti da Instagram, Facebook, TikTok, YouTube e altri social media.

## Caratteristiche

✅ **Instagram** - Download di reels, post, storie (con autenticazione)
✅ **Facebook** - Download di video, reels e contenuti (incluso formato /share/)
✅ **TikTok** - Download di video
✅ **YouTube** - Download di video
✅ **Twitter/X** - Download di video
✅ **Reddit** - Download di video e GIF

## Installazione

### Locale

```bash
# Clone repository
git clone https://github.com/your-username/social-media-downloader.git
cd social-media-downloader

# Crea virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\\Scripts\\activate  # Windows

# Installa dipendenze
pip install -r requirements.txt

# Esegui l'app
python main.py
```

L'API sarà disponibile su `http://localhost:8000`

### Su Render

1. Crea un account su [Render.com](https://render.com)
2. Connetti il tuo repository GitHub
3. Crea un nuovo Web Service
4. Seleziona "Python" come runtime
5. Build command: `pip install -r requirements.txt`
6. Start command: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT`

## Configurazione Instagram

Per scaricare da Instagram, hai bisogno dei cookies di autenticazione:

1. Installa l'estensione "Get cookies.txt LOCALLY" nel tuo browser
2. Accedi a Instagram
3. Visita https://www.instagram.com
4. Esporta i cookies in formato Netscape
5. Salva il file come `instagram_cookies.txt` nella root del progetto

**IMPORTANTE**: Non condividere mai i tuoi cookies online! Trattali come una password.

## Utilizzo

### GET Request

```bash
curl "http://localhost:8000/download?url=https://www.instagram.com/reel/xxxxx/"
```

### POST Request

```bash
curl -X POST http://localhost:8000/download \\
  -H "Content-Type: application/json" \\
  -d '{"url": "https://www.facebook.com/watch/?v=xxxxx"}'
```

### Response di successo

```json
{
  "success": true,
  "title": "Video Title",
  "url": "https://...",
  "filename": "Video Title.mp4",
  "duration": 120,
  "uploader": "Username"
}
```

### Response di errore

```json
{
  "success": false,
  "error": "Error message",
  "url": "https://..."
}
```

## Endpoint

- `GET /` - Info API
- `GET /download?url=URL` - Download (GET method)
- `POST /download` - Download (POST method)
- `GET /health` - Health check
- `GET /status` - Status e informazioni

## Troubleshooting

### "Cookies Instagram non trovati"
Assicurati che il file `instagram_cookies.txt` sia nella root del progetto e contenga cookie validi.

### "ERROR: URL not supported"
Verifica che l'URL sia corretto e nella lista di piattaforme supportate.

### "Sign in required"
I tuoi cookies Instagram sono scaduti. Esporta nuovi cookies.

### Facebook Reels /share/ non funzionano
L'app converte automaticamente gli URL `/share/` nel formato corretto. Se continua a non funzionare, prova con l'URL diretto.

## Licenza

MIT License - Vedi LICENSE file

## Supporto

Per bug e feature requests, apri una issue su GitHub.

## Disclaimer

Questo tool è solo per scopi educativi e personali. Assicurati di rispettare i termini di servizio delle piattaforme utilizzate e i diritti d'autore dei contenuti scaricati.
# Social Media Downloader - Struttura del Progetto

## 📁 File Structure

```
social-media-downloader/
├── main.py                    # File principale dell'app FastAPI
├── requirements.txt           # Dipendenze Python
├── Procfile                   # Configurazione per Heroku/Render
├── runtime.txt               # Versione Python
├── Dockerfile                # Configurazione Docker
├── docker-compose.yml        # Docker Compose per testing
├── .gitignore               # Git ignore patterns
├── README.md                # Documentazione principale
├── RENDER_SETUP.md          # Guida deploy su Render
├── PROJECT_STRUCTURE.md     # Questo file
├── instagram_cookies.txt    # Cookies Instagram (DA AGGIUNGERE MANUALMENTE)
└── downloads/               # Cartella per i file scaricati (creata automaticamente)
```

## 🔧 Componenti Principali

### main.py

**Classe SocialMediaDownloader**
- `__init__()` - Inizializza le opzioni di download
- `fix_facebook_url()` - Converte URL Facebook /share/ in formato compatibile
- `download()` - Metodo universale per scaricare contenuti

**Endpoint FastAPI**
- `GET /` - Info API
- `GET /download?url=URL` - Download tramite query parameter
- `POST /download` - Download tramite body JSON
- `GET /health` - Health check
- `GET /status` - Status e info sistema

### requirements.txt

Dipendenze critiche:
- `yt-dlp>=2025.11.0` - Downloader principale
- `fastapi>=0.104.0` - Framework API
- `uvicorn>=0.24.0` - ASGI server
- `requests>=2.31.0` - HTTP requests
- `gunicorn>=21.0.0` - Production server

### Configurazione Deploy

**Procfile** - Comando startup per Render/Heroku
**runtime.txt** - Specifica versione Python 3.11.7
**Dockerfile** - Containerizza l'app per Docker
**docker-compose.yml** - Setup locale con Docker

## 🔐 Sicurezza

### Protezione dei Cookies
1. I cookies Instagram sono nel `.gitignore`
2. Non verranno mai pushati su GitHub
3. Vanno aggiunti manualmente su Render tramite shell

### Best Practices
- ✅ Mai commitare `.env` o file con credenziali
- ✅ Usare variabili d'ambiente per config sensibili
- ✅ Validare tutti gli input URLs
- ✅ Aggiungere rate limiting per evitare ban
- ✅ Loggare tutte le operazioni

## 🚀 Deployment Checklist

- [ ] `main.py` pronto e testato
- [ ] `requirements.txt` con tutte le dipendenze
- [ ] `.gitignore` configurato correttamente
- [ ] `README.md` completo
- [ ] Repository GitHub pulito
- [ ] Instagram cookies (opzionale) generati localmente
- [ ] Account Render creato
- [ ] Repository connesso a Render
- [ ] Build command configurato
- [ ] Start command configurato
- [ ] Deploy completato e testato

## 📝 Comandi Utili

### Setup Locale
```bash
# Clone
git clone https://github.com/your-username/social-media-downloader.git
cd social-media-downloader

# Virtual environment
python -m venv venv
source venv/bin/activate

# Install
pip install -r requirements.txt

# Run
python main.py
```

### Docker
```bash
# Build
docker build -t social-downloader .

# Run
docker run -p 8000:8000 -v $(pwd)/instagram_cookies.txt:/app/instagram_cookies.txt social-downloader

# Compose
docker-compose up
```

### Testing
```bash
# Test API
curl http://localhost:8000/

# Test Instagram
curl "http://localhost:8000/download?url=https://www.instagram.com/reel/xxxxx/"

# Test Facebook
curl -X POST http://localhost:8000/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.facebook.com/share/r/1H5M3S7Wra/"}'
```

## 🐛 Troubleshooting

### Import Errors
```python
# Se yt-dlp non è importato:
pip install --upgrade yt-dlp
```

### Connection Issues
```python
# Aumenta il timeout in main.py:
'socket_timeout': 60  # da 30 a 60 secondi
```

### Rate Limiting
```python
# Aggiungi delay tra richieste:
import time
time.sleep(5)  # 5 secondi di delay
```

## 📈 Monitoring Locale

```bash
# Watch logs in real-time
tail -f logs.txt

# Monitor performance
python -m cProfile -s cumulative main.py
```

## 🔄 Updates e Maintenance

### Aggiornare yt-dlp
```bash
# Locale
pip install --upgrade yt-dlp

# Su GitHub
# Modifica requirements.txt -> yt-dlp>=X.X.X
# Push su GitHub -> Render auto-deploy
```

### Aggiungere Nuove Piattaforme
1. Aggiungi logica di riconoscimento in `download()`
2. Testa localmente
3. Push su GitHub
4. Render auto-deploy

## 📞 Support e Risorse

- **yt-dlp Docs**: https://github.com/yt-dlp/yt-dlp
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Render Docs**: https://render.com/docs
- **Instagram Download**: Richiede autenticazione con cookies
- **Facebook Download**: Funziona senza autenticazione (con limitazioni)
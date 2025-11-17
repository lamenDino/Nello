# ⚡ Quick Start Guide

## 📦 Come Usare i File Forniti

### Step 1: Scarica Tutti i File

Scarica questi file dalla cartella generata:
```
✅ main.py
✅ requirements.txt
✅ Procfile
✅ runtime.txt
✅ .gitignore
✅ README.md
✅ RENDER_SETUP.md
✅ PROJECT_STRUCTURE.md
✅ Dockerfile
✅ docker-compose.yml
✅ instagram_cookies.txt (IL TUO FILE)
```

### Step 2: Crea il Repository GitHub

```bash
# Crea folder locale
mkdir social-media-downloader
cd social-media-downloader

# Inizializza Git
git init
git add .
git commit -m "Initial commit: Social Media Downloader"

# Crea repo su GitHub, poi:
git remote add origin https://github.com/YOUR-USERNAME/social-media-downloader.git
git branch -M main
git push -u origin main
```

### Step 3: Deploy su Render

1. Vai su https://render.com → Sign up
2. Clicca "New" → "Web Service"
3. Connetti GitHub
4. Seleziona il tuo repository
5. Configura:
   - **Name**: `social-media-downloader`
   - **Region**: `Frankfurt` (più vicino a te)
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT`
   - **Instance Type**: `Free`
6. Clicca "Create Web Service"
7. Aspetta 2-3 minuti

### Step 4: Aggiungi Cookies (Per Instagram)

Dopo che il servizio è online (Status = "Live"):

1. Clicca su "Shell" nella dashboard Render
2. Copia il contenuto del tuo file `instagram_cookies.txt`
3. Nella shell, esegui:
```bash
cat > instagram_cookies.txt << 'EOF'
# INCOLLA TUTTO IL CONTENUTO DEL FILE QUI
# ...
EOF
```
4. Premi Ctrl+D per salvare

### Step 5: Test il Servizio

```bash
# Sostituisci con l'URL del tuo servizio Render
RENDER_URL="https://social-media-downloader.onrender.com"

# Test 1: Health Check
curl $RENDER_URL/health

# Test 2: Status
curl $RENDER_URL/status

# Test 3: Download Facebook
curl "$RENDER_URL/download?url=https://www.facebook.com/share/r/1H5M3S7Wra/"

# Test 4: Download YouTube
curl "$RENDER_URL/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Test 5: Download Instagram
curl "$RENDER_URL/download?url=https://www.instagram.com/reel/XXXXX/"
```

## 🔧 Configurazione Locale (Opzionale)

Se vuoi testare prima localmente:

```bash
# Setup
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oppure
venv\Scripts\activate  # Windows

# Install
pip install -r requirements.txt

# Aggiungi il file instagram_cookies.txt nella cartella corrente

# Run
python main.py
```

Accedi a: `http://localhost:8000`

## 📊 File Inclusi - Spiegazione Rapida

| File | Scopo |
|------|-------|
| `main.py` | **Codice principale** - Contiene tutta la logica |
| `requirements.txt` | Dipendenze Python (yt-dlp, fastapi, etc) |
| `Procfile` | Comando di startup per Render |
| `runtime.txt` | Versione Python |
| `.gitignore` | Protegge i tuoi cookies |
| `README.md` | Documentazione per gli utenti |
| `RENDER_SETUP.md` | Guida dettagliata deploy Render |
| `PROJECT_STRUCTURE.md` | Struttura e architettura |
| `Dockerfile` | Per deployare con Docker |
| `docker-compose.yml` | Testing locale con Docker |
| `instagram_cookies.txt` | **TUO FILE** - Cookies autenticazione |

## ⚠️ IMPORTANTE: Proteggi i Tuoi Cookies

**PRIMA di fare il push su GitHub:**

1. Assicurati che `instagram_cookies.txt` sia nel `.gitignore`
2. Verifica che il file sia nel `.gitignore`:
```bash
# Visualizza il content di .gitignore
cat .gitignore
# Deve contenere: instagram_cookies.txt
```
3. Verifica che non sia stato già tracciato:
```bash
git rm --cached instagram_cookies.txt
git commit -m "Remove cookies from tracking"
```

## 🚨 Troubleshooting Rapido

**Errore: "No module named 'yt_dlp'"**
```bash
pip install --upgrade yt-dlp
```

**Errore: "Instagram cookies not found"**
→ Aggiungi il file tramite la shell Render (Step 4)

**Errore: "Port already in use"**
→ Cambia porta in main.py: `port = 8001`

**Facebook Reels non funzionano**
→ Prova con l'URL diretto: `https://www.facebook.com/reel/123456/`

**Il servizio va offline (Free tier)**
→ Render mette in sleep dopo 15 min di inattività
→ Usa il tier pagato oppure installa un wake-up bot

## 📞 Next Steps

1. ✅ Upload su GitHub
2. ✅ Deploy su Render
3. ✅ Aggiungi cookies
4. ✅ Test tutti i link
5. ✅ Condividi l'URL del servizio!

## 💡 Tips

- **URL vari**: Funziona con TikTok, YouTube, Twitter, Reddit, etc.
- **Aggiungi corshe**: Modifica `CORS` in `main.py` per limitare i domini
- **Aggiungi logging**: Aggiungi variabili d'ambiente per debug
- **Rate limiting**: Considera di aggiungere un sistema di rate limit

---

**Domande?** Leggi i file README.md e RENDER_SETUP.md per dettagli completi!
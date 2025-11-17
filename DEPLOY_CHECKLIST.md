# ✅ Checklist Deploy - Step-by-Step

## 📦 FASE 1: Preparazione File

- [ ] **main.py** - Copiato nella cartella
- [ ] **requirements.txt** - Contiene tutte le dipendenze
- [ ] **Procfile** - Configurazione per Render
- [ ] **runtime.txt** - Python 3.11.7 specificato
- [ ] **.gitignore** - Protegge instagram_cookies.txt
- [ ] **README.md** - Documentazione pronta
- [ ] **Dockerfile** - Per testing con Docker
- [ ] **docker-compose.yml** - Setup Docker Compose
- [ ] **instagram_cookies.txt** - IL TUO FILE nella cartella
- [ ] **RENDER_SETUP.md** - Guida di riferimento
- [ ] **PROJECT_STRUCTURE.md** - Architettura documentata
- [ ] **QUICKSTART.md** - Quick reference

---

## 🔧 FASE 2: Setup GitHub Repository

### Creazione Repo

```bash
# 1. Crea cartella e vai dentro
mkdir social-media-downloader
cd social-media-downloader

# 2. Copia TUTTI i 12 file nella cartella

# 3. Inizializza Git
git init
git config user.name "Your Name"
git config user.email "your.email@gmail.com"

# 4. Stage all files
git add .

# 5. Verifica che instagram_cookies.txt NON sia tracciato
git status
# Dovrebbe mostrare: (modified: ...)
# Ma NO instagram_cookies.txt se è in .gitignore correttamente!

# 6. First commit
git commit -m "Initial commit: Social Media Downloader API"

# 7. Crea repo su GitHub tramite browser:
# - Vai a https://github.com/new
# - Nome: social-media-downloader
# - Descrizione: "Social Media Downloader API - Instagram, Facebook, TikTok, etc"
# - Public (opzionale)
# - Non inizializzare con README (lo hai già)
# - Create repository

# 8. Connetti repository remoto
git remote add origin https://github.com/YOUR-USERNAME/social-media-downloader.git
git branch -M main
git push -u origin main

# Verifica il push
git log --oneline
```

### Verifica GitHub

- [ ] Repository creato
- [ ] Tutti i file su GitHub (tranne instagram_cookies.txt)
- [ ] File .gitignore presente e funzionante
- [ ] README.md visibile nella homepage repo

---

## 🚀 FASE 3: Deploy su Render

### Preparazione Render

1. [ ] Vai a https://render.com
2. [ ] Clicca "Sign Up" → Connetti con GitHub
3. [ ] Autorizza l'accesso ai tuoi repository

### Creazione Web Service

1. [ ] Clicca "New" → "Web Service"
2. [ ] Seleziona il repository `social-media-downloader`
3. [ ] Clicca "Connect"

### Configurazione Servizio

Compila i seguenti campi:

| Campo | Valore |
|-------|--------|
| **Name** | `social-media-downloader` |
| **Region** | `Frankfurt (Europe)` |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT` |
| **Instance Type** | `Free` (oppure Pro/Premium se vuoi che stia sempre online) |

### Environment Variables

Clicca "Advanced" → "Environment":

- [ ] Add: `PYTHONUNBUFFERED` = `1`
- [ ] Add: `PORT` = `8000`

### Deploy

- [ ] Clicca il tasto blu "Create Web Service"
- [ ] Aspetta che appaia il logo di Render
- [ ] Aspetta 2-3 minuti per il build
- [ ] Quando vedi "Live" e un checkmark verde ✅ sei online!

---

## 🔐 FASE 4: Aggiunta Cookies Instagram

### IMPORTANTE: Protezione Cookies

✅ **I tuoi cookies NON sono su GitHub** (protetti da .gitignore)

### Aggiunta su Render

1. [ ] Nella dashboard Render, clicca su "Shell" (in alto a sinistra)
2. [ ] Si aprirà una shell bash del server

#### Metodo A: Copia/Incolla (Più facile)

```bash
# Nella shell Render, esegui:
cat > instagram_cookies.txt << 'EOF'
# Netscape HTTP Cookie File
# https://curl.haxx.se/rfc/cookie_spec.html
# This is a generated file! Do not edit.

.instagram.com	TRUE	/	TRUE	1797943763	csrftoken	uBLIg2WPpa36vTgFDfFxB2yFXOgXTsXW
.instagram.com	TRUE	/	TRUE	1793963692	datr	n17eaPykJ6wFm_IgdXbGCIhk
# ... (COPIA TUTTO IL CONTENUTO DEL TUO FILE QUI)

EOF
# Dopo il'EOF, il file è salvato
```

#### Metodo B: Upload file (Se Render lo permette)

```bash
# Oppure scarica il file dalla shell se Render lo permette
# e usa l'interfaccia web per uploadare
```

### Verifica Cookies

- [ ] Verifica che il file esista:
```bash
ls -la instagram_cookies.txt
```
- [ ] Verifica che sia leggibile:
```bash
cat instagram_cookies.txt | head -5
```

---

## ✅ FASE 5: Testing

### Test 1: Health Check

```bash
curl https://social-media-downloader.onrender.com/health
# Risposta attesa: {"status":"ok","service":"Social Media Downloader"}
```

- [ ] Status: 200 OK

### Test 2: Status API

```bash
curl https://social-media-downloader.onrender.com/status
# Risposta attesa: JSON con info sistema e cookies status
```

- [ ] Instagram cookies: `configured` (se aggiunti)
- [ ] Supported platforms: lista piattaforme

### Test 3: Download Facebook

```bash
curl "https://social-media-downloader.onrender.com/download?url=https://www.facebook.com/share/r/1H5M3S7Wra/"
# Dovrebbe iniziare il download del reel
```

- [ ] Response: `success: true`
- [ ] File scaricato nella cartella `downloads/`

### Test 4: Download YouTube

```bash
curl "https://social-media-downloader.onrender.com/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

- [ ] Response: `success: true`

### Test 5: Download Instagram

```bash
curl "https://social-media-downloader.onrender.com/download?url=https://www.instagram.com/reel/XXXXX/"
# Sostituisci XXXXX con un vero ID
```

- [ ] Response: `success: true`
- [ ] Se respons e è `error`, i cookies potrebbero essere scaduti

---

## 🐛 FASE 6: Troubleshooting

### Se Build Fallisce

```
ERROR: Could not find a version that satisfies the requirement
```

- [ ] Verifica `requirements.txt` → Corretti i nomi pacchetti
- [ ] Clicca "Manual Deploy" → "Re-deploy"

### Se Servizio è Offline

```
503 Service Unavailable
```

- [ ] Verifica che il `Start Command` sia corretto
- [ ] Guarda i "Logs" per errori
- [ ] Clicca "Manual Deploy" per riavviare

### Se Instagram Non Funziona

```
"Instagram cookies not found"
```

- [ ] Verifica il file `instagram_cookies.txt` esista:
```bash
ls instagram_cookies.txt
```
- [ ] Verifica il formato sia Netscape:
```bash
head -1 instagram_cookies.txt
# Deve contenere: # Netscape HTTP Cookie File
```

### Se Facebook /share/ Continua a Non Funzionare

- [ ] Verifica l'URL: `https://www.facebook.com/share/r/XXXXX/`
- [ ] Prova diretto: `https://www.facebook.com/reel/123456/`
- [ ] Il fix_facebook_url() dovrebbe convertirlo automaticamente
- [ ] Se non funziona, leggi i logs per il messaggio d'errore

---

## 📊 FASE 7: Monitoring

### Visualizza Logs

1. [ ] Dashboard Render → Clicca il nome del servizio
2. [ ] Logs (pannello centrale)
3. [ ] Vedi tutti gli accessi e errori

### Tieni d'Occhio

- [ ] Numero di richieste al giorno
- [ ] Errori e warning
- [ ] Usage CPU/RAM (se tier pagato)

### Aggiornamenti

Per aggiornare il codice:

```bash
# Nel tuo PC
git add .
git commit -m "Update: new feature"
git push origin main

# Render auto-deploya se "Auto-Deploy from Git" è abilitato
# Oppure clicca "Manual Deploy" nella dashboard
```

- [ ] Auto-deploy abilitato (consigliato)

---

## 🎉 FASE 8: Finale

- [ ] ✅ Repository GitHub pronto
- [ ] ✅ Deploy su Render completato
- [ ] ✅ Cookies Instagram aggiunti (opzionale)
- [ ] ✅ Tutti i test passati
- [ ] ✅ Logs controllati
- [ ] ✅ Servizio online e funzionante!

### Prossimi Step

1. [ ] Condividi l'URL: `https://social-media-downloader.onrender.com`
2. [ ] Testa con amici/colleghi
3. [ ] Monitora i logs
4. [ ] Se necessario, fai aggiornamenti
5. [ ] Goditi il tuo servizio di download! 🎊

---

## 📞 Support Rapido

| Problema | Soluzione |
|----------|-----------|
| Build fallisce | Rileggi `requirements.txt`, vedi error nei logs |
| Service offline | Vedi logs per errori, clicca "Re-deploy" |
| Instagram non scarica | Cookies scaduti o formato errato |
| Facebook /share/ non funziona | Il fix_facebook_url() lo converte, controlla logs |
| Serve aiuto? | Leggi RENDER_SETUP.md per guide complete |

---

**Una volta completato tutto, avrai un servizio di download completamente funzionante! 🚀**
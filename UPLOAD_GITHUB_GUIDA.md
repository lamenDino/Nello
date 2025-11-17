# 📤 GUIDA: Upload su GitHub (5 minuti)

## 📋 File che Hai Ricevuto (v2.2 - COMPLETO)

Questi sono i file AGGIORNATI che devi uploadare:

```
✅ main.py              - Codice principale (v2.2 DEFINITIVO)
✅ requirements.txt     - Dipendenze
✅ Procfile            - Start command per Render (PORTA 8080 FIX)
✅ runtime.txt         - Python 3.11.7
✅ .gitignore          - Protegge i cookies
✅ README.md           - Documentazione
✅ instagram_cookies.txt - IL TUO FILE (aggiungi localmente)
```

---

## 🔧 SETUP LOCALE (10 minuti prima del push)

### PASSO 1: Crea la Cartella

```bash
# Nel tuo PC, crea una cartella nuova
mkdir social-media-downloader
cd social-media-downloader
```

### PASSO 2: Copia i File

Scarica e copia TUTTI questi file nella cartella:
- main.py [70]
- requirements.txt [71]
- Procfile [74]
- runtime.txt [75]
- .gitignore [72]
- README.md [73]
- instagram_cookies.txt (il tuo file)

### PASSO 3: Verifica Che i File Siano Lì

```bash
ls -la
# Dovresti vedere:
# main.py
# requirements.txt
# Procfile
# runtime.txt
# .gitignore
# README.md
# instagram_cookies.txt
```

---

## 🚀 UPLOAD SU GITHUB (5 minuti)

### PASSO 1: Inizializza Git

```bash
# Dalla cartella del progetto
git init
git config user.name "Your Name"
git config user.email "your.email@gmail.com"
```

### PASSO 2: Stage Tutti i File

```bash
git add .
```

### PASSO 3: Verifica Che i Cookies NON Vengono Tracciati

```bash
git status
```

**Dovresti vedere:**
```
Changes to be committed:
  new file:   .gitignore
  new file:   Procfile
  new file:   README.md
  new file:   main.py
  new file:   requirements.txt
  new file:   runtime.txt

Untracked files:
  instagram_cookies.txt      ← QUESTO NON DEVE ESSERE QUI
```

Se vedi `instagram_cookies.txt` nella sezione "Changes to be committed", allora il .gitignore non funziona!

**Se succede:**
```bash
git reset
# Modifica .gitignore e assicurati che contenga: instagram_cookies.txt
git add -A
```

### PASSO 4: Primo Commit

```bash
git commit -m "Initial commit: Social Media Downloader v2.2"
```

Dovrebbe mostrare qualcosa tipo:
```
6 files changed, 250 insertions(+)
 create mode 100644 .gitignore
 create mode 100644 Procfile
 create mode 100644 README.md
 create mode 100644 main.py
 create mode 100644 requirements.txt
 create mode 100644 runtime.txt
```

### PASSO 5: Crea Repository su GitHub

1. Vai a https://github.com/new
2. Nome: `social-media-downloader`
3. Descrizione: `Social Media Downloader API - Download from Instagram, Facebook, TikTok, YouTube`
4. Public (opzionale)
5. **NON inizializzare con README** (lo hai già)
6. Clicca "Create repository"

### PASSO 6: Connetti e Push

GitHub ti darà i comandi. Oppure:

```bash
git remote add origin https://github.com/YOUR_USERNAME/social-media-downloader.git
git branch -M main
git push -u origin main
```

Sostituisci `YOUR_USERNAME` con il tuo nome utente GitHub.

### PASSO 7: Verifica su GitHub

1. Vai a https://github.com/YOUR_USERNAME/social-media-downloader
2. Dovresti vedere tutti i file (tranne instagram_cookies.txt) ✅
3. README.md deve essere visibile nella homepage

---

## 🔄 DOPO IL PRIMO PUSH: Future Updates

Se vuoi aggiornare il codice:

```bash
# Nel tuo PC, modifica main.py (es. aggiungi frasi simpatiche)

# Poi:
git add main.py
git commit -m "Update: aggiunte frasi simpatiche per maria e franco"
git push origin main

# Render redeploya automaticamente! ✅
```

---

## ⚙️ PERSONALIZZAZIONE PRIMA DI PUSHARE (OPZIONALE)

### Aggiungi i Tuoi Creator Preferiti

Nel file `main.py`, cerca questa sezione:

```python
CREATOR_FRASI = {
    # Aggiungi qui i nomi che vuoi con le tue frasi personalizzate
    # Esempio: 'giovanni': 'il monello',
}
```

**Modifica in:**

```python
CREATOR_FRASI = {
    'giovanni': 'il monello',
    'francesca': 'la regina dei reel',
    'marco': 'il re del web',
    'luigi': 'il capo supremo',
}
```

Salvate le modifiche, poi fai il commit:

```bash
git add main.py
git commit -m "Update: personalizzati i nomi dei creator"
git push
```

---

## 📊 CHECKLIST FINALE

✅ Ho scaricato tutti i 6 file (main.py, requirements.txt, etc.)
✅ Ho copiato i file nella cartella `social-media-downloader`
✅ Ho verificato che tutti i file sono nella cartella (ls -la)
✅ Ho fatto `git init`
✅ Ho fatto `git add .` e `git status` (cookies NON devono essere tracciati)
✅ Ho fatto il primo `git commit`
✅ Ho creato il repository su GitHub
✅ Ho fatto `git remote add origin https://github.com/...`
✅ Ho fatto `git push -u origin main`
✅ Ho verificato che su GitHub vedo i file (senza cookies)
✅ Ho (opzionalmente) personalizzato i creator

**SE HAI CHECKATO TUTTO = SEI PRONTO! 🎉**

---

## 🎯 PROSSIMI STEP DOPO IL PUSH

1. **Connetti a Render**: Vai su render.com → Connetti GitHub
2. **Crea il servizio**: New → Web Service → Seleziona il repo
3. **Render configura automaticamente** da Procfile
4. **Deploy!**
5. **Aggiungi cookies via Shell Render** (leggi guide)
6. **Test**: `/status` e `/download`

---

## ⚠️ ERRORI COMUNI

### "fatal: not a git repository"
→ Non sei nella cartella giusta. Assicurati di essere in `social-media-downloader`

### "Permission denied: instagram_cookies.txt"
→ Non è un errore! Significa che il file non è stato tracciato (corretto!)

### "fatal: pathspec 'main.py' did not match any files"
→ Non hai copiato i file nella cartella. Copia main.py dal link [70]

### "The current branch master has no upstream branch"
→ Fai: `git push -u origin main` (invece di solo `git push`)

---

## 💡 QUICK REFERENCE

```bash
# Setup completo in 4 comandi:
git init
git config user.name "Your Name" && git config user.email "your@email.com"
git add . && git commit -m "Initial commit"
git remote add origin https://github.com/USERNAME/social-media-downloader.git
git push -u origin main

# Per future updates:
git add file.py
git commit -m "Update: description"
git push
```

---

**PRONTO? Inizia con PASSO 1 e seguir questo step! 🚀**
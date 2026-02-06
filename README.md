# 🤖 NelloTok - The Ultimate Social Media Downloader Bot 🚀

![Python Version](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python&logoColor=white)
![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![Render Deploy](https://img.shields.io/badge/Deploy-Render-black?style=for-the-badge&logo=render&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)

> *"Nello il cane è vecchio e saggio, le sue gambe cigolano, ma con i biscotti giusti (cookies) ti porta qualsiasi video!"* 🐶🦴

Un bot Telegram **professionale, robusto e gratuito** progettato per scaricare media da tutte le principali piattaforme social (**TikTok, Instagram, Facebook, YouTube**) rimuovendo watermark, processando caroselli ed aggirando le protezioni anti-bot tramite l'uso avanzato dei cookie.

---

## 📖 Indice dei Contenuti

1.  [🌟 Perché questo Bot?](#-perché-questo-bot)
2.  [✨ Funzionalità Avanzate](#-funzionalità-avanzate)
3.  [🍪 Il "Grande Firewall" e i Cookies](#-il-grande-firewall-e-i-cookies-importante)
4.  [🛠️ Requisiti Preliminari](#️-requisiti-preliminari)
5.  [🚀 Guida Completa all'Installazione](#-guida-completa-allinstallazione)
    *   [Fase 1: Creare il Bot su Telegram](#fase-1-creare-il-bot-su-telegram-🤖)
    *   [Fase 2: Estrarre i Biscotti (Cookies)](#fase-2-estrarre-i-biscotti-cookies-🍪-fondamentale)
    *   [Fase 3: Deploy su Render.com](#fase-3-deploy-su-rendercom-☁️)
6.  [⚙️ Configurazione Variabili d'Ambiente](#️-configurazione-variabili-dambiente)
7.  [🎮 Guida all'Uso](#-guida-alluso)
8.  [🚑 Risoluzione Problemi (Troubleshooting)](#-risoluzione-problemi-troubleshooting)
9.  [👨‍💻 Sviluppo Locale](#-sviluppo-locale)
10. [📜 Disclaimer](#-disclaimer)

---

## 🌟 Perché questo Bot?

La maggior parte dei bot online smette di funzionare dopo poche settimane perché i social network aggiornano le loro protezioni. **NelloTok** è diverso perché è progettato come un'applicazione "self-hosted" (che ospiti tu stesso) con funzionalità Enterprise:

*   **Non dipendi da API esterne** a pagamento che possono chiudere.
*   **Gestione Sessioni Reale**: Usa i cookie del tuo browser per simulare un utente reale.
*   **Privacy**: I video vengono scaricati sul server e inviati a te, nessuno traccia i tuoi download.
*   **Community Oriented**: Include classifiche e messaggi divertenti per gruppi di amici.

---

## ✨ Funzionalità Avanzate

### 🎥 Supporto Multi-Piattaforma Esteso
*   **TikTok**: Scarica video **senza logo/watermark** in alta definizione. Supporta anche gli slideshow di foto (li converte in album Telegram).
*   **Instagram**:
    *   **Reels**: Download istantaneo.
    *   **Post Video**: Download video dai feed.
    *   **Caroselli**: Scarica **tutte** le foto e i video di un post multiplo (album) e te li invia come un gruppo unico.
    *   **Storie**: (Sperimentale) Scarica storie se l'account è pubblico.
*   **Facebook**: Supporta video pubblici, Reel di Facebook e molti video da gruppi pubblici.
*   **YouTube**:
    *   **Shorts**: Download ottimizzato per i video verticali.
    *   **Video Classici**: Scarica video fino a 10 minuti (configurabile).

### 🤖 Intelligenza "Canina"
*   **Auto-Retry System**: Se un download fallisce (es. server occupato), Nello riprova automaticamente 3 volte con strategie diverse.
*   **Link Cleaner**: Rimuove automaticamente i parametri di tracciamento (`?igshid=...`, `?share_id=...`) dai link.
*   **Short Link Resolver**: Converte automaticamente link corti (es. `vm.tiktok.com`, `fb.watch`) nei link reali.
*   **File System Read-Only Fix**: Unico nel suo genere, gestisce automaticamente la copia dei cookie su file system di sola lettura (come Render) per evitare crash.

### 🏆 Funzioni Social & Gamification
*   **Classifica Settimanale**: Ogni volta che scarichi un video, guadagni punti!
*   **Podio**: Visualizza chi sono i TOP 3 downloader del gruppo con comando `/ranking`.
*   **Nello Humor**: Messaggi di errore personificati dal cane Nello (che ha l'artrosi e si stanca).

---

## 🍪 Il "Grande Firewall" e i Cookies (IMPORTANTE)

**Leggi attentamente**: Instagram e TikTok non vogliono che i bot scarichino i video. Hanno sistemi di sicurezza che bloccano qualsiasi richiesta non provenga da un browser loggato.

Per questo motivo, **NelloTok NON può funzionare "a vuoto"**. Ha bisogno di **Cookies**.
Un "Cookie" è un file di testo che dice al sito "Ehi, sono io (il tuo account), sono loggato e affidabile".

> ⚠️ **Senza i file cookie aggiornati, riceverai errori come "Sign in to confirm you're not a bot" o "403 Forbidden".**

Nella sezione installazione vedremo come estrarli. Ricorda che i cookie "scadono" (come i biscotti veri diventano stantii). Se il bot smette di funzionare dopo un mese, dovrai aggiornare i cookie.

---

## 🛠️ Requisiti Preliminari

1.  **Account Telegram** (ovviamente).
2.  **Account GitHub** (per copiare il codice).
3.  **Account Render.com** (per ospitare il bot gratis).
4.  **PC/Mac** con browser Google Chrome, Edge o Firefox.
5.  Un account **Instagram** (consigliato crearne uno secondario "da battaglia" per non rischiare nulla sul tuo principale, anche se il rischio è basso).

---

## 🚀 Guida Completa all'Installazione

### Fase 1: Creare il Bot su Telegram 🤖

1.  Apri Telegram e cerca l'utente **@BotFather** (l'ha la spunta blu).
2.  Avvia la chat e scrivi (o clicca): `/newbot`
3.  **Nome**: Scegli come si chiamerà il bot nella chat (es. `Super Scaricatore 3000`).
4.  **Username**: Scegli l'ID univoco. **DEVE** finire con `bot` (es. `MioGruppoDownloaderBot`).
5.  ✅ **Vittoria!** BotFather ti risponderà con un messaggio contenente il **TOKEN API**.
    *   È una stringa lunga tipo: `123456789:AAHdqTcv...`
    *   **COPIALO E CUSTODISCILO GELOSAMENTE.** Chi ha questo token controlla il bot.

### Fase 2: Estrarre i Biscotti (Cookies) 🍪 [FONDAMENTALE]

Questa è la parte che distingue un bot funzionante da uno rotto.

1.  **Installa l'estensione browser**:
    *   Cerca su Google: **"Get cookies.txt LOCALLY"** per Chrome/Edge/Firefox.
    *   Assicurati che sia un'estensione sicura e con buone recensioni.

2.  **Estrai Instagram**:
    *   Vai su `www.instagram.com` e fai il login con l'account che il bot userà.
    *   Clicca sull'icona dell'estensione dei cookie in alto a destra.
    *   Clicca su **"Export"** o **"Copia"**. Assicurati di selezionare "Netscape format" se richiesto (è lo standard).
    *   Salva il contenuto in un file di testo chiamato `instagram_cookies.txt` (o incollalo da qualche parte temporaneamente).

3.  **Estrai Altri Social (Opzionale ma Raccomandato)**:
    *   Vai su `www.tiktok.com`, fai login, estrai i cookie -> `tiktok_cookies.txt`.
    *   Vai su `www.youtube.com`, (login opzionale ma aiuta per i video 18+), estrai -> `youtube_cookies.txt`.
    *   Vai su `www.facebook.com`, fai login, estrai -> `facebook_cookies.txt`.

### Fase 3: Deploy su Render.com ☁️

Render ci permette di ospitare il codice Docker gratuitamente.

1.  **Fork del progetto**:
    *   Vai sulla pagina GitHub di questo progetto.
    *   Clicca il pulsante **"Fork"** in alto a destra per creare una tua copia.

2.  **Crea il Web Service**:
    *   Vai su [dashboard.render.com](https://dashboard.render.com/).
    *   Clicca **New +** -> **Web Service**.
    *   Seleziona "Build and deploy from a Git repository".
    *   Scegli il repository che hai appena forkato.

3.  **Configurazione Base**:
    *   **Name**: Un nome a piacere (es. `nello-bot-telegram`).
    *   **Region**: `Frankfurt (EU Central)` (la più veloce per l'Italia).
    *   **Branch**: `main`.
    *   **Runtime**: `Docker` (Render dovrebbe rilevarlo automaticamente dalla presenza del `Dockerfile`).
    *   **Instance Type**: `Free`.

4.  **Variabili d'Ambiente (Environment Variables)**:
    Scorri giù fino alla sezione "Environment Variables" e inserisci queste chiavi:

    | Chiave (Key) | Valore (Value) | Note |
    | :--- | :--- | :--- |
    | `TELEGRAM_BOT_TOKEN` | `Il_Tuo_Token_Di_BotFather` | Incolla quello preso al punto 1. |
    | `ADMIN_USER_ID` | `12345678` | Il tuo ID Telegram numerico (scrivilo a @userinfobot per scoprirlo). |
    | `PORT` | `8080` | Obbligatorio per Render. |
    | `LOG_LEVEL` | `INFO` | Per vedere cosa succede. |

5.  **Configurazione COOKIES (Secret Files)**:
    Sotto le variabili d'ambiente, trovi la sezione **"Secret Files"**. Questa è la "cassaforte" per i tuoi biscotti.
    
    Clicca **Add Secret File** per ogni file cookie che hai:

    *   **File 1**:
        *   Filename: `INSTAGRAM_COOKIES`
        *   Content: (Incolla tutto il testo estratto da instagram)
    *   **File 2**:
        *   Filename: `TIKTOK_COOKIES`
        *   Content: (Incolla tutto il testo estratto da tiktok)
    *   **File 3**:
        *   Filename: `YOUTUBE_COOKIES`
        *   Content: (Incolla testo youtube)
    *   **File 4**:
        *   Filename: `FACEBOOK_COOKIES`
        *   Content: (Incolla testo facebook)

    > **NOTA TECNICA**: Il bot cercherà questi file automaticamente in `/etc/secrets/` e ne farà una copia temporanea scrivibile per funzionare correttamente.

6.  **Lancio! 🚀**:
    Clicca su **Create Web Service**.
    Render inizierà a costruire il container (Build). Ci vorranno dai 3 ai 6 minuti la prima volta.
    Quando vedrai la scritta verde **Live** nei log, il bot è attivo!

---

## ⚙️ Configurazione Variabili d'Ambiente

Ecco la lista completa di tutte le variabili che puoi usare per personalizzare il bot (nel file `.env` locale o su Render):

| Variabile | Default | Descrizione |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | (Richiesto) | Il token del bot. |
| `ADMIN_USER_ID` | `0` | ID dell'amministratore (per comandi speciali, se implementati). |
| `ALLOWED_USER_IDS` | (Vuoto) | Lista ID utenti separati da virgola. Se impostata, il bot risponde SOLO a questi utenti. |
| `MAX_VIDEO_DURATION` | `600` | Durata massima video in secondi (default 10 min). |
| `MAX_FILE_SIZE` | `50MB` | Limite dimensione file (limite bot Telegram standard). |
| `TEMP_DIR` | `/tmp` | Cartella temporanea per i download. |

---

## 🎮 Guida all'Uso

### Aggiungere il Bot al Gruppo
1.  Aggiungi il bot al gruppo Telegram desiderato.
2.  **Promuovilo Amministratore** (Tasto destro sul bot nel gruppo -> Promuovi ad Admin).
    *   *Perché?* Deve avere il permesso di "Eliminare messaggi" per cancellare il tuo link originale e sostituirlo con il video, tenendo pulita la chat.

### Scaricare un Video
È semplicissimo: invia il link!
*   ✅ `https://www.instagram.com/reel/Cm12345/`
*   ✅ `https://vm.tiktok.com/ZM12345/`
*   ✅ `https://youtube.com/shorts/AbC123`

Il bot:
1.  Leggerà il messaggio.
2.  Tenterà di scaricare il video.
3.  Cancellerà il tuo messaggio originale.
4.  Invierà il video con didascalia:
    > 📹 **Video TikTok**
    > *Scaricato da @TuoNome*

### Comandi
*   `/start` - Verifica se il bot è vivo.
*   `/ranking` - Mostra la "Hall of Fame" della settimana.
*   `/help` - Mostra info di aiuto.

---

## 🚑 Risoluzione Problemi (Troubleshooting)

### 🔴 "Sign in to confirm you're not a bot" / Errore 403 / Video non scaricato
**Causa**: I cookies sono scaduti o Instagram/TikTok ha invalidato la sessione.
**Soluzione**:
1.  Rifai la procedura di **Estrazione Cookies** dal browser (Fase 2).
2.  Vai su Render -> Dashboard -> Secret Files.
3.  Modifica i file esistenti incollando i **nuovi** valori.
4.  Vai su "Manual Deploy" -> "Deploy latest commit" per riavviare il bot.

### 🔴 "Format not available" (YouTube)
**Causa**: YouTube cambia spesso i formati video degli Shorts.
**Soluzione**: Il bot è stato aggiornato per provare diverse combinazioni di formati automaticamente. Se persiste, prova ad aggiornare i cookie di YouTube.

### 🔴 "Read-only file system" nei log
**Causa**: Render non permette di scrivere nella cartella dei Secret Files.
**Soluzione**: **Risolto!** Il codice attuale rileva questo errore e copia automaticamente i cookie in una cartella temporanea (`/tmp`) scrivibile prima di usarli. Non devi fare nulla.

### 🔴 Il bot non risponde proprio
**Causa**: Probabilmente è andato in "Sleep" (il piano Free di Render spegne il bot dopo 15 min di inattività).
**Soluzione**:
1.  Invia un messaggio e aspetta ~1 minuto. Il bot si risveglierà.
2.  *Opzionale*: Usa un servizio di "Uptime Monitor" (come UptimeRobot) gratuito che pinga l'URL del tuo servizio Render ogni 5 minuti per tenerlo sempre sveglio.

---

## 👨‍💻 Sviluppo Locale

Se sei uno sviluppatore e vuoi modificare il codice:

1.  Clona la repo:
    ```bash
    git clone https://github.com/tuo-user/NelloTok.git
    cd NelloTok
    ```
2.  Crea un ambiente virtuale:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate  # Windows
    source venv/bin/activate # Mac/Linux
    ```
3.  Installa dipendenze:
    ```bash
    pip install -r requirements.txt
    ```
4.  Crea file `.env` locale e inserisci i token.
5.  Piazza i file `.txt` dei cookie nella cartella principale del progetto.
6.  Avvia:
    ```bash
    python bot.py
    ```

---

## 📜 Disclaimer

Questo bot è un progetto open source a scopo educativo.
L'autore non si assume alcuna responsabilità per l'uso improprio dello strumento.
Scaricare contenuti protetti da copyright senza permesso potrebbe violare i termini di servizio delle piattaforme.
Usa i cookie responsabilmente: usare il tuo account personale principale potrebbe (in rari casi) portare a shadowban temporanei se scarichi migliaia di video al giorno. **Si consiglia l'uso di account account secondari/burner.**

---

*Creato con ❤️, Python e tanti 🦴 da Nello.*
*Buon divertimento!*

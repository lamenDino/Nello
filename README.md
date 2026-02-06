# 🤖 NelloTok - Ultimate Social Downloader Bot

![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue?style=for-the-badge&logo=telegram)
![Render](https://img.shields.io/badge/Deploy-Render-black?style=for-the-badge&logo=render)

Un bot Telegram avanzato e robusto per scaricare video senza watermark, reels, storie e caroselli da **TikTok**, **Instagram**, **Facebook** e **YouTube Shorts**. 

> 🐶 *Nello il cane è vecchio e saggio, ma con i biscotti giusti (cookies) ti porta qualsiasi video!*

---

## ✨ Funzionalità

*   🎥 **TikTok**: Video senza watermark.
*   📸 **Instagram**: Reels, Post Video e **Caroselli** (scarica tutte le foto/video in un album).
*   📘 **Facebook**: Video pubblici e Reels.
*   🔴 **YouTube**: Shorts e Video classici (fino a 10 minuti).
*   🍪 **Gestione Avanzata Cookies**: Supporto per cookies criptati, failover su variabili d'ambiente e bypass blocchi geografici.
*   🏆 **Ranking Settimanale**: Classifica dei topdownloader del gruppo con medaglie.
*   🔄 **Auto-Retry**: Sistema intelligente che riprova il download in caso di errori temporanei.
*   🧹 **Link Cleaning**: Rimuove automaticamente i parametri di tracciamento e converte short link.

---

## 🛠️ Prerequisiti

Prima di iniziare, assicurati di avere:

1.  Un account **Telegram**.
2.  Un account **Render.com** (per l'hosting gratuito).
3.  Un browser (Chrome/Edge/Firefox) su PC per estrarre i cookie.
4.  L'estensione browser **"Get cookies.txt LOCALLY"** (o simile) per estrarre i cookie in formato Netscape.

---

## 🚀 Guida all'Installazione (Passo dopo Passo)

### FASE 1: Creazione del Bot Telegram 🤖

1.  Apri Telegram e cerca **@BotFather**.
2.  Avvia la chat e invia il comando `/newbot`.
3.  Segui le istruzioni:
    *   Scegli un **Nome** (es. `Nello Downloader`).
    *   Scegli uno **Username** (deve finire con `bot`, es. `NelloTokBot`).
4.  BotFather ti darà un **TOKEN** (es. `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`). 
    *   ⚠️ **Conservalo!** Ti servirà su Render.

### FASE 2: Estrazione dei Cookie 🍪 (Fondamentale!)

Per evitare che Instagram/TikTok blocchino il bot, devi fornirgli i "biscotti" (cookies) di un account reale.

1.  Installa l'estensione **"Get cookies.txt LOCALLY"** sul tuo browser.
2.  **Instagram**:
    *   Vai su `instagram.com` e assicurati di essere loggato con un account (meglio se secondario).
    *   Clicca sull'estensione e premi **"Export"**.
    *   Salva il file come `instagram_cookies.txt` (o apri il file e copia tutto il testo).
3.  **TikTok, Facebook, YouTube**:
    *   Ripeti la stessa procedura sui rispettivi siti (`tiktok.com`, `facebook.com`, `youtube.com`).
    *   Salva/Copia il contenuto dei cookie.

> **NOTA:** I cookie scadono dopo un po' di tempo o se fai logout dal browser. Se il bot smette di funzionare, dovrai rifare questa procedura e aggiornare le variabili su Render.

### FASE 3: Deploy su Render ☁️

Render è la piattaforma che ospiterà il tuo bot 24/7.

1.  **Fork del Repository**: Clicca "Fork" in alto a destra su GitHub per copiare questo progetto nel tuo profilo.
2.  Vai su [dashboard.render.com](https://dashboard.render.com/) e clicca **"New +"** -> **"Web Service"**.
3.  Seleziona "Build and deploy from a Git repository" e scegli il repo che hai appena forkato.
4.  Configura il servizio:
    *   **Name**: Scegli un nome (es. `nello-bot`).
    *   **Region**: Frankfurt (o quella più vicina).
    *   **Branch**: `main`.
    *   **Runtime**: `Docker`.
    *   **Plan**: Free.

5.  **Environment Variables** (Variabili d'Ambiente):
    Clicca su "Advanced" o scendi fino alla sezione Environment Variables e aggiungi:

    | Key | Value | Descrizione |
    | :--- | :--- | :--- |
    | `TELEGRAM_BOT_TOKEN` | `123456...` | Il token ricevuto da BotFather. |
    | `ADMIN_USER_ID` | `tuo_id` | Il tuo ID numerico Telegram (chiedilo a @userinfobot). |
    | `PORT` | `8080` | La porta su cui ascolterà il server. |
    | `LOG_LEVEL` | `INFO` | Livello di dettaglio dei log. |

6.  **Secret Files / Cookies** (Metodo Consigliato):
    Poiché inserire tutto il testo dei cookie nelle variabili può essere scomodo, usa la sezione **"Secret Files"** su Render (appena sotto le variabili d'ambiente).
    
    Crea i seguenti file e incolla dentro il contenuto estratto al *Fase 2*:
    
    *   **Filename**: `INSTAGRAM_COOKIES`
        *   **Contents**: (Incolla tutto il testo del file `instagram_cookies.txt`)
    *   **Filename**: `TIKTOK_COOKIES`
        *   **Contents**: (Incolla tutto il testo del file tiktok)
    *   **Filename**: `FACEBOOK_COOKIES`
        *   **Contents**: (Incolla tutto il testo del file facebook)
    *   **Filename**: `YOUTUBE_COOKIES`
        *   **Contents**: (Incolla tutto il testo del file youtube)

    > **Alternativa rapida**: Puoi anche incollare il contenuto direttamente nelle Environment Variables usando le stesse Key (`INSTAGRAM_COOKIES`, ecc.), il bot è programmato per leggere da entrambe le fonti!

7.  Premi **Create Web Service**.
8.  Attendi che il deploy finisca (ci vorranno circa 2-5 minuti). Se vedi "Build successful" e poi "Live", il bot è online!

---

## 🎮 Come Usare il Bot

1.  Aggiungi il bot al tuo gruppo di amici o scrivigli in privato.
2.  Assicurati che il bot sia **Amministratore** del gruppo (per poter cancellare i messaggi con i link originali e sostituirli con i video).
3.  **Invia un Link**:
    *   Copia un link di un video (TikTok, Reel IG, Shorts YT).
    *   Incollalo nella chat.
4.  **Magia**: Il bot cancellerà il tuo link e invierà il video scaricato con una didascalia carina.

### Comandi Disponibili

*   `/start` - Avvia il bot e mostra il messaggio di benvenuto.
*   `/help` - Mostra la guida.
*   `/ranking` - Mostra la classifica settimanale di chi ha scaricato più video.

---

## 🚑 Risoluzione Problemi (Troubleshooting)

*   **Il download fallisce con "Sign in to confirm you're not a bot"**:
    *   Significa che i **cookie sono scaduti**. Riesportali dal browser e aggiorna i Secret Files su Render. Riavvia il servizio.
*   **Errore "Read-only file system"**:
    *   Il bot è stato aggiornato per gestire questo errore automaticamente copiando i file in una cartella temporanea. Assicurati di avere l'ultima versione del codice.
*   **YouTube Shorts "Format not available"**: 
    *   A volte YouTube cambia i formati. Il bot prova diverse combinazioni. Se persiste, prova ad aggiornare i cookie di YouTube.
*   **Il bot non risponde**:
    *   Controlla i log su Render. Se vedi errori rossi, copiali e chiedi aiuto (o a ChatGPT!).

---

## 👨‍💻 Sviluppo Locale

Se vuoi modificare il codice sul tuo PC:

1.  Clona la repo.
2.  Crea un file `.env` nella root con le variabili (vedi Fase 3).
3.  Metti i file `cookies.txt`, `tiktok_cookies.txt`, ecc. nella cartella principale.
4.  Esegui:
    ```bash
    pip install -r requirements.txt
    python bot.py
    ```

---

*Creato con ❤️ (e tanti biscotti) da Nello.*

# Vocali italiani con Groq Free

La trascrizione dei vocali Telegram, WhatsApp e Discord può usare Groq direttamente
dal servizio principale, evitando la coda dei video e Whisper locale sul downloader.
I sottotitoli dei video continuano a usare il percorso esistente.

## Attivazione

1. Creare un account **Free** su https://console.groq.com e una API key.
2. Nel servizio Render principale (`nello-9amr`), salvare `GROQ_API_KEY` come
   variabile riservata. Non serve copiarla sul downloader.
3. Impostare `VOICE_TRANSCRIBER=groq` e distribuire il servizio.

Senza selezione esplicita, la presenza della chiave abilita Groq; senza chiave
resta il riconoscimento locale. `VOICE_TRANSCRIBER=local` ripristina esplicitamente
il percorso precedente. Una selezione non valida o una chiave mancante con
`VOICE_TRANSCRIBER=groq` produce un avviso, senza avviare il riconoscimento locale.

La chiave API non permette di verificare il piano: l'account deve restare Free.
Non attivare il piano Developer se il requisito è costo zero. Il codice non
esegue upgrade e non passa ad altri provider quando incontra un limite.

## Comportamento

- Massimo 8 MiB e 180 secondi per vocale; il file originale resta nella chat.
- Decodifica locale limitata a PCM mono 16 kHz, poi un'unica richiesta
  `whisper-large-v3` per conservare il contesto del vocale.
- Rilevamento automatico della lingua, senza imporre italiano o tradurre.
  Solo un risultato classificato italiano viene mostrato. La classificazione
  riguarda il file intero: non è una garanzia per vocali che mescolano lingue.
- Passaggio opzionale `openai/gpt-oss-20b` per la punteggiatura. Il risultato è
  accettato solo se parole, ordine e numeri sono identici; altrimenti resta
  il testo riconosciuto. Non riscrive né riassume il contenuto.
- Le ripetizioni anomale vengono rifiutate/segnalate. Nessun testo viene salvato
  nei log; i file temporanei vengono cancellati anche in caso di errore.
- Un limite HTTP 429 o un errore produce un avviso: nessun tentativo automatico
  contro il motore locale lento. La punteggiatura può fallire senza perdere
  la trascrizione riuscita.
- Il risultato arriva completo, senza suddividerlo artificialmente in blocchi
  progressivi. Su Telegram sostituisce il messaggio “Audio ricevuto”.

La CPU locale non esegue più Whisper né avvia Java/LanguageTool in questa modalità.
I timeout massimi sono 25 s per decodifica, 75 s per riconoscimento e 20 s per
punteggiatura; sono limiti di arresto, non tempi promessi.

## Quota e dati

Alla verifica del 22 settembre 2026, la documentazione Free indica per Whisper
20 richieste/minuto, 2.000/giorno, 7.200 secondi audio/ora e 28.800/giorno.
Per il modello di punteggiatura sono indicati 30 richieste/minuto, 1.000/giorno,
8.000 token/minuto e 200.000/giorno. Le quote dell'account prevalgono e sono
condivise da tutta l'organizzazione. Il codice rispetta gli errori 429 senza
cercare di aggirare le quote.

Gli audio e il testo da formattare vengono inviati a Groq. È disponibile
Zero Data Retention nei Data Controls dell'account. Non va presentato come
attivo senza verificarne l'impostazione.

- https://console.groq.com/docs/speech-to-text
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/your-data

## Verifica

`python -m unittest test_remote_voice test_voice_messages`

I test non inviano audio a Groq: usano un server HTTP locale. Le prove reali
richiedono una chiave Free e audio autorizzato. Misurare separatamente il tempo
del servizio remoto e quello completo di download/consegna nella chat.

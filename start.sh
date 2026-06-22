#!/usr/bin/env bash
# Avvia il provider po_token (bgutil) in background, poi il bot Telegram.
# Il plugin yt-dlp 'bgutil-ytdlp-pot-provider' (installato via pip) interroga
# automaticamente questo server locale su http://127.0.0.1:4416 per ottenere i
# po_token richiesti da YouTube sugli IP datacenter.

BGUTIL_MAIN="/opt/bgutil/server/build/main.js"

if [ -f "$BGUTIL_MAIN" ]; then
    node "$BGUTIL_MAIN" --port 4416 >/tmp/bgutil.log 2>&1 &
    echo "bgutil po_token provider avviato su :4416 (pid $!)"
else
    echo "ATTENZIONE: $BGUTIL_MAIN non trovato, il bot parte senza provider po_token"
fi

# Worker WhatsApp (Baileys): avviato solo se WHATSAPP_ENABLED=1. Aspetta da solo
# che il bridge Python sia pronto (vedi wa_worker.js). Il QR del primo
# collegamento comparira' in questi log.
if [ "$WHATSAPP_ENABLED" = "1" ]; then
    if [ -f "/app/wa/wa_worker.js" ]; then
        node /app/wa/wa_worker.js >/tmp/wa_worker.log 2>&1 &
        echo "worker WhatsApp avviato (pid $!) - log: /tmp/wa_worker.log"
        # mostra i log del worker (incluso il QR) nello stream principale
        ( tail -n +1 -F /tmp/wa_worker.log & ) 2>/dev/null
    else
        echo "ATTENZIONE: /app/wa/wa_worker.js non trovato, worker WhatsApp non avviato"
    fi
fi

exec python bot.py

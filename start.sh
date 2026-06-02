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

exec python bot.py

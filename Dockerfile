# Dockerfile per il bot TikTok Telegram
FROM python:3.11-slim

# Imposta la directory di lavoro
WORKDIR /app

# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copia i file dei requisiti
COPY requirements.txt .

# Installa le dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice dell'applicazione
COPY . .

# Crea directory per i log
RUN mkdir -p /app/logs

# Esponi la porta (per webhook, opzionale)
EXPOSE 8080

# Comando per avviare il bot
CMD ["python", "bot.py"]
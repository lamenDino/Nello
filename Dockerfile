FROM python:3.11-slim

WORKDIR /app

# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y \
    gcc \
    ffmpeg \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements
COPY requirements.txt .

# Installa dipendenze Python
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia il codice
COPY . .

# Esponi porta (Render la assegna dinamicamente)
EXPOSE 8080

# Start del bot
CMD ["python", "bot.py"]

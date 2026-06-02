FROM python:3.11-slim
WORKDIR /app

# Node 20+ richiesto da bgutil (il nodejs di Debian slim e' troppo vecchio): uso NodeSource
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    ffmpeg \
    libxml2-dev libxslt-dev \
    curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# po_token provider (bgutil): genera i po_token necessari a YouTube su IP datacenter.
# Buildato in fase di immagine; verra' avviato come server locale da start.sh.
RUN git clone --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
 && cd /opt/bgutil/server \
 && npm install \
 && npx tsc

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Avvia il provider po_token + il bot
CMD ["bash", "start.sh"]

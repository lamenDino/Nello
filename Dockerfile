FROM python:3.11-slim
WORKDIR /app

# Node 20+ richiesto da bgutil (il nodejs di Debian slim e' troppo vecchio): uso NodeSource
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    ffmpeg \
    libxml2-dev libxslt-dev \
    curl ca-certificates gnupg unzip \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# Deno: runtime JS usato dal solver EJS di yt-dlp per risolvere le sfide nsig/signature
# (senza, YouTube scarta i formati -> "Requested format is not available").
RUN curl -fsSL https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip \
 && unzip /tmp/deno.zip -d /usr/local/bin/ \
 && rm /tmp/deno.zip \
 && chmod +x /usr/local/bin/deno

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

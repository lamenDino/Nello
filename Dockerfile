FROM python:3.11-slim
WORKDIR /app

# Node 20+ richiesto da bgutil (il nodejs di Debian slim e' troppo vecchio): uso NodeSource
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    ffmpeg \
    libxml2-dev libxslt-dev \
    curl ca-certificates gnupg unzip bzip2 \
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

# Small CPU-only speaker models. Download once at build time and verify hashes.
RUN mkdir -p /opt/voice-speakers \
 && curl -fSL --retry 3 https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_speakerverification_speakernet.onnx -o /opt/voice-speakers/speaker.onnx \
 && echo 'd204dc8aac0014b8543f05fc8e310510c7022bc65b6452c203ec205ef7a66b23  /opt/voice-speakers/speaker.onnx' | sha256sum -c - \
 && curl -fSL --retry 3 https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2 -o /tmp/speakers.tar.bz2 \
 && echo '24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488  /tmp/speakers.tar.bz2' | sha256sum -c - \
 && tar -xjf /tmp/speakers.tar.bz2 -C /tmp \
 && cp /tmp/sherpa-onnx-pyannote-segmentation-3-0/model.int8.onnx /opt/voice-speakers/segmentation.onnx \
 && cp /tmp/sherpa-onnx-pyannote-segmentation-3-0/LICENSE /opt/voice-speakers/SEGMENTATION-LICENSE \
 && rm -rf /tmp/sherpa-onnx-pyannote-segmentation-3-0 /tmp/speakers.tar.bz2

# Dipendenze del worker WhatsApp (Baileys). Buildato sempre; il worker viene
# avviato da start.sh solo se WHATSAPP_ENABLED=1.
COPY wa/package.json /app/wa/package.json
RUN cd /app/wa && npm install --omit=dev --no-audit --no-fund

COPY . .

EXPOSE 8080

# Avvia il provider po_token + il bot
CMD ["bash", "start.sh"]

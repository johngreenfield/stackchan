FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_MODEL=base.en \
    WHISPER_MODEL_DIR=/opt/models/whisper \
    PIPER_MODEL_DIR=/opt/models/piper \
    PIPER_MODEL_PATH=/opt/models/piper/en_US-lessac-medium.onnx \
    DATA_DIR=/app/data \
    PORT=8765

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libopus-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Pre-download Whisper base.en and Piper English voice during build so startup is instant & offline-ready
RUN mkdir -p /opt/models/whisper /opt/models/piper /app/data && \
    python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8', download_root='/opt/models/whisper')" && \
    curl -fSL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" -o /opt/models/piper/en_US-lessac-medium.onnx && \
    curl -fSL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" -o /opt/models/piper/en_US-lessac-medium.onnx.json

COPY app ./app
COPY static ./static

EXPOSE 8765

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8765} --ws-ping-interval 30 --ws-ping-timeout 30"]

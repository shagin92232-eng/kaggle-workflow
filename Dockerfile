FROM python:3.11-slim

# FFmpeg + libs needed by opencv/mediapipe
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Job data + music library live in volumes (see docker-compose.yml)
RUN mkdir -p data/jobs music/library assets/overlays

CMD ["python", "-m", "bot.main"]

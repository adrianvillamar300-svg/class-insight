FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN pip install yt-dlp

RUN yt-dlp --update-to nightly 2>/dev/null || true
RUN python3 -c "import yt_dlp; yt_dlp.YoutubeDL({'quiet':True}).download([])" 2>/dev/null || true

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

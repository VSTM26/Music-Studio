FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV NO_OPEN_BROWSER=1
ENV APP_HOST=0.0.0.0
ENV MUSIC_STUDIO_HELPER_ONLY=1

EXPOSE 4173

CMD ["python", "main.py", "--helper-only"]

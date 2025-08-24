# Python + ffmpeg 포함 이미지
FROM python:3.11-slim

# ffmpeg 설치
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server.py index.html robots.txt sitemap.xml ./

# Render/Cloud Run 등이 지정하는 $PORT 지원
EXPOSE 8000
ENV PYTHONUNBUFFERED=1

CMD ["python", "server.py"]
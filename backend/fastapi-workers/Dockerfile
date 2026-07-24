FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-nanum \
    fontconfig \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY fastapi-workers/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
# CPU 전용 PyTorch 설치로 CUDA 패키지 다운로드 스킵 (빌드 시간 단축 및 용량 최적화)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
# Chromium is installed once in the worker image. Debian trixie/arm64 is not
# supported by Playwright's `--with-deps` script (it requests obsolete Ubuntu
# font packages), so its supported runtime libraries are installed explicitly.
# Evidence requests reuse this browser process but create an isolated context
# per capture.
ENV PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2t64 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libglib2.0-0 libnspr4 libnss3 libx11-6 libx11-xcb1 \
    libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
    libxrandr2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/* \
    && playwright install chromium

COPY fastapi-workers/ .
COPY shared/ /app/shared/

# Create data directory for generated files
RUN mkdir -p /app/data /app/assets/fonts

EXPOSE 8001

# Production: no --reload flag
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

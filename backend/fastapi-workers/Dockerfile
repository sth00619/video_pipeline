FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-nanum \
    fontconfig \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
# CPU 전용 PyTorch 설치로 CUDA 패키지 다운로드 스킵 (빌드 시간 단축 및 용량 최적화)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for generated files
RUN mkdir -p /app/data

EXPOSE 8001

# Production: no --reload flag
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

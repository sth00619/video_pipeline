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
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for generated files
RUN mkdir -p /app/data

EXPOSE 8001

# Production: no --reload flag
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

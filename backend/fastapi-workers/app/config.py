import os

APP_MODE = os.getenv("APP_MODE", "local")

# S3/MinIO
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "ai-video-assets")

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# API Keys (prod only)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
KLING_API_KEY = os.getenv("KLING_API_KEY", "")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")

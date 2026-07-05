from app.config import APP_MODE
from app.providers.base import (
    TranscriptProvider, LLMProvider, ImageProvider,
    VideoProvider, TTSProvider, TrendingVideoAnalyzer
)
from app.providers.mock.transcript import WhisperTranscriptProvider
from app.providers.mock.llm import MockLLMProvider
from app.providers.mock.assets import MockImageProvider, MockVideoProvider, MockTTSProvider
from app.providers.mock.trending import MockTrendingVideoAnalyzer


def get_transcript_provider() -> TranscriptProvider:
    return WhisperTranscriptProvider(model_size="base")


def get_llm_provider() -> LLMProvider:
    if APP_MODE == "prod":
        from app.providers.real.llm import ClaudeProvider
        return ClaudeProvider()
    return MockLLMProvider()


def get_image_provider() -> ImageProvider:
    """Nana Banana AI 이미지 프로바이더 (pollinations.ai 기반, 무인증)"""
    try:
        from app.providers.real.image import NanaBananaProvider
        return NanaBananaProvider()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"NanaBananaProvider 로드 실패, Mock 사용: {e}")
        return MockImageProvider()


def get_video_provider() -> VideoProvider:
    if APP_MODE == "prod":
        from app.providers.real.video import KlingProvider
        return KlingProvider()
    return MockVideoProvider()


def get_tts_provider() -> TTSProvider:
    if APP_MODE == "prod":
        from app.providers.real.tts import ElevenLabsProvider
        return ElevenLabsProvider()
    return MockTTSProvider()


def get_trending_video_analyzer() -> TrendingVideoAnalyzer:
    """
    Phase 1 (Mock): 시뮬레이션 데이터
    Phase 2 (Real): YouTube Data API v3 통합 예정
    """
    if APP_MODE == "prod":
        from app.providers.real.trending import YouTubeTrendingAnalyzer
        return YouTubeTrendingAnalyzer()
    return MockTrendingVideoAnalyzer()

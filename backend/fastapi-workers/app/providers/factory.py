from app.config import APP_MODE
from app.providers.base import (
    TranscriptProvider, LLMProvider, ImageProvider,
    VideoProvider, TTSProvider, KeywordToolProvider
)
from app.providers.mock.transcript import WhisperTranscriptProvider
from app.providers.mock.llm import MockLLMProvider
from app.providers.mock.assets import MockImageProvider, MockVideoProvider, MockTTSProvider
from app.providers.mock.keyword import MockKeywordToolProvider


def get_transcript_provider() -> TranscriptProvider:
    return WhisperTranscriptProvider(model_size="base")


def get_llm_provider() -> LLMProvider:
    if APP_MODE == "prod":
        from app.providers.real.llm import ClaudeProvider
        return ClaudeProvider()
    return MockLLMProvider()


def get_image_provider() -> ImageProvider:
    if APP_MODE == "prod":
        from app.providers.real.image import NanaBananaProvider
        return NanaBananaProvider()
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


def get_keyword_tool_provider() -> KeywordToolProvider:
    if APP_MODE == "prod":
        from app.providers.real.keyword import RealKeywordToolProvider
        return RealKeywordToolProvider()
    return MockKeywordToolProvider()

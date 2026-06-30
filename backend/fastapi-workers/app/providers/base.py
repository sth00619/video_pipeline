from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TranscriptSegment:
    text: str
    start: float
    end: float
    words: list


@dataclass
class GeneratedAsset:
    asset_type: str
    local_path: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class TrendingVideo:
    """YouTube 영상 + 채널 통계 통합 모델"""
    title: str
    channel_title: str
    video_id: str
    views: int
    subscribers: int
    channel_avg_views: int
    published_at: str
    hours_since_publish: float


@dataclass
class ScriptResult:
    synopsis: str
    script: str
    estimated_minutes: float
    char_count: int


class TranscriptProvider(ABC):
    @abstractmethod
    def transcribe(self, video_path: str, language: str = "ko") -> list[TranscriptSegment]:
        pass


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        pass


class ImageProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, width: int = 1920, height: int = 1080) -> GeneratedAsset:
        pass


class VideoProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, duration: int = 5) -> GeneratedAsset:
        pass


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice_id: str) -> GeneratedAsset:
        pass


class TrendingVideoAnalyzer(ABC):
    """
    트렌딩 영상 풀 + 통계 조회 추상화.
    Phase 1 (Mock): 시뮬레이션
    Phase 2 (Real): YouTube Data API v3 (search.list + videos.list + channels.list)
    """
    @abstractmethod
    def collect(self, category: str, seed: str, limit: int = 30) -> list[TrendingVideo]:
        pass

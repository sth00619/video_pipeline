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
    meta: Optional[dict] = None


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
    channel_id: str = ""
    likes: int = 0
    comments: int = 0
    likes_available: bool = True
    comments_available: bool = True
    duration_seconds: float = 0.0
    average_view_duration_seconds: Optional[float] = None
    average_view_percentage: Optional[float] = None
    retention_available: bool = False
    statistics_as_of: str = ""
    channel_avg_views_is_sample: bool = False
    subscriber_count_available: bool = True
    # 라이브/라이브 다시보기는 일반 업로드와 시청 패턴이 달라 자동 주제
    # 근거에서 제외한다. YouTube의 liveStreamingDetails로 판별한 값이다.
    is_live: bool = False
    # 공개 videos.list snippet/contentDetails에서 가져오는 정보다. 이 값들은
    # 마인드맵·쇼츠/롱폼 분리·뉴스 클립 표시에 사용하며 LLM이 만들지 않는다.
    tags: list[str] | None = None
    category_id: str = ""
    performance_score: float = 0.0
    performance_grade: str = "C"
    # Only collected for S-grade videos, with a separate per-day quota cap.
    # These are public comments, never private Analytics data.
    top_comments: list[str] | None = None


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
    def collect(self, category: str, seed: str, limit: int = 30, recent_hours: Optional[int] = None) -> list[TrendingVideo]:
        pass

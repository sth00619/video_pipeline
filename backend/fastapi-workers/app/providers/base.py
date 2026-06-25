from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
class KeywordItem:
    keyword: str
    search_volume: int
    competition: str  # LOW / MEDIUM / HIGH
    reason: str = ""


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


class KeywordToolProvider(ABC):
    """키워드 탐색 도구 추상화 (KeywordTool.io, YouTube Data API 등)"""
    @abstractmethod
    def search(self, seed: str, limit: int = 5) -> list[KeywordItem]:
        pass


class ScriptProvider(ABC):
    """스크립트 생성 추상화 (LLM 활용)"""
    @abstractmethod
    def generate(self, keyword: str, target_minutes: int) -> ScriptResult:
        pass

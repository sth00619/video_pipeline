from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TranscriptSegment:
    text: str
    start: float
    end: float
    words: list  # [{word, start, end}]


@dataclass
class GeneratedAsset:
    asset_type: str   # image | video | audio
    local_path: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


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

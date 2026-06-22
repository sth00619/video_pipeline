import os
import tempfile
from app.providers.base import ImageProvider, VideoProvider, TTSProvider, GeneratedAsset


class MockImageProvider(ImageProvider):
    """Mock 이미지 — 검정 PNG 생성 (FFmpeg 사용)"""

    def generate(self, prompt: str, width: int = 1920, height: int = 1080) -> GeneratedAsset:
        path = tempfile.mktemp(suffix=".png")
        os.system(f'ffmpeg -f lavfi -i color=c=black:s={width}x{height}:d=1 -frames:v 1 {path} -y -loglevel quiet')
        return GeneratedAsset(asset_type="image", local_path=path, width=width, height=height)


class MockVideoProvider(VideoProvider):
    """Mock 비디오 — 검정 MP4 생성 (FFmpeg 사용)"""

    def generate(self, prompt: str, duration: int = 5) -> GeneratedAsset:
        path = tempfile.mktemp(suffix=".mp4")
        os.system(
            f'ffmpeg -f lavfi -i color=c=black:s=1920x1080:d={duration} '
            f'-f lavfi -i anullsrc=r=44100:cl=stereo '
            f'-t {duration} -c:v libx264 -c:a aac {path} -y -loglevel quiet'
        )
        return GeneratedAsset(asset_type="video", local_path=path, duration=duration)


class MockTTSProvider(TTSProvider):
    """Mock TTS — 무음 MP3 생성 (FFmpeg 사용)"""

    def synthesize(self, text: str, voice_id: str) -> GeneratedAsset:
        duration = max(2, len(text) // 10)
        path = tempfile.mktemp(suffix=".mp3")
        os.system(
            f'ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo '
            f'-t {duration} -c:a libmp3lame {path} -y -loglevel quiet'
        )
        return GeneratedAsset(asset_type="audio", local_path=path, duration=duration)

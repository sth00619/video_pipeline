import os
from faster_whisper import WhisperModel
from app.providers.base import TranscriptProvider, TranscriptSegment


class WhisperTranscriptProvider(TranscriptProvider):
    """faster-whisper 로컬 실행 — 완전 무료"""

    def __init__(self, model_size: str = "base"):
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, video_path: str, language: str = "ko") -> list[TranscriptSegment]:
        segments, _ = self.model.transcribe(
            video_path,
            language=language,
            word_timestamps=True
        )
        result = []
        for seg in segments:
            words = []
            if seg.words:
                words = [{"word": w.word, "start": w.start, "end": w.end} for w in seg.words]
            result.append(TranscriptSegment(
                text=seg.text.strip(),
                start=seg.start,
                end=seg.end,
                words=words
            ))
        return result

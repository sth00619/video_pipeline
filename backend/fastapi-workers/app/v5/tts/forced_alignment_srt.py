"""실제 오디오 기준 강제 정렬과 SRT 변환 유틸리티."""
from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Optional

import requests


ELEVEN_BASE = "https://api.elevenlabs.io/v1"


class AlignmentError(Exception):
    """음성 강제 정렬 실패."""


@dataclass
class WordTiming:
    text: str
    start: float
    end: float


@dataclass
class SubtitleCue:
    index: int
    start: float
    end: float
    text: str


def align_audio_to_text(audio_path: str, transcript: str, *, api_key: Optional[str] = None) -> list[WordTiming]:
    key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise AlignmentError("ELEVENLABS_API_KEY 미설정")
    with open(audio_path, "rb") as audio_file:
        response = requests.post(
            f"{ELEVEN_BASE}/forced-alignment", headers={"xi-api-key": key},
            files={"file": (os.path.basename(audio_path), audio_file, "audio/mpeg")},
            data={"text": transcript}, timeout=120,
        )
    if response.status_code != 200:
        raise AlignmentError(f"강제 정렬 실패: HTTP {response.status_code}")
    words = [WordTiming(str(word.get("text", "")), float(word.get("start", 0.0)), float(word.get("end", 0.0))) for word in response.json().get("words", [])]
    if not words:
        raise AlignmentError("강제 정렬 응답에 단어 타임스탬프가 없습니다.")
    return words


def tts_with_timestamps(text: str, voice_id: str, *, model_id: str = "eleven_multilingual_v2", api_key: Optional[str] = None, stability: float = 0.40, similarity_boost: float = 0.75, style: float = 0.0) -> tuple[bytes, list[WordTiming]]:
    key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise AlignmentError("ELEVENLABS_API_KEY 미설정")
    response = requests.post(
        f"{ELEVEN_BASE}/text-to-speech/{voice_id}/with-timestamps",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": text, "model_id": model_id, "voice_settings": {"stability": stability, "similarity_boost": similarity_boost, "style": style, "use_speaker_boost": True}},
        timeout=120,
    )
    if response.status_code != 200:
        raise AlignmentError(f"타임스탬프 TTS 실패: HTTP {response.status_code}")
    payload = response.json()
    alignment = payload.get("alignment") or {}
    words = _chars_to_words(alignment.get("characters") or [], alignment.get("character_start_times_seconds") or [], alignment.get("character_end_times_seconds") or [])
    return base64.b64decode(payload["audio_base64"]), words


def _chars_to_words(chars: list[str], starts: list[float], ends: list[float]) -> list[WordTiming]:
    words: list[WordTiming] = []
    current, start = "", None
    for index, char in enumerate(chars):
        if char.isspace():
            if current and start is not None:
                words.append(WordTiming(current, start, ends[index - 1]))
            current, start = "", None
        else:
            start = starts[index] if start is None else start
            current += char
    if current and start is not None:
        words.append(WordTiming(current, start, ends[-1]))
    return words


def words_to_cues(words: list[WordTiming], *, max_chars: int = 20, max_duration: float = 4.0, gap_split: float = 0.5) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    pending: list[WordTiming] = []
    def flush() -> None:
        if pending:
            cues.append(SubtitleCue(len(cues) + 1, pending[0].start, pending[-1].end, " ".join(word.text for word in pending).strip()))
            pending.clear()
    for word in words:
        if pending:
            duration = pending[-1].end - pending[0].start
            if word.start - pending[-1].end >= gap_split or len(" ".join(item.text for item in pending)) >= max_chars or duration >= max_duration:
                flush()
        pending.append(word)
    flush()
    return cues


def cues_to_srt(cues: list[SubtitleCue]) -> str:
    def timestamp(value: float) -> str:
        hours, remainder = divmod(int(value), 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = round((value - int(value)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    return "\n".join(f"{cue.index}\n{timestamp(cue.start)} --> {timestamp(cue.end)}\n{cue.text}\n" for cue in cues)


_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def normalize_korean_for_tts(text: str) -> str:
    """오디오 입력에서만 퍼센트를 자연어로 읽게 한다. 자막 원문은 보존한다."""
    return _PERCENT.sub(lambda match: f"{match.group(1)}퍼센트", text)

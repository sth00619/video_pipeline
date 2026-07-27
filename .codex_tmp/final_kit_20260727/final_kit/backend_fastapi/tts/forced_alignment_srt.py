"""
forced_alignment_srt.py — 싱크 문제의 근본 해결.

【진단】(첨부 테스트 영상 실측 기반)
- 영상: 24fps CFR, A/V 길이 일치 (60.04s vs 60.00s) → 프레임레이트 드리프트 아님.
- 즉 싱크 깨짐의 원인은 "자막 타임스탬프를 스크립트 텍스트 길이로 추정"하는 방식.
- 한국어는 숫자 확장("52,300원"→"오만이천삼백원") 때문에 글자수 비례 추정이 무너진다.
  (userMemories의 _map_timestamps_by_preprocessed_length() 버그와 동일 원인)

【해결 원칙】
자막은 스크립트가 아니라 "실제로 생성된 오디오"에 정렬해야 한다.
ElevenLabs Forced Alignment API는 오디오 + 텍스트를 받아 단어/문자 단위
타임스탬프를 돌려준다. 한국어 공식 지원. 이 타임스탬프가 자막의 단일 진실.

두 가지 경로 모두 지원:
  (A) TTS 생성 시 with-timestamps로 정렬 정보를 함께 받음 (1콜, AI 음성)
  (B) 사람이 녹음한 mp3 + 스크립트를 Forced Alignment에 넣어 정렬 (사람 음성)

경로 (B)가 핵심: 사용자가 "목소리 좋은 분이 직접 녹음"을 원하므로,
사람 음성에도 정확한 자막을 붙일 수 있어야 한다. Forced Alignment가 그 답.

의존성: requests
환경변수: ELEVENLABS_API_KEY
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import requests


ELEVEN_BASE = "https://api.elevenlabs.io/v1"


class AlignmentError(Exception):
    pass


@dataclass
class WordTiming:
    text: str
    start: float   # 초
    end: float


@dataclass
class SubtitleCue:
    index: int
    start: float
    end: float
    text: str


# ---------------------------------------------------------------------------
# 경로 (B): 사람 녹음 mp3 + 스크립트 → 단어 타임스탬프
#   docs: elevenlabs.io/docs/api-reference/forced-alignment/create
#   ⚠️ input text는 순수 문자열. JSON으로 감싸지 말 것.
# ---------------------------------------------------------------------------
def align_audio_to_text(
    audio_path: str,
    transcript: str,
    *,
    api_key: Optional[str] = None,
) -> list[WordTiming]:
    key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise AlignmentError("ELEVENLABS_API_KEY 미설정.")

    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
        data = {"text": transcript}   # 순수 문자열
        r = requests.post(
            f"{ELEVEN_BASE}/forced-alignment",
            headers={"xi-api-key": key},
            files=files,
            data=data,
            timeout=120,
        )
    if r.status_code != 200:
        raise AlignmentError(f"정렬 실패 {r.status_code}: {r.text[:300]}")

    payload = r.json()
    # 응답에는 characters[] 및 words[]가 온다. words 우선 사용.
    words = payload.get("words") or []
    out = []
    for w in words:
        out.append(WordTiming(
            text=w.get("text", ""),
            start=float(w.get("start", 0.0)),
            end=float(w.get("end", 0.0)),
        ))
    if not out:
        raise AlignmentError(f"words 비어 있음. 응답 키: {list(payload.keys())}")
    return out


# ---------------------------------------------------------------------------
# 경로 (A): TTS 생성 + 타임스탬프 (AI 음성)
#   with-timestamps 엔드포인트는 audio_base64 + alignment를 함께 반환.
#   latency_optimization은 절대 쓰지 않는다 (텍스트 정규화 비활성화 → 한국어 숫자 깨짐).
# ---------------------------------------------------------------------------
def tts_with_timestamps(
    text: str,
    voice_id: str,
    *,
    model_id: str = "eleven_multilingual_v2",   # 한국어 안정성 최강 (v3보다 발음/일관성 우위)
    api_key: Optional[str] = None,
    stability: float = 0.40,        # 35~45%: 로봇틱 방지 + 일관성 (본문 내레이션 권장)
    similarity_boost: float = 0.75,
    style: float = 0.0,
) -> tuple[bytes, list[WordTiming]]:
    import base64
    key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise AlignmentError("ELEVENLABS_API_KEY 미설정.")

    r = requests.post(
        f"{ELEVEN_BASE}/text-to-speech/{voice_id}/with-timestamps",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "use_speaker_boost": True,
            },
            # latency_optimization 절대 넣지 않음
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise AlignmentError(f"TTS 실패 {r.status_code}: {r.text[:300]}")

    payload = r.json()
    audio = base64.b64decode(payload["audio_base64"])
    align = payload.get("alignment") or {}
    chars = align.get("characters") or []
    starts = align.get("character_start_times_seconds") or []
    ends = align.get("character_end_times_seconds") or []

    # 문자 타임스탬프 → 단어 타임스탬프로 병합 (공백 기준)
    words = _chars_to_words(chars, starts, ends)
    return audio, words


def _chars_to_words(chars, starts, ends) -> list[WordTiming]:
    words: list[WordTiming] = []
    cur, w_start = "", None
    for i, ch in enumerate(chars):
        if ch.strip() == "":
            if cur:
                words.append(WordTiming(cur, w_start, ends[i - 1]))
                cur, w_start = "", None
        else:
            if w_start is None:
                w_start = starts[i]
            cur += ch
    if cur and w_start is not None:
        words.append(WordTiming(cur, w_start, ends[-1]))
    return words


# ---------------------------------------------------------------------------
# 단어 타임스탬프 → 자막 큐 (읽기 좋은 줄바꿈)
#   경제사냥꾼 스타일: 한 줄에 한 호흡. 너무 길면 분할.
# ---------------------------------------------------------------------------
def words_to_cues(
    words: list[WordTiming],
    *,
    max_chars: int = 20,          # 한 자막 최대 글자수 (한글 가독성)
    max_duration: float = 4.0,    # 한 자막 최대 노출 시간
    gap_split: float = 0.5,       # 이 이상 쉬면 무조건 자막 분할 (발화 경계)
) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    if not words:
        return cues
    buf: list[WordTiming] = []
    idx = 1

    def flush():
        nonlocal idx, buf
        if not buf:
            return
        text = " ".join(w.text for w in buf).strip()
        cues.append(SubtitleCue(idx, buf[0].start, buf[-1].end, text))
        idx += 1
        buf = []

    for i, w in enumerate(words):
        if buf:
            gap = w.start - buf[-1].end
            cur_text = " ".join(x.text for x in buf)
            cur_dur = buf[-1].end - buf[0].start
            if gap >= gap_split or len(cur_text) >= max_chars or cur_dur >= max_duration:
                flush()
        buf.append(w)
    flush()
    return cues


def cues_to_srt(cues: list[SubtitleCue]) -> str:
    def ts(t: float) -> str:
        h = int(t // 3600); m = int((t % 3600) // 60)
        s = int(t % 60); ms = int(round((t - int(t)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    lines = []
    for c in cues:
        lines += [str(c.index), f"{ts(c.start)} --> {ts(c.end)}", c.text, ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 한국어 TTS 입력 전처리 — 숫자를 한글 낭독형으로.
#   ⚠️ 자막에는 숫자 그대로, 오디오에만 한글 확장. (userMemories 규칙)
#   ⚠️ % → "퍼센트"만, "포인트" 금지. 소수점은 문장 경계로 오인 금지.
# ---------------------------------------------------------------------------
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")

def normalize_korean_for_tts(text: str) -> str:
    """오디오 생성 '입력'용으로만 쓴다. 자막 텍스트에는 원본을 유지."""
    # 예시 규칙만. 실제 숫자→한글 확장은 기존 모듈(numeral→Korean word) 사용.
    text = _PERCENT.sub(lambda m: f"{m.group(1)}퍼센트", text)  # 포인트 금지
    return text

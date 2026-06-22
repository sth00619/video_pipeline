"""
Phase 1 핵심 워커 — 파생 쇼츠 생성
1. faster-whisper 로 단어 단위 타임스탬프 추출
2. LLM으로 하이라이트 텍스트 선정
3. rapidfuzz로 텍스트 → 타임스탬프 역매핑
4. FFmpeg으로 9:16 클립 생성
"""
import json
import os
import tempfile
import logging
from dataclasses import dataclass
from rapidfuzz import fuzz

from app.providers.factory import get_transcript_provider, get_llm_provider

logger = logging.getLogger(__name__)


@dataclass
class ShortClip:
    index: int
    text: str
    start: float
    end: float
    output_path: str


# "highlight"라는 단어를 시스템 프롬프트에 명시해서 Mock LLM이 JSON 응답을 반환하게 함
HIGHLIGHT_SYSTEM_PROMPT = """highlight extraction task.
당신은 유튜브 쇼츠 편집 전문가입니다.
주어진 영상 트랜스크립트에서 독립적으로 이해 가능하고 흥미로운 구간 텍스트를 골라주세요.
반드시 JSON 배열로만 응답하세요. 다른 설명 없이:
[{"text": "실제 트랜스크립트 텍스트", "reason": "선정 이유"}]
"""


class ShortsWorker:

    def __init__(self):
        self.transcript_provider = get_transcript_provider()
        self.llm_provider = get_llm_provider()

    def process(self, video_path: str, shorts_count: int = 3,
                output_dir: str = None) -> list[ShortClip]:
        if output_dir is None:
            output_dir = tempfile.mkdtemp()

        logger.info(f"트랜스크립트 추출 시작: {video_path}")
        segments = self.transcript_provider.transcribe(video_path)

        if not segments:
            logger.warning("트랜스크립트가 비어 있습니다.")
            return []

        full_text = " ".join(s.text for s in segments)
        all_words = []
        for seg in segments:
            all_words.extend(seg.words)

        logger.info(f"LLM 하이라이트 선정 중 (요청: {shorts_count}개)")
        user_prompt = (
            f"highlight: 다음 트랜스크립트에서 {shorts_count}개의 하이라이트 구간을 선정해주세요:\n\n"
            f"{full_text}"
        )
        raw = self.llm_provider.generate(HIGHLIGHT_SYSTEM_PROMPT, user_prompt)

        try:
            highlights = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"LLM 응답 파싱 실패: {raw[:200]}")
            # Mock 모드 fallback: 트랜스크립트를 N등분해서 직접 선정
            highlights = self._fallback_highlights(segments, shorts_count)

        clips = []
        for i, h in enumerate(highlights[:shorts_count]):
            clip = self._text_to_clip(h["text"], all_words, i, output_dir, video_path)
            if clip:
                clips.append(clip)

        return clips

    def _fallback_highlights(self, segments, count: int) -> list[dict]:
        """LLM 파싱 실패 시 트랜스크립트를 균등 분할하여 하이라이트 선정"""
        if not segments:
            return []
        step = max(1, len(segments) // count)
        highlights = []
        for i in range(count):
            idx = i * step
            if idx < len(segments):
                highlights.append({
                    "text": segments[idx].text,
                    "reason": f"fallback: segment {idx}"
                })
        return highlights

    def _text_to_clip(self, highlight_text: str, all_words: list,
                      index: int, output_dir: str, video_path: str) -> ShortClip | None:
        """핵심 로직: 텍스트 → rapidfuzz 매칭 → 타임스탬프 → FFmpeg 클립"""
        if not all_words:
            return None

        word_texts = [w["word"].strip() for w in all_words]
        window_size = max(3, len(highlight_text.split()))
        best_score = 0
        best_start_idx = 0

        for i in range(len(word_texts) - window_size + 1):
            window = " ".join(word_texts[i:i + window_size])
            score = fuzz.partial_ratio(highlight_text, window)
            if score > best_score:
                best_score = score
                best_start_idx = i

        if best_score < 30:
            logger.warning(f"하이라이트 매칭 실패 (score={best_score}): {highlight_text[:50]}")
            return None

        end_idx = min(best_start_idx + window_size, len(all_words) - 1)
        start_time = all_words[best_start_idx]["start"]
        end_time = all_words[end_idx]["end"]

        # 앞뒤 0.5초 여유
        start_time = max(0, start_time - 0.5)
        end_time = end_time + 0.5

        # 최소 5초 보장
        if end_time - start_time < 5:
            end_time = start_time + 5

        output_path = os.path.join(output_dir, f"short_{index + 1}.mp4")
        success = self._cut_and_reframe(video_path, start_time, end_time, output_path)

        if not success:
            return None

        logger.info(f"쇼츠 {index+1} 생성 완료: {start_time:.1f}s ~ {end_time:.1f}s")
        return ShortClip(
            index=index + 1,
            text=highlight_text,
            start=start_time,
            end=end_time,
            output_path=output_path
        )

    def _cut_and_reframe(self, video_path: str, start: float,
                         end: float, output_path: str) -> bool:
        """FFmpeg: 16:9 원본 → 9:16 (1080x1920) 센터 크롭"""
        duration = end - start
        cmd = (
            f'ffmpeg -ss {start} -i "{video_path}" -t {duration} '
            f'-vf "crop=ih*9/16:ih,scale=1080:1920" '
            f'-c:v libx264 -c:a aac -y "{output_path}" -loglevel error'
        )
        ret = os.system(cmd)
        if ret != 0:
            logger.error(f"FFmpeg 실패 (ret={ret})")
            return False
        return True

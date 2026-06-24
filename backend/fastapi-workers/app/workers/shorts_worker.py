"""
Phase 2-A — 쇼츠 워커 (analyze + cut 분리 버전)

analyze(): 영상 → Whisper → LLM 제안 구간 반환 (자르지 않음)
cut():     확정된 구간 리스트 → FFmpeg으로 9:16 자르기
"""
import json
import os
import logging
from rapidfuzz import fuzz

from app.providers.factory import get_transcript_provider, get_llm_provider

logger = logging.getLogger(__name__)


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

    def analyze(self, video_path: str, shorts_count: int = 3) -> dict:
        """
        Stage 1: 영상 → 트랜스크립트 + 제안 구간 (자르지 않음)
        반환:
          {
            "transcript": str,
            "words": [{"word", "start", "end"}, ...],
            "suggested_segments": [{"index", "text", "start", "end", "reason"}, ...]
          }
        """
        logger.info(f"트랜스크립트 추출 시작: {video_path}")
        segments = self.transcript_provider.transcribe(video_path)
        if not segments:
            return {"transcript": "", "words": [], "suggested_segments": []}

        full_text = " ".join(s.text for s in segments)
        all_words = []
        for seg in segments:
            all_words.extend(seg.words)

        # LLM 하이라이트 선정
        logger.info(f"LLM 하이라이트 선정 중 (요청: {shorts_count}개)")
        user_prompt = (
            f"highlight: 다음 트랜스크립트에서 {shorts_count}개의 하이라이트 구간을 선정해주세요:\n\n"
            f"{full_text}"
        )
        raw = self.llm_provider.generate(HIGHLIGHT_SYSTEM_PROMPT, user_prompt)
        try:
            highlights = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"LLM 응답 파싱 실패, fallback 사용")
            highlights = self._fallback_highlights(segments, shorts_count)

        # 각 하이라이트 텍스트 → 타임스탬프 매핑
        suggested = []
        for i, h in enumerate(highlights[:shorts_count]):
            mapped = self._map_text_to_timestamps(h["text"], all_words)
            if mapped is None:
                continue
            start, end = mapped
            suggested.append({
                "index": i + 1,
                "text": h["text"],
                "start": round(start, 2),
                "end": round(end, 2),
                "reason": h.get("reason", "")
            })

        return {
            "transcript": full_text,
            "words": all_words,
            "suggested_segments": suggested,
        }

    def cut(self, source_path: str, segments: list, output_dir: str) -> list:
        """
        Stage 2: 확정된 구간 리스트 → 9:16 FFmpeg 자르기.
        반환: [{"index", "text", "start", "end", "output_path"}, ...]
        """
        clips = []
        for seg in segments:
            idx = seg["index"]
            start = float(seg["start"])
            end = float(seg["end"])
            text = seg.get("text", "")

            output_path = os.path.join(output_dir, f"short_{idx}.mp4")
            success = self._cut_and_reframe(source_path, start, end, output_path)
            if not success:
                logger.error(f"쇼츠 {idx} 자르기 실패")
                continue

            clips.append({
                "index": idx,
                "text": text,
                "start": start,
                "end": end,
                "output_path": output_path,
            })
            logger.info(f"쇼츠 {idx} 생성 완료: {start:.1f}s ~ {end:.1f}s")

        return clips

    # ============================
    # 내부 유틸
    # ============================
    def _fallback_highlights(self, segments, count: int) -> list:
        if not segments:
            return []
        step = max(1, len(segments) // count)
        return [
            {"text": segments[i * step].text, "reason": f"fallback: segment {i * step}"}
            for i in range(count) if i * step < len(segments)
        ]

    def _map_text_to_timestamps(self, highlight_text: str, all_words: list):
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
            return None

        end_idx = min(best_start_idx + window_size, len(all_words) - 1)
        start_time = all_words[best_start_idx]["start"]
        end_time = all_words[end_idx]["end"]
        start_time = max(0, start_time - 0.5)
        end_time = end_time + 0.5
        if end_time - start_time < 5:
            end_time = start_time + 5

        return start_time, end_time

    def _cut_and_reframe(self, video_path: str, start: float, end: float, output_path: str) -> bool:
        duration = end - start
        cmd = (
            f'ffmpeg -ss {start} -i "{video_path}" -t {duration} '
            f'-vf "crop=ih*9/16:ih,scale=1080:1920" '
            f'-c:v libx264 -c:a aac -y "{output_path}" -loglevel error'
        )
        ret = os.system(cmd)
        return ret == 0

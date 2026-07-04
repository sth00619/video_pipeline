"""
쇼츠 추출 워커 v5 — 주식 콘텐츠 letterbox 변환

핵심 변경: crop(잘림) → letterbox(전체 보존)
  원본 16:9 영상을 1080x1920에 letterbox로 배치
  위아래 네이비 패딩(#0d1b2a) — 주식 영상 배경과 동일
  차트, 자막, 수치 잘림 없음
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CLIP = 60.0
MIN_CLIP = 10.0

STOCK_KW_HIGH = [
    "지금 당장", "핵심은", "결론은", "정리하면",
    "매수 타이밍", "매도 타이밍", "손절", "목표가", "시나리오",
    "상승 가능성", "하락 가능성", "외국인 매수", "기관 매수",
    "돌파", "지지선", "저항선",
]
STOCK_KW_MED = [
    "코스피", "코스닥", "나스닥", "S&P", "FOMC", "금리", "환율",
    "반등", "조정", "박스권", "RSI", "MACD",
]


class ShortsWorker:

    def analyze(self, video_path: str, shorts_count: int = 3) -> dict:
        total_duration = self._get_duration(video_path)
        transcript, words, suggested = "", [], []
        try:
            from app.providers.factory import get_transcript_provider
            provider = get_transcript_provider()
            try:
                segments = provider.transcribe(video_path, language="ko")
            except Exception as e:
                logger.warning(f"Whisper 실패: {e}")
                segments = []

            if segments:
                transcript = " ".join(s.text for s in segments)
                for seg in segments:
                    if seg.words:
                        for w in seg.words:
                            words.append({"word": w.word, "start": w.start, "end": w.end})
                if not total_duration and segments:
                    total_duration = segments[-1].end
                suggested = self._extract(segments, shorts_count, total_duration)
            else:
                suggested = self._equal_split(total_duration or 300, shorts_count)
        except Exception as e:
            logger.error(f"analyze 실패: {e}")
            suggested = self._equal_split(total_duration or 300, shorts_count)

        return {
            "transcript": transcript,
            "words": words,
            "suggested_segments": suggested,
            "total_duration": round(total_duration, 2) if total_duration else 0,
        }

    def _extract(self, segments, count, total_duration):
        if not total_duration or total_duration < 10:
            return self._equal_split(total_duration or 60, count)
        for seg in segments:
            seg._score = sum(3 for kw in STOCK_KW_HIGH if kw in seg.text)
            seg._score += sum(1 for kw in STOCK_KW_MED if kw in seg.text)
        window, step = DEFAULT_CLIP, max(15.0, total_duration / 20)
        candidates, t = [], 0.0
        while t + window <= total_duration:
            score = sum(getattr(s, '_score', 0) for s in segments if s.start >= t and s.end <= t + window)
            candidates.append((score, t, t + window))
            t += step
        if not candidates:
            return self._equal_split(total_duration, count)
        candidates.sort(key=lambda x: x[0], reverse=True)
        selected = []
        for sc, st, en in candidates:
            if len(selected) >= count: break
            if not any(min(en, e) - max(st, s) > window * 0.4 for _, s, e in selected):
                selected.append((sc, st, en))
        while len(selected) < count:
            last = max((e for _, _, e in selected), default=0)
            ns = min(last + 5, total_duration - window)
            ne = min(ns + window, total_duration)
            if ne - ns < MIN_CLIP: break
            selected.append((0, ns, ne))
        selected.sort(key=lambda x: x[1])
        labels = ["핵심 분석", "시나리오 분석", "실행 가이드", "결론 요약", "데이터 정리"]
        return [
            {
                "index": i + 1,
                "text": " ".join(s.text for s in segments if s.start >= st and s.end <= en)[:100] or f"구간 {i+1}",
                "label": labels[i % len(labels)],
                "start": round(st, 2), "end": round(en, 2),
                "duration": round(en - st, 2), "score": round(sc, 1),
            }
            for i, (sc, st, en) in enumerate(selected[:count])
        ]

    def _equal_split(self, total_duration: float, count: int) -> list:
        labels = ["핵심 분석", "시나리오 분석", "실행 가이드", "결론 요약", "데이터 정리"]
        clip = min(DEFAULT_CLIP, total_duration / max(count, 1))
        step = total_duration / (count + 1)
        return [
            {
                "index": i + 1, "text": f"구간 {i+1}", "label": labels[i % len(labels)],
                "start": round(step * (i + 0.5), 2),
                "end": round(min(step * (i + 0.5) + clip, total_duration), 2),
                "duration": round(clip, 2), "score": 0,
            }
            for i in range(count)
        ]

    def cut(self, source_path: str, segments: list, output_dir: str) -> list:
        """
        letterbox 방식으로 9:16 변환
        
        변환 방식:
          scale=1080:1920:force_original_aspect_ratio=decrease
            → 원본 비율 유지하며 1080x1920 안에 맞게 축소
          pad=1080:1920:(ow-iw)/2:(oh-ih)/2:0x0d1b2a
            → 16:9 영상 → 위아래 네이비 패딩으로 채움
            → 예: 1080x607 영상 → 위 656px 패딩 + 영상 + 아래 657px 패딩
        
        결과: 전체 내용 보존, 잘림 없음, 주식 차트/자막/수치 모두 표시
        """
        clips = []
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        for seg in segments:
            idx = seg.get("index", len(clips) + 1)
            start = float(seg.get("start", 0))
            end = float(seg.get("end", start + 60))
            duration = end - start

            if duration < MIN_CLIP:
                logger.warning(f"구간 {idx}: {duration:.1f}초 미만, 건너뜀")
                continue

            output_path = str(Path(output_dir) / f"short_{idx:03d}.mp4")

            # letterbox: 네이비 배경 (#0d1b2a — 주식 영상 배경색과 동일)
            vf = (
                "scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:0x0d1b2a,"
                "setsar=1"
            )

            cmd = (
                f'ffmpeg -i "{source_path}" '
                f'-ss {start:.3f} -t {duration:.3f} '
                f'-vf "{vf}" '
                f'-c:v libx264 -preset fast -crf 23 '
                f'-c:a aac -b:a 128k '
                f'-y "{output_path}" -loglevel error'
            )
            ret = os.system(cmd)

            if ret != 0:
                # 폴백: 검정 배경
                logger.warning(f"구간 {idx}: 네이비 패딩 실패, 검정으로 재시도")
                cmd_fb = (
                    f'ffmpeg -i "{source_path}" '
                    f'-ss {start:.3f} -t {duration:.3f} '
                    f'-vf "scale=1080:1920:force_original_aspect_ratio=decrease,'
                    f'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1" '
                    f'-c:v libx264 -preset fast -c:a aac '
                    f'-y "{output_path}" -loglevel error'
                )
                os.system(cmd_fb)

            if os.path.exists(output_path):
                clips.append({
                    "index": idx,
                    "text": seg.get("text", ""),
                    "label": seg.get("label", f"쇼츠 {idx}"),
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "duration": round(duration, 2),
                    "output_path": output_path,
                    "file_size_mb": round(os.path.getsize(output_path) / 1024 / 1024, 1),
                })
                logger.info(f"쇼츠 {idx} 생성 완료: letterbox {duration:.0f}s")
            else:
                logger.error(f"쇼츠 {idx} 생성 실패")

        return clips

    @staticmethod
    def _get_duration(path: str) -> float:
        try:
            r = os.popen(
                f'ffprobe -v error -show_entries format=duration '
                f'-of default=noprint_wrappers=1:nokey=1 "{path}"'
            ).read().strip()
            return float(r)
        except:
            return 0.0

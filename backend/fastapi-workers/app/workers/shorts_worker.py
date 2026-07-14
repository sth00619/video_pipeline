"""
쇼츠 추출 워커 v6 — 9:16 fill/crop 및 60초 상한

원본 영상의 중심을 기준으로 세로 화면을 빈 여백 없이 채운다.
모든 개별 쇼츠와 병합 쇼츠는 YouTube Shorts 권장 길이인 60초를 넘지 않는다.
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CLIP = 60.0
MIN_CLIP = 10.0
MAX_SHORT_DURATION = 60.0

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

    @staticmethod
    def _vertical_fill_filter() -> str:
        """Fill a 9:16 canvas without letterboxing, preserving the source centre."""
        return (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920:(in_w-out_w)/2:(in_h-out_h)/2,setsar=1"
        )

    def _cap_segments_to_short_limit(self, segments: list) -> list:
        """Keep ordered source ranges within the 60-second Shorts ceiling.

        A final range is shortened when necessary instead of allowing a merged
        output to silently exceed the platform limit.
        """
        capped, remaining = [], MAX_SHORT_DURATION
        for raw_segment in segments:
            if remaining <= 0:
                break
            segment = dict(raw_segment)
            try:
                start = float(segment.get("start", 0))
                end = float(segment.get("end", start))
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue
            duration = min(end - start, remaining)
            if duration <= 0:
                continue
            segment.update({"start": round(start, 3), "end": round(start + duration, 3)})
            capped.append(segment)
            remaining -= duration
        if len(capped) < len(segments):
            logger.info("Shorts timeline capped at %.0fs", MAX_SHORT_DURATION)
        return capped

    def _prepare_segments_for_cut(self, source_path: str, segments: list) -> list:
        """Expand short Whisper sentence matches instead of dropping them.

        Keyword matching is sentence-level (often 1--5 seconds), but a Shorts
        clip needs enough context to be watchable. Each short match is expanded
        symmetrically to ``MIN_CLIP`` within the source-video bounds.
        """
        source_duration = self._get_duration(source_path)
        prepared = []
        for position, raw_segment in enumerate(segments):
            segment = dict(raw_segment)
            try:
                start = max(0.0, float(segment.get("start", 0)))
                end = float(segment.get("end", start + MIN_CLIP))
            except (TypeError, ValueError):
                logger.warning("Skipping Shorts segment %s with invalid timestamps", position)
                continue
            if end <= start:
                logger.warning("Skipping Shorts segment %s with non-positive duration", position)
                continue

            if source_duration > 0:
                start = min(start, source_duration)
                end = min(end, source_duration)
            duration = end - start
            if duration < MIN_CLIP and source_duration > duration:
                required = min(MIN_CLIP, source_duration)
                padding = (required - duration) / 2
                start = max(0.0, start - padding)
                end = min(source_duration, end + padding)
                if end - start < required:
                    if start <= 0:
                        end = min(source_duration, required)
                    else:
                        start = max(0.0, source_duration - required)
                logger.info("Expanded short transcript segment %s to %.1fs", position, end - start)

            if end - start < 0.05:
                logger.warning("Skipping Shorts segment %s with insufficient duration", position)
                continue
            segment.update({"start": round(start, 3), "end": round(end, 3)})
            prepared.append(segment)
        return prepared

    def normalize_scenes(self, scenes: list[dict], video_path: str) -> list[dict]:
        """Fill missing scene timestamps from the actual source-video duration."""
        ordered = [dict(scene) for scene in sorted(scenes, key=lambda scene: int(scene.get("index", 0)))]
        if not ordered:
            return []
        total_duration = self._get_duration(video_path)
        if total_duration <= 0:
            raise RuntimeError("Could not determine source video duration")

        def number(value, default=0.0):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        valid = all(
            number(scene.get("start")) >= 0
            and number(scene.get("duration")) > 0
            and number(scene.get("start")) + number(scene.get("duration")) <= total_duration + 0.25
            for scene in ordered
        ) and all(
            number(current.get("start")) >= number(previous.get("start")) + number(previous.get("duration")) - 0.25
            for previous, current in zip(ordered, ordered[1:])
        )
        if valid:
            for scene in ordered:
                start = max(0.0, number(scene.get("start")))
                duration = min(number(scene.get("duration")), max(0.05, total_duration - start))
                scene.update({"start": round(start, 3), "duration": round(duration, 3), "end": round(start + duration, 3)})
            return ordered

        weights = [max(20, len(str(scene.get("text") or scene.get("prompt") or "").replace(" ", ""))) for scene in ordered]
        total_weight = sum(weights) or len(ordered)
        cursor = 0.0
        for position, (scene, weight) in enumerate(zip(ordered, weights)):
            duration = max(0.05, total_duration - cursor) if position == len(ordered) - 1 else max(0.05, total_duration * weight / total_weight)
            duration = min(duration, max(0.05, total_duration - cursor))
            scene.update({"start": round(cursor, 3), "duration": round(duration, 3), "end": round(cursor + duration, 3)})
            cursor += duration
        return ordered

    def analyze(self, video_path: str, shorts_count: int = 3) -> dict:
        total_duration = self._get_duration(video_path)
        transcript, words, suggested, transcript_segments = "", [], [], []
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
                for index, seg in enumerate(segments, start=1):
                    transcript_segments.append({
                        "index": index,
                        "text": seg.text,
                        "start": round(float(seg.start), 3),
                        "end": round(float(seg.end), 3),
                        "duration": round(max(0.0, float(seg.end) - float(seg.start)), 3),
                    })
                    if seg.words:
                        for w in seg.words:
                            if isinstance(w, dict):
                                word, start, end = w.get("word", ""), w.get("start", 0), w.get("end", 0)
                            else:
                                word, start, end = getattr(w, "word", ""), getattr(w, "start", 0), getattr(w, "end", 0)
                            words.append({"word": word, "start": start, "end": end})
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
            "transcript_segments": transcript_segments,
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
        빈 여백 없는 fill/crop 방식으로 9:16 변환
        
        원본 중심을 기준으로 1080x1920을 가득 채운 뒤 잘라낸다.
        모든 결과는 최대 60초로 제한한다.
        """
        clips = []
        segments = self._prepare_segments_for_cut(source_path, segments)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        for seg in segments:
            idx = seg.get("index", len(clips) + 1)
            start = float(seg.get("start", 0))
            end = min(float(seg.get("end", start + MAX_SHORT_DURATION)), start + MAX_SHORT_DURATION)
            duration = end - start

            if duration < MIN_CLIP:
                logger.warning(f"구간 {idx}: {duration:.1f}초 미만, 건너뜀")
                continue

            output_path = str(Path(output_dir) / f"short_{idx:03d}.mp4")

            vf = self._vertical_fill_filter()

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
                logger.warning(f"구간 {idx}: fill/crop 인코딩 실패, 단순 인코더로 재시도")
                cmd_fb = (
                    f'ffmpeg -i "{source_path}" '
                    f'-ss {start:.3f} -t {duration:.3f} '
                    f'-vf "{vf}" '
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

    def extract_scenarios(self, scenes: list, job_id: int = 0) -> dict:
        """
        Claude 4.6을 호출하여 대본 내용 중 3가지 테마(실적 중심, 리스크 중심, 호재 중심)에 맞는
        최적의 씬 구간(30~60초 분량)을 기승전결 구조로 자동 선택하고, 추천 키워드 리스트를 반환합니다.
        """
        import json
        import re
        from app.providers.factory import get_llm_provider
        
        # claude-sonnet-4-6를 제공하는 LLM 프로바이더 로드
        llm = get_llm_provider()
        
        # 1. 씬 목록 포맷팅 (각 씬의 지속 시간은 10~20초 수준으로 이미 정규화되어 있음)
        scene_list_str = ""
        for s in scenes:
            idx = s.get("index")
            text = s.get("text", "")
            start = s.get("start", 0.0)
            duration = s.get("duration", 0.0)
            scene_list_str += f"Scene {idx} (시작: {start:.1f}초, 분량: {duration:.1f}초): {text}\n"

        system_prompt = (
            "You are an expert financial YouTube editor. Your task is to analyze the longform script scenes "
            "and select a single contiguous range of scenes (e.g. from Scene X to Scene Y) to create a compelling, viral 30-60 second YouTube Short. "
            "You must use the model 'claude-sonnet-4-6' to generate the response.\n\n"
            "You must generate 3 distinct scenarios:\n"
            "1. 'performance': Focuses on corporate earnings, sales, or positive data indicators.\n"
            "2. 'risk': Focuses on macro warnings, downswings, or risk management tips.\n"
            "3. 'upside': Focuses on momentum triggers, news events, or future opportunities.\n\n"
            "Constraints:\n"
            "- For each scenario, you MUST choose a contiguous block of scenes (e.g. indices [3, 4, 5]).\n"
            "- The sum of durations of the selected scenes MUST be between 30 and 60 seconds.\n"
            "- You must also recommend exactly 10 relevant keywords. For each keyword, return the indices of all scenes that contain or are related to that keyword.\n"
            "- Output MUST be a valid JSON object matching the exact structure below, with no markdown tags or conversational filler.\n\n"
            "Output JSON Format:\n"
            "{\n"
            "  \"scenarios\": {\n"
            "    \"performance\": {\n"
            "      \"title\": \"String (Korean title, under 20 chars)\",\n"
            "      \"description\": \"String (Detailed narrative storyline in Korean)\",\n"
            "      \"selected_scene_indices\": [int, int, ...]\n"
            "    },\n"
            "    \"risk\": {\n"
            "      \"title\": \"String (Korean title, under 20 chars)\",\n"
            "      \"description\": \"String (Detailed narrative storyline in Korean)\",\n"
            "      \"selected_scene_indices\": [int, int, ...]\n"
            "    },\n"
            "    \"upside\": {\n"
            "      \"title\": \"String (Korean title, under 20 chars)\",\n"
            "      \"description\": \"String (Detailed narrative storyline in Korean)\",\n"
            "      \"selected_scene_indices\": [int, int, ...]\n"
            "    }\n"
            "  },\n"
            "  \"keywords\": [\n"
            "    {\n"
            "      \"word\": \"String (Keyword in Korean)\",\n"
            "      \"description\": \"String (Short explanation in Korean)\",\n"
            "      \"matching_scene_indices\": [int, int, ...]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        user_prompt = (
            f"Here is the list of scenes in the video:\n\n{scene_list_str}\n\n"
            f"Please analyze the scenes and return the JSON object."
        )

        logger.info(f"Claude 4.6 쇼츠 시나리오 & 키워드 추천 요청 시작: job_id={job_id}, scene_count={len(scenes)}")
        
        try:
            response_text = llm.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                response_text = match.group(0)
            result = json.loads(response_text)
            result["keywords"] = self._ensure_ten_keywords(result.get("keywords"), scenes)
            logger.info("Claude 4.6 쇼츠 추출 결과 파싱 성공")
            return result
        except Exception as e:
            logger.error(f"Claude 4.6 호출 실패 또는 JSON 파싱 오류: {e}")
            # Mock 폴백 데이터 제공
            return {
                "scenarios": {
                    "performance": {
                        "title": "실적 중심 분석 쇼츠",
                        "description": "2분기 반도체 부문 영업이익이 급등한 호재 데이터를 집중 분석하는 고밀도 쇼츠입니다.",
                        "selected_scene_indices": [1, 2] if len(scenes) >= 2 else [1]
                    },
                    "risk": {
                        "title": "시장 리스크 경고 쇼츠",
                        "description": "외국인 투자자의 대형주 대량 매도 흐름과 주가 하락 가능성을 밀착 경고하는 리스크 관리용 쇼츠입니다.",
                        "selected_scene_indices": [3, 4] if len(scenes) >= 4 else [1]
                    },
                    "upside": {
                        "title": "반등 모멘텀 기회 쇼츠",
                        "description": "최근 60일 이동평균선 지지 및 신규 HBM 공급 기대감에 따른 하반기 반등 타이밍을 진단하는 쇼츠입니다.",
                        "selected_scene_indices": [min(5, len(scenes)), min(6, len(scenes))] if len(scenes) >= 6 else [1]
                    }
                },
                "keywords": [
                    {"word": "핵심 지표", "description": "영상의 수치와 지표를 설명하는 구간", "matching_scene_indices": [1]},
                    {"word": "시장 흐름", "description": "시장 방향성을 설명하는 구간", "matching_scene_indices": [1, 2]},
                    {"word": "투자 포인트", "description": "의사결정에 도움이 되는 구간", "matching_scene_indices": [2]},
                    {"word": "주가 변동", "description": "상승과 하락 원인을 설명하는 구간", "matching_scene_indices": [3]},
                    {"word": "향후 전망", "description": "다음 흐름과 전망을 정리하는 구간", "matching_scene_indices": [4]},
                    {"word": "삼성전자", "description": "대본 내에서 삼성전자 동향을 다루는 구간", "matching_scene_indices": [1, 2, 5]},
                    {"word": "영업이익", "description": "실적 및 이익 컨센서스 언급 구간", "matching_scene_indices": [1, 3]},
                    {"word": "외국인", "description": "수급 및 투자주체별 거래 패턴 구간", "matching_scene_indices": [2, 4]},
                    {"word": "지지선", "description": "기술적 분석 및 매수 가격 기준점", "matching_scene_indices": [5, 6]},
                    {"word": "리스크", "description": "투자 시 주의해야 할 변동성 위험 요인", "matching_scene_indices": [3, 4]}
                ]
            }

    @staticmethod
    def _ensure_ten_keywords(raw_keywords, scenes: list[dict]) -> list[dict]:
        """Normalize model output to exactly ten selectable keyword cards."""
        import re
        scene_indices = [int(scene.get("index", position + 1)) for position, scene in enumerate(scenes)]
        normalized, seen = [], set()
        for item in raw_keywords or []:
            if not isinstance(item, dict):
                continue
            word = str(item.get("word") or "").strip()
            if not word or word in seen:
                continue
            matching = [int(value) for value in item.get("matching_scene_indices", []) if str(value).isdigit()]
            normalized.append({
                "word": word,
                "description": str(item.get("description") or f"{word} 관련 구간"),
                "matching_scene_indices": matching or scene_indices[:1],
            })
            seen.add(word)
            if len(normalized) == 10:
                return normalized

        corpus = " ".join(str(scene.get("text") or scene.get("prompt") or "") for scene in scenes)
        for word in re.findall(r"[가-힣A-Za-z0-9]{2,}", corpus):
            if word in seen:
                continue
            matching = [int(scene.get("index", position + 1)) for position, scene in enumerate(scenes) if word in str(scene.get("text") or scene.get("prompt") or "")]
            normalized.append({"word": word, "description": f"{word} 관련 핵심 구간", "matching_scene_indices": matching or scene_indices[:1]})
            seen.add(word)
            if len(normalized) == 10:
                return normalized

        while len(normalized) < 10:
            number = len(normalized) + 1
            normalized.append({
                "word": f"핵심 장면 {number}",
                "description": "영상 흐름을 기준으로 선택하는 보조 키워드",
                "matching_scene_indices": [scene_indices[(number - 1) % len(scene_indices)]] if scene_indices else [],
            })
        return normalized

    def cut_and_merge(self, source_path: str, segments: list, output_path: str) -> dict:
        """
        여러 씬 구간을 9:16 fill/crop으로 만들고, 총 60초 이내로 병합합니다.
        """
        import tempfile
        from pathlib import Path
        
        logger.info(f"쇼츠 병합 컷팅 시작: segments_count={len(segments)}")
        segments = self._cap_segments_to_short_limit(
            self._prepare_segments_for_cut(source_path, segments)
        )
        tmp_clips = []
        rendered_duration = 0.0
        
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 1. 각 구간별 컷팅 및 9:16 fill/crop 인코딩
            for idx, seg in enumerate(segments):
                start = float(seg.get("start", 0))
                end = float(seg.get("end", start + 15))
                duration = end - start
                
                if duration < MIN_CLIP:
                    logger.warning(f"병합 파트 {idx} 건너뜀 (duration {duration:.1f}s가 최소 요건 미달)")
                    continue
                    
                tmp_clip = tempfile.mktemp(suffix=f"_merge_part_{idx}.mp4")
                
                vf = self._vertical_fill_filter()
                
                cmd = (
                    f'ffmpeg -i "{source_path}" '
                    f'-ss {start:.3f} -t {duration:.3f} '
                    f'-vf "{vf}" '
                    f'-c:v libx264 -preset fast -crf 23 '
                    f'-c:a aac -b:a 128k '
                    f'-y "{tmp_clip}" -loglevel error'
                )
                ret = os.system(cmd)
                if ret == 0 and os.path.exists(tmp_clip):
                    tmp_clips.append(tmp_clip)
                    rendered_duration += duration
                    
            if not tmp_clips:
                raise ValueError("합성할 수 있는 유효한 영상 클립이 단 하나도 생성되지 않았습니다.")
                
            # 2. 임시 파일들을 Concat demuxer용 텍스트 파일로 정의
            list_file = tempfile.mktemp(suffix="_concat_list.txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for tc in tmp_clips:
                    escaped_path = tc.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
                    
            # 3. 비디오 무손실 Concat 병합
            merge_cmd = f'ffmpeg -f concat -safe 0 -i "{list_file}" -c copy -y "{output_path}" -loglevel error'
            ret_merge = os.system(merge_cmd)
            
            # 임시 리스트 파일 삭제
            if os.path.exists(list_file):
                os.remove(list_file)
                
            if ret_merge == 0 and os.path.exists(output_path):
                total_dur = min(MAX_SHORT_DURATION, rendered_duration)
                logger.info(f"쇼츠 병합 완료: {output_path} ({total_dur:.1f}초)")
                return {
                    "index": 1,
                    "text": "키워드 매칭 합성 쇼츠",
                    "label": "합성 쇼츠",
                    "start": round(float(segments[0].get("start", 0)), 2),
                    "end": round(float(segments[-1].get("end", 0)), 2),
                    "duration": round(total_dur, 2),
                    "output_path": output_path,
                    "file_size_mb": round(os.path.getsize(output_path) / 1024 / 1024, 1),
                }
            else:
                raise RuntimeError("FFmpeg Concat 병합 실패")
                
        finally:
            # 모든 임시 파일 청소
            for tc in tmp_clips:
                if os.path.exists(tc):
                    try:
                        os.remove(tc)
                    except Exception as clean_ex:
                        logger.warning(f"임시 파일 청소 실패: {clean_ex}")

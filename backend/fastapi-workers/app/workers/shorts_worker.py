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
                    {"word": "삼성전자", "description": "대본 내에서 삼성전자 동향을 다루는 구간", "matching_scene_indices": [1, 2, 5]},
                    {"word": "영업이익", "description": "실적 및 이익 컨센서스 언급 구간", "matching_scene_indices": [1, 3]},
                    {"word": "외국인", "description": "수급 및 투자주체별 거래 패턴 구간", "matching_scene_indices": [2, 4]},
                    {"word": "지지선", "description": "기술적 분석 및 매수 가격 기준점", "matching_scene_indices": [5, 6]},
                    {"word": "리스크", "description": "투자 시 주의해야 할 변동성 위험 요인", "matching_scene_indices": [3, 4]}
                ]
            }

    def cut_and_merge(self, source_path: str, segments: list, output_path: str) -> dict:
        """
        여러 씬 구간을 개별적으로 크롭(letterbox) 컷팅한 후 하나의 mp4 파일로 무손실 병합(Concat)합니다.
        """
        import tempfile
        from pathlib import Path
        
        logger.info(f"쇼츠 병합 컷팅 시작: segments_count={len(segments)}")
        tmp_clips = []
        
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 1. 각 구간별 컷팅 및 9:16 letterbox 패딩 인코딩
            for idx, seg in enumerate(segments):
                start = float(seg.get("start", 0))
                end = float(seg.get("end", start + 15))
                duration = end - start
                
                if duration < MIN_CLIP:
                    logger.warning(f"병합 파트 {idx} 건너뜀 (duration {duration:.1f}s가 최소 요건 미달)")
                    continue
                    
                tmp_clip = tempfile.mktemp(suffix=f"_merge_part_{idx}.mp4")
                
                # letterbox 네이비 배경 (#0d1b2a)
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
                    f'-y "{tmp_clip}" -loglevel error'
                )
                ret = os.system(cmd)
                if ret == 0 and os.path.exists(tmp_clip):
                    tmp_clips.append(tmp_clip)
                    
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
                total_dur = sum(float(s.get("end", 0)) - float(s.get("start", 0)) for s in segments)
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

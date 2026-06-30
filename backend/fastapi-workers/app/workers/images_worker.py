"""
Phase 3-4 — 씬 이미지 + GIF 생성 워커

핵심:
  1. TTS chunks를 15~20초 단위로 그룹핑 → 1 씬 = 1 이미지
  2. 각 씬에 대한 이미지 프롬프트 생성 (텍스트 기반)
  3. Mock: FFmpeg으로 색상 + 텍스트 오버레이 PNG
  4. 섹션 전환 포인트에 GIF 클립 생성

산출물:
  - scenes[]: 씬별 이미지 파일 경로 + 시작/길이 + 프롬프트
  - gifs[]: GIF 파일 경로 + 삽입 위치 + 프롬프트
"""
import json
import os
import logging
from pathlib import Path

from app.providers.factory import get_image_provider

logger = logging.getLogger(__name__)

# 씬 그룹핑 기준 (초)
SCENE_TARGET_DURATION = 15.0
# GIF 삽입 간격 (초) — 대략 3~4분마다
GIF_INTERVAL_SECONDS = 200.0
# GIF 길이 (초)
GIF_DURATION = 3.0

# 씬 배경색 팔레트 (Mock 전용, 섹션별 다른 색)
SECTION_COLORS = {
    "intro":      "0x1a1a2e",
    "background": "0x16213e",
    "data":       "0x0f3460",
    "scenario":   "0x533483",
    "action":     "0xe94560",
    "conclusion": "0x1a1a2e",
    "default":    "0x2d2d2d",
}


class ImagesWorker:

    def __init__(self):
        self.image_provider = get_image_provider()

    def generate(self, tts_meta_json: str, script_meta_json: str,
                 job_id: int = 0) -> dict:

        # 1. TTS chunks 파싱
        tts_meta = json.loads(tts_meta_json)
        chunks = tts_meta.get("chunks", [])
        total_duration = tts_meta.get("total_duration", 0)

        # 2. 스크립트 섹션 정보 파싱 (있으면)
        script_meta = json.loads(script_meta_json)
        sections = script_meta.get("sections", [])

        if not chunks:
            logger.warning("TTS chunks가 비어있습니다. 이미지 생성 건너뜀.")
            return {"job_id": job_id, "scene_count": 0, "gif_count": 0,
                    "scenes": [], "gifs": []}

        logger.info(f"이미지 생성 시작: job_id={job_id}, chunks={len(chunks)}, "
                    f"total_duration={total_duration:.0f}s")

        # 출력 폴더
        job_dir = Path(f"/app/data/jobs/{job_id}/images")
        job_dir.mkdir(parents=True, exist_ok=True)
        gif_dir = Path(f"/app/data/jobs/{job_id}/gifs")
        gif_dir.mkdir(parents=True, exist_ok=True)

        # 3. 씬 그룹핑 (15~20초 단위)
        scenes = self._group_chunks_to_scenes(chunks)

        # 4. 각 씬에 섹션 라벨 부여
        self._assign_sections(scenes, sections, total_duration)

        # 5. 씬 이미지 생성
        scene_results = []
        for scene in scenes:
            img_path = str(job_dir / f"scene_{scene['index']:03d}.png")
            section = scene.get("section", "default")
            color = SECTION_COLORS.get(section, SECTION_COLORS["default"])
            prompt = self._build_prompt(scene)

            self._create_mock_image(img_path, color, scene["index"],
                                     scene["text_preview"], section)

            scene_results.append({
                "index": scene["index"],
                "image_path": img_path,
                "prompt": prompt,
                "start": scene["start"],
                "duration": scene["duration"],
                "section": section,
            })

        # 6. GIF 삽입 포인트 (일정 간격)
        gif_results = self._generate_gifs(total_duration, gif_dir)

        logger.info(f"이미지 생성 완료: 씬 {len(scene_results)}장, GIF {len(gif_results)}개")

        return {
            "job_id": job_id,
            "scene_count": len(scene_results),
            "gif_count": len(gif_results),
            "scenes": scene_results,
            "gifs": gif_results,
        }

    # ============================
    # 내부 로직
    # ============================
    def _group_chunks_to_scenes(self, chunks: list) -> list:
        """TTS chunks를 SCENE_TARGET_DURATION 단위로 그룹핑"""
        scenes = []
        current_start = 0.0
        current_duration = 0.0
        current_texts = []
        scene_index = 1

        for chunk in chunks:
            chunk_dur = chunk.get("duration", 3.0)
            current_duration += chunk_dur
            current_texts.append(chunk.get("text", ""))

            if current_duration >= SCENE_TARGET_DURATION:
                scenes.append({
                    "index": scene_index,
                    "start": round(current_start, 2),
                    "duration": round(current_duration, 2),
                    "text_preview": " ".join(current_texts)[:80],
                    "full_text": " ".join(current_texts),
                })
                scene_index += 1
                current_start += current_duration
                current_duration = 0.0
                current_texts = []

        # 남은 부분
        if current_texts:
            scenes.append({
                "index": scene_index,
                "start": round(current_start, 2),
                "duration": round(current_duration, 2),
                "text_preview": " ".join(current_texts)[:80],
                "full_text": " ".join(current_texts),
            })

        return scenes

    def _assign_sections(self, scenes: list, sections: list, total_duration: float):
        """각 씬에 섹션 라벨 부여 (시간 기준 매핑)"""
        if not sections:
            for s in scenes:
                s["section"] = "default"
            return

        # 섹션별 시간 범위 계산 (chars 비율 → 시간 비율)
        total_chars = sum(sec.get("expected_chars", 1) for sec in sections)
        section_ranges = []
        cursor = 0.0
        for sec in sections:
            ratio = sec.get("expected_chars", 1) / max(total_chars, 1)
            sec_duration = total_duration * ratio
            section_ranges.append({
                "name": sec.get("name", "default"),
                "start": cursor,
                "end": cursor + sec_duration,
            })
            cursor += sec_duration

        # 각 씬의 중심점이 어떤 섹션에 속하는지
        for scene in scenes:
            midpoint = scene["start"] + scene["duration"] / 2
            scene["section"] = "default"
            for sr in section_ranges:
                if sr["start"] <= midpoint < sr["end"]:
                    scene["section"] = sr["name"]
                    break

    def _build_prompt(self, scene: dict) -> str:
        """씬 텍스트에서 이미지 프롬프트 생성 (실제 Phase에서는 LLM 활용)"""
        section = scene.get("section", "default")
        text = scene.get("text_preview", "")
        section_label = {
            "intro": "도입부 영상 시작",
            "background": "시장 배경 분석",
            "data": "핵심 데이터 차트",
            "scenario": "시나리오 분석",
            "action": "투자 실행 가이드",
            "conclusion": "결론 및 요약",
        }.get(section, "인포그래픽")

        return f"[{section_label}] {text[:60]}"

    def _create_mock_image(self, output_path: str, color: str,
                            index: int, text: str, section: str):
        """Mock: FFmpeg으로 색상 배경 + 텍스트 오버레이 PNG"""
        label = f"Scene {index} ({section})"
        cmd = (
            f'ffmpeg -f lavfi -i "color=c={color}:s=1920x1080:d=1" '
            f'-frames:v 1 -y "{output_path}" -loglevel quiet'
        )
        os.system(cmd)

    def _generate_gifs(self, total_duration: float, gif_dir: Path) -> list:
        """일정 간격으로 Mock GIF 생성"""
        gifs = []
        gif_index = 1
        insert_at = GIF_INTERVAL_SECONDS

        while insert_at < total_duration - 10:
            gif_path = str(gif_dir / f"gif_{gif_index:03d}.gif")
            prompt = f"[강조 모션] 씬 전환 효과 {gif_index}"

            # Mock: 3초짜리 컬러 사이클 GIF
            cmd = (
                f'ffmpeg -f lavfi -i "color=c=0xe94560:s=640x360:d={GIF_DURATION}" '
                f'-vf "fade=in:0:15,fade=out:60:15" '
                f'-y "{gif_path}" -loglevel quiet'
            )
            os.system(cmd)

            gifs.append({
                "index": gif_index,
                "gif_path": gif_path,
                "prompt": prompt,
                "insert_at": round(insert_at, 2),
                "duration": GIF_DURATION,
            })
            gif_index += 1
            insert_at += GIF_INTERVAL_SECONDS

        return gifs

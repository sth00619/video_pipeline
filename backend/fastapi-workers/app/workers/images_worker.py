"""
Phase 3-4 v3 — 씬 이미지 생성 + 텍스트 오버레이

주식 플랫폼 특화:
  - 섹션명 (도입/시장배경/핵심데이터/시나리오/실행가이드/결론) 상단 표시
  - 씬 키워드 텍스트 중앙 표시
  - 씬 번호 / 총 씬 수 우하단 표시
  - 금융 테마 색상 팔레트
"""
import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCENE_TARGET_DURATION = 15.0
GIF_INTERVAL_SECONDS = 200.0
GIF_DURATION = 3.0

NANUM_FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
NANUM_BOLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"

# 섹션별 배경색 + 강조색 (배경: 어두운 금융 테마, 강조: 밝은 포인트)
SECTION_STYLES = {
    "intro":      {"bg": "1a1a2e", "accent": "e2b96f", "label": "도입"},
    "background": {"bg": "16213e", "accent": "7ec8e3", "label": "시장 배경"},
    "data":       {"bg": "0f3460", "accent": "00d4ff", "label": "핵심 데이터"},
    "scenario":   {"bg": "1b1464", "accent": "f5a623", "label": "시나리오 분석"},
    "action":     {"bg": "0d3b2e", "accent": "00ff88", "label": "실행 가이드"},
    "conclusion": {"bg": "1a1a2e", "accent": "e2b96f", "label": "결론"},
    "default":    {"bg": "0d1b2a", "accent": "ffffff", "label": ""},
}


class ImagesWorker:

    def generate(self, tts_meta_json: str, script_meta_json: str,
                 job_id: int = 0) -> dict:

        tts_meta = json.loads(tts_meta_json)
        chunks = tts_meta.get("chunks", [])
        total_duration = tts_meta.get("total_duration", 0)

        script_meta = json.loads(script_meta_json)
        sections = script_meta.get("sections", [])

        # 스크립트 키워드 추출 (meta에서)
        keyword = ""
        try:
            raw_script = script_meta.get("script", "")
            if raw_script:
                keyword = raw_script[:50].replace('"', '').replace("'", "")
        except:
            pass

        if not chunks:
            return {"job_id": job_id, "scene_count": 0, "gif_count": 0,
                    "scenes": [], "gifs": []}

        logger.info(f"이미지 생성 시작: job_id={job_id}, chunks={len(chunks)}, "
                    f"total_duration={total_duration:.0f}s")

        job_dir = Path(f"/app/data/jobs/{job_id}/images")
        job_dir.mkdir(parents=True, exist_ok=True)
        gif_dir = Path(f"/app/data/jobs/{job_id}/gifs")
        gif_dir.mkdir(parents=True, exist_ok=True)

        scenes = self._group_chunks_to_scenes(chunks)
        total_scenes = len(scenes)
        self._assign_sections(scenes, sections, total_duration)

        scene_results = []
        for scene in scenes:
            img_path = str(job_dir / f"scene_{scene['index']:03d}.png")
            section = scene.get("section", "default")
            style = SECTION_STYLES.get(section, SECTION_STYLES["default"])
            prompt = self._build_prompt(scene)
            text_preview = scene.get("text_preview", "")

            self._create_scene_image(
                img_path, style, scene["index"], total_scenes,
                text_preview
            )

            scene_results.append({
                "index": scene["index"],
                "image_path": img_path,
                "prompt": prompt,
                "start": scene["start"],
                "duration": scene["duration"],
                "section": section,
            })

        gif_results = self._generate_gifs(total_duration, gif_dir)

        logger.info(f"이미지 생성 완료: 씬 {len(scene_results)}장, GIF {len(gif_results)}개")

        return {
            "job_id": job_id,
            "scene_count": len(scene_results),
            "gif_count": len(gif_results),
            "scenes": scene_results,
            "gifs": gif_results,
        }

    def _create_scene_image(self, output_path: str, style: dict,
                             index: int, total: int, text: str):
        """FFmpeg drawtext로 주식 테마 씬 이미지 생성"""
        bg = style["bg"]
        accent = style["accent"]
        label = style.get("label", "")

        # 텍스트 안전 처리 (FFmpeg drawtext 특수문자 이스케이프)
        safe_text = self._escape_ffmpeg_text(text[:60] if text else "")
        safe_label = self._escape_ffmpeg_text(label)
        scene_num = f"{index}/{total}"

        font = NANUM_FONT if os.path.exists(NANUM_FONT) else ""
        font_opt = f"fontfile='{font}':" if font else ""

        # drawtext 필터 구성
        # 1) 상단 섹션 라벨 (강조색)
        # 2) 중앙 씬 텍스트 (흰색)
        # 3) 우하단 씬 번호 (회색)
        vf_parts = [
            # 배경 그라데이션 효과 (하단 어둡게)
            f"color=c={bg}:s=1920x1080",
        ]

        # drawtext 필터 체인
        drawtext_filters = []

        if safe_label:
            drawtext_filters.append(
                f"drawtext={font_opt}"
                f"text='{safe_label}':"
                f"fontcolor=0x{accent}:"
                f"fontsize=52:"
                f"x=80:y=80:"
                f"box=1:boxcolor=0x000000@0.4:boxborderw=12"
            )

        if safe_text:
            # 긴 텍스트는 줄바꿈 처리
            drawtext_filters.append(
                f"drawtext={font_opt}"
                f"text='{safe_text}':"
                f"fontcolor=0xffffff:"
                f"fontsize=44:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:"
                f"box=1:boxcolor=0x000000@0.5:boxborderw=16"
            )

        # 씬 번호 (우하단)
        drawtext_filters.append(
            f"drawtext={font_opt}"
            f"text='{scene_num}':"
            f"fontcolor=0xaaaaaa:"
            f"fontsize=32:"
            f"x=w-text_w-40:y=h-text_h-40"
        )

        # 상단 구분선 효과 (accent 색상)
        # drawbox로 상단 라인 추가
        drawbox = f"drawbox=x=0:y=0:w=iw:h=8:color=0x{accent}@0.9:t=fill"

        vf = (
            f"[0:v]{drawbox}"
            + "".join(f",{dt}" for dt in drawtext_filters)
        )

        cmd = (
            f'ffmpeg -f lavfi -i "color=c={bg}:s=1920x1080:d=1" '
            f'-frames:v 1 '
            f'-vf "{drawbox}'
            + "".join(f",{dt}" for dt in drawtext_filters)
            + f'" -y "{output_path}" -loglevel error'
        )

        ret = os.system(cmd)
        if ret != 0:
            # 폴백: 텍스트 없는 단색 배경
            logger.warning(f"drawtext 실패, 단색 폴백: scene_{index}")
            fallback = (
                f'ffmpeg -f lavfi -i "color=c={bg}:s=1920x1080:d=1" '
                f'-frames:v 1 -y "{output_path}" -loglevel error'
            )
            os.system(fallback)

    def _generate_gifs(self, total_duration: float, gif_dir: Path) -> list:
        gifs = []
        gif_index = 1
        insert_at = GIF_INTERVAL_SECONDS
        colors = ["e94560", "00ff88", "f5a623", "00d4ff", "e2b96f"]

        while insert_at < total_duration - 10:
            gif_path = str(gif_dir / f"gif_{gif_index:03d}.gif")
            color = colors[(gif_index - 1) % len(colors)]
            cmd = (
                f'ffmpeg -f lavfi '
                f'-i "color=c={color}:s=640x360:d={GIF_DURATION}" '
                f'-y "{gif_path}" -loglevel error'
            )
            os.system(cmd)
            gifs.append({
                "index": gif_index,
                "gif_path": gif_path,
                "prompt": f"[주가 강조 모션] 섹션 전환 {gif_index}",
                "insert_at": round(insert_at, 2),
                "duration": GIF_DURATION,
            })
            gif_index += 1
            insert_at += GIF_INTERVAL_SECONDS

        return gifs

    def _group_chunks_to_scenes(self, chunks: list) -> list:
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
        if not sections:
            for s in scenes:
                s["section"] = "default"
            return

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

        for scene in scenes:
            midpoint = scene["start"] + scene["duration"] / 2
            scene["section"] = "default"
            for sr in section_ranges:
                if sr["start"] <= midpoint < sr["end"]:
                    scene["section"] = sr["name"]
                    break

    def _build_prompt(self, scene: dict) -> str:
        section = scene.get("section", "default")
        text = scene.get("text_preview", "")
        style = SECTION_STYLES.get(section, SECTION_STYLES["default"])
        return f"[{style['label']}] {text[:60]}"

    @staticmethod
    def _escape_ffmpeg_text(text: str) -> str:
        """FFmpeg drawtext 특수문자 이스케이프"""
        return (text
                .replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace(":", "\\:")
                .replace("[", "\\[")
                .replace("]", "\\]")
                .replace(",", "\\,"))

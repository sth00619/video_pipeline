"""
Phase 3-4 v4 — 씬 이미지 (주식 시장 특화)

수정:
  - 씬 번호 제거
  - 중앙 텍스트 제거 (자막은 SRT에서 전담)
  - 섹션명만 좌상단에 표시 (도입/시장배경/핵심데이터/시나리오/실행가이드/결론)
  - 상단 강조선 유지
"""
import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCENE_TARGET_DURATION = 15.0
GIF_INTERVAL_SECONDS = 200.0
GIF_DURATION = 3.0

NANUM_FONT = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
NANUM_FONT_REGULAR = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

SECTION_STYLES = {
    "intro":      {"bg": "1a1a2e", "accent": "e2b96f", "label": "INTRO"},
    "background": {"bg": "16213e", "accent": "7ec8e3", "label": "시장 배경"},
    "data":       {"bg": "0f3460", "accent": "00d4ff", "label": "핵심 데이터"},
    "scenario":   {"bg": "1b1464", "accent": "f5a623", "label": "시나리오 분석"},
    "action":     {"bg": "0d3b2e", "accent": "00ff88", "label": "실행 가이드"},
    "conclusion": {"bg": "1a1a2e", "accent": "e2b96f", "label": "CONCLUSION"},
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
        self._assign_sections(scenes, sections, total_duration)

        scene_results = []
        for scene in scenes:
            img_path = str(job_dir / f"scene_{scene['index']:03d}.png")
            section = scene.get("section", "default")
            style = SECTION_STYLES.get(section, SECTION_STYLES["default"])
            prompt = self._build_prompt(scene)

            self._create_scene_image(img_path, style)

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

    def _create_scene_image(self, output_path: str, style: dict):
        """섹션명 + 상단 강조선만 표시. 중앙 텍스트/씬번호 없음."""
        bg = style["bg"]
        accent = style["accent"]
        label = style.get("label", "")

        font = NANUM_FONT if os.path.exists(NANUM_FONT) else (
            NANUM_FONT_REGULAR if os.path.exists(NANUM_FONT_REGULAR) else ""
        )
        font_opt = f"fontfile='{font}':" if font else ""

        safe_label = self._escape(label)

        filters = [f"drawbox=x=0:y=0:w=iw:h=6:color=0x{accent}@0.9:t=fill"]

        if safe_label:
            filters.append(
                f"drawtext={font_opt}"
                f"text='{safe_label}':"
                f"fontcolor=0x{accent}:"
                f"fontsize=36:"
                f"x=60:y=50"
            )

        vf = ",".join(filters)

        cmd = (
            f'ffmpeg -f lavfi -i "color=c={bg}:s=1920x1080:d=1" '
            f'-frames:v 1 -vf "{vf}" '
            f'-y "{output_path}" -loglevel error'
        )
        ret = os.system(cmd)
        if ret != 0:
            os.system(
                f'ffmpeg -f lavfi -i "color=c={bg}:s=1920x1080:d=1" '
                f'-frames:v 1 -y "{output_path}" -loglevel error'
            )

    def _generate_gifs(self, total_duration: float, gif_dir: Path) -> list:
        gifs = []
        gif_index = 1
        insert_at = GIF_INTERVAL_SECONDS
        colors = ["e94560", "00ff88", "f5a623", "00d4ff", "e2b96f"]

        while insert_at < total_duration - 10:
            gif_path = str(gif_dir / f"gif_{gif_index:03d}.gif")
            color = colors[(gif_index - 1) % len(colors)]
            os.system(
                f'ffmpeg -f lavfi -i "color=c={color}:s=640x360:d={GIF_DURATION}" '
                f'-y "{gif_path}" -loglevel error'
            )
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

    def _assign_sections(self, scenes, sections, total_duration):
        if not sections:
            for s in scenes:
                s["section"] = "default"
            return
        total_chars = sum(sec.get("expected_chars", 1) for sec in sections)
        ranges = []
        cursor = 0.0
        for sec in sections:
            ratio = sec.get("expected_chars", 1) / max(total_chars, 1)
            dur = total_duration * ratio
            ranges.append({"name": sec.get("name", "default"), "start": cursor, "end": cursor + dur})
            cursor += dur
        for scene in scenes:
            mid = scene["start"] + scene["duration"] / 2
            scene["section"] = "default"
            for r in ranges:
                if r["start"] <= mid < r["end"]:
                    scene["section"] = r["name"]
                    break

    def _build_prompt(self, scene):
        section = scene.get("section", "default")
        text = scene.get("text_preview", "")
        style = SECTION_STYLES.get(section, SECTION_STYLES["default"])
        return f"[{style['label']}] {text[:60]}"

    @staticmethod
    def _escape(text):
        return (text.replace("\\", "\\\\").replace("'", "\\'")
                .replace(":", "\\:").replace("[", "\\[")
                .replace("]", "\\]").replace(",", "\\,"))

"""
이미지 생성 워커 v3 — 배경 레이어 분리 + 캐릭터 합성 (Sprint 2)

핵심 변경:
  [S2-1] 배경 전용 생성 모드:
    - character_style_prompt="background_only"를 AI 프로바이더에 전달
    - 캐릭터 없는 순수 배경 이미지 생성
  [S2-3] 이중 레이어 합성 파이프라인:
    - channel_poses_dir 제공 시: 포즈별 투명 PNG + 배경 이미지를 FFmpeg overlay로 합성
    - 설정 단계에서 아직 포즈 라이브러리가 없으면 기존 캐릭터 일체형 모드로 폴백

비용: Fal.ai/Gemini API 콜 비용 + FFmpeg 로컬 코딩
"""
import os
import json
import hashlib
import logging
import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image, ImageFilter, ImageStat
from app.utils.process_manager import is_job_stopped
from app import runtime_config
from app.utils.quality_gate import enrich_scene_plan, assess_images, persist_quality_report
from app.utils.art_direction import direct_scenes, plan_image_quality_tiers, compile_editorial_prompt, assess_art_diversity
from app.utils.visual_qa import assess_visual_alignment
from app.utils import gemini_batch
from app.pipeline.scene_director import SceneDirector, SceneSpec
from app.providers.real.prompt_builder import build_prompt
from app.postprocess.text_overlay import add_headline
from app.utils.budget import plan_preflight, record_cost, write_preflight
from app.utils.intro_motion import infer_total_duration_seconds, select_intro_motion_scene_indices, scene_duration_seconds
from app.utils.gemini_pressure import gemini_pressure
from app.utils.image_job_lock import acquire_image_job_lock, release_image_job_lock
from app.utils.retry_policy import classify_image_error, error_signature

logger = logging.getLogger(__name__)


def _scene_metadata_contract(source_scenes: list[dict], output_scenes: list[dict]) -> dict:
    """Audit that every source metadata key survives image generation."""
    source_keys = sorted({key for scene in source_scenes for key in scene})
    output_keys = sorted({key for scene in output_scenes for key in scene})
    missing = sorted(set(source_keys) - set(output_keys))
    return {
        "passed": not missing,
        "source_keys": source_keys,
        "output_keys": output_keys,
        "missing_keys": missing,
        "market_chart_count": sum(bool(scene.get("market_chart")) for scene in output_scenes),
        "index_data_count": sum(bool(scene.get("index_data")) for scene in output_scenes),
        "motion_type_count": sum(bool(scene.get("motion_type")) for scene in output_scenes),
    }


def _article_evidence_path(scene: dict) -> str:
    capture = scene.get("article_capture")
    kind = str(scene.get("visual_kind") or scene.get("visual_type") or "")
    if kind not in {"article_evidence", "article_scene"} or not isinstance(capture, dict):
        return ""
    return str(capture.get("local_path") or scene.get("image_path") or "")


def _character_regions(scene: dict) -> list[dict[str, float]]:
    """Return conservative normalized keep-out zones for post-production UI.

    Integrated AI illustrations cannot yield an alpha mask, so their region is
    derived from the same art-direction placement contract used to compose the
    scene.  Explicit regions from an editor/compositor always take precedence.
    """
    explicit = scene.get("character_regions")
    if isinstance(explicit, list):
        return explicit
    direction = scene.get("art_direction") or {}
    if not direction.get("character_required", False):
        return []
    placement = str(direction.get("character_placement") or "right third").lower()
    if "left" in placement:
        return [{"x": .015, "y": .10, "width": .41, "height": .79, "source": "art_direction_estimate"}]
    return [{"x": .555, "y": .10, "width": .43, "height": .79, "source": "art_direction_estimate"}]


def _saliency_grid_and_negative_spaces(clean_plate_path: str | None) -> tuple[list[list[float]], list[dict[str, float]]]:
    """Build a deterministic local 8×8 saliency approximation from edge energy.

    It deliberately avoids sending a frame to another model.  The planner uses
    it only to reject busy speech-bubble positions; it is not face detection.
    """
    default_grid = [[0.0 for _ in range(8)] for _ in range(8)]
    if not clean_plate_path or not Path(clean_plate_path).is_file():
        return default_grid, []
    try:
        with Image.open(clean_plate_path) as loaded:
            image = loaded.convert("L").resize((320, 180), Image.Resampling.LANCZOS)
        edges = image.filter(ImageFilter.FIND_EDGES)
        values: list[list[float]] = []
        for row in range(8):
            result_row: list[float] = []
            for col in range(8):
                crop = edges.crop((col * 40, row * 22, (col + 1) * 40, (row + 1) * 22))
                result_row.append(float(ImageStat.Stat(crop).mean[0]))
            values.append(result_row)
        maximum = max(max(row) for row in values) or 1.0
        grid = [[round(value / maximum, 4) for value in row] for row in values]
        # Candidate locations correspond to common bubble slots. Low edge
        # energy means the copy will not collide with a visual focal object.
        candidates = [
            (0, 0, 3, 3), (5, 0, 3, 3), (0, 3, 3, 2), (5, 3, 3, 2),
        ]
        spaces: list[dict[str, float]] = []
        for x, y, width, height in candidates:
            cells = [grid[row][col] for row in range(y, y + height) for col in range(x, x + width)]
            if sum(cells) / len(cells) <= .42:
                spaces.append({"x": x / 8, "y": y / 8, "width": width / 8, "height": height / 8})
        return grid, spaces
    except OSError:
        return default_grid, []


def _asset_layout_metadata(scene: dict, clean_plate_path: str | None) -> dict:
    """Persist enough layout facts to make thumbnail selection deterministic.

    This intentionally does not pretend to have face detection for an AI
    illustration.  Unknown values remain null and the planner then avoids
    person/mascot-led candidates rather than guessing an empty space.
    """
    regions = _character_regions(scene)
    direction = scene.get("art_direction") or {}
    placement = str(direction.get("character_placement") or "").lower()
    subject_side = "left" if "left" in placement else ("right" if placement else None)
    saliency_grid, negative_spaces = _saliency_grid_and_negative_spaces(clean_plate_path)
    # A pose's opposite side is preferred if it is also locally quiet. If the
    # plate is visually busy, no bubble is emitted rather than guessing.
    preferred = {"x": .54, "y": .08, "width": .39, "height": .38} if subject_side == "left" else (
        {"x": .07, "y": .08, "width": .39, "height": .38} if subject_side == "right" else None
    )
    negative_space = preferred if preferred and negative_spaces else (negative_spaces[0] if negative_spaces else None)
    return {
        "face_bbox": None,
        "gaze_direction": None,
        "hand_regions": [],
        "saliency_map_version": "edge_energy_8x8_v1",
        "saliency_grid": saliency_grid,
        "negative_space": negative_space,
        "negative_spaces": negative_spaces,
        "subject_side": subject_side,
        "clean_plate_path": clean_plate_path,
        "duplicate_character_count": 0 if clean_plate_path else None,
        "character_regions": regions,
    }

DEFAULT_CHARACTER_SHEET = Path("/app/assets/character/goldie_sheet_v1.png")


class NonRetryableImageGenerationError(RuntimeError):
    """A deterministic image-generation fault that must not fan out into scene retries."""


class ImageProviderCreditRequiredError(RuntimeError):
    """The configured image provider cannot render until billing/quota is restored."""


def _is_non_retryable_image_error(exc: Exception) -> bool:
    return not classify_image_error(exc).retryable

import re

# 캐릭터 합성 위치 설정 (영상 충 대비 비율)
# 우하단 중앙에 위치
CHAR_OVERLAY_X_RATIO = 0.58   # 화면 왼쪽에서 58% 지점 (1920기준 약 1114px)
CHAR_OVERLAY_Y_RATIO = 0.08   # 상단 8% 지점
CHAR_HEIGHT_RATIO   = 0.72   # Keep the whole character inside a 16:9 frame.


def _extract_market_signal(text: str) -> dict:
    """
    씬 텍스트에서 실제 언급된 등락 방향과 지수/수치를 추출합니다.
    matplotlib 폴백 차트가 대본 내용과 모순되는 방향·숫자로 그려지는 것을
    막기 위한 용도입니다.
    """
    if not text:
        return {"direction": None, "value": None, "pct": None}

    direction = None
    if any(k in text for k in ["상승", "급등", "올랐", "돌파", "반등", "강세", "최고치", "호재"]):
        direction = "up"
    if any(k in text for k in ["하락", "급락", "내렸", "붕괴", "꺾", "약세", "부진", "악재"]):
        direction = "down"

    pct_match = re.search(r'([+-]?\d+(?:\.\d+)?)\s*(?:퍼센트|%)', text)
    pct = float(pct_match.group(1)) if pct_match else None
    if pct is not None and direction is None:
        if pct > 0:
            direction = "up"
        elif pct < 0:
            direction = "down"
    if pct is not None and direction == "down" and pct > 0:
        pct = -pct
    elif pct is not None and direction == "up" and pct < 0:
        pct = abs(pct)

    value_match = re.search(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)', text)
    value = value_match.group(1) if value_match else None

    return {"direction": direction, "value": value, "pct": pct}

# 주식 플랫폼 컬러 팔레트 (네이비 테마 통일)
COLOR_BG = "#0d1b2a"
COLOR_BG2 = "#16213e"
COLOR_ACCENT_GOLD = "#e2b96f"
COLOR_ACCENT_CYAN = "#00d4ff"
COLOR_ACCENT_GREEN = "#00c896"
COLOR_ACCENT_RED = "#e94560"
COLOR_TEXT = "#ffffff"
COLOR_GRID = "#2a3f5f"

FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"


class ImagesWorker:
    CANVAS_SIZE = (1920, 1080)

    def _normalize_canvas(self, img_path: str) -> None:
        """AI 이미지를 최종 캔버스(1920x1080)로 정규화. cover-crop 방식.

        반드시 모든 Pillow 오버레이보다 먼저 호출할 것.
        Flash 1K(≈1024px) 이미지도 여기서 Lanczos 업스케일되므로,
        이후에 그리는 차트/말풍선/숫자는 최종 해상도에서 렌더되어 선명함.
        """
        from PIL import Image
        sw, sh = self.CANVAS_SIZE
        with Image.open(img_path) as img:
            img = img.convert("RGB")
            if img.size == (sw, sh):
                return
            scale = max(sw / img.width, sh / img.height)   # cover (여백 없음)
            nw, nh = round(img.width * scale), round(img.height * scale)
            img = img.resize((nw, nh), Image.Resampling.LANCZOS)
            left, top = (nw - sw) // 2, (nh - sh) // 2
            
            # Save format matching the extension
            ext = os.path.splitext(img_path)[1].lower()
            save_format = "JPEG" if ext in {".jpg", ".jpeg"} else "PNG"
            img.crop((left, top, left + sw, top + sh)).save(img_path, save_format)

    def generate(self, scenes_meta: list = None, job_id: int = 0,
                 tts_meta_json: str = None, script_meta_json: str = None,
                 character_image_path: str = None, character_style_prompt: str = None,
                 character_poses_dir: str = None,
                 lora_model_id: str = None, lora_trigger_word: str = None,
                 lora_scale: float = 1.0) -> dict:
        """
        씬별 이미지를 생성합니다.

        [Sprint 3] LoRA 파라미터:
          - lora_model_id: safetensors CDN URL (Fal.ai flux-lora 사용)
          - lora_trigger_word: LoRA 활성화 트리거 단어
          - lora_scale: LoRA 적용 강도 (0.8~1.2, 기본 1.0)

        [S2-3] character_poses_dir 지정 시 이중 레이어 합성 모드:
          1) 배경 전용 이미지 생성 (character_style_prompt="background_only")
          2) 씬별 포즈 투명 PNG 로드
          3) FFmpeg overlay 필터로 합성
        """
        lock_token = acquire_image_job_lock(job_id)
        try:
            return self._generate(
                scenes_meta=scenes_meta, job_id=job_id, tts_meta_json=tts_meta_json,
                script_meta_json=script_meta_json, character_image_path=character_image_path,
                character_style_prompt=character_style_prompt, character_poses_dir=character_poses_dir,
                lora_model_id=lora_model_id, lora_trigger_word=lora_trigger_word, lora_scale=lora_scale,
            )
        finally:
            release_image_job_lock(job_id, lock_token)

    def _generate(self, scenes_meta: list = None, job_id: int = 0,
                  tts_meta_json: str = None, script_meta_json: str = None,
                  character_image_path: str = None, character_style_prompt: str = None,
                  character_poses_dir: str = None,
                  lora_model_id: str = None, lora_trigger_word: str = None,
                  lora_scale: float = 1.0) -> dict:
        market_snapshot = {}
        self.market_snapshot = {}
        self.evidence_audit = {}
        script_data: dict = {}
        # scenes_meta가 주어지지 않은 경우 script_meta_json에서 복원
        if script_meta_json:
            try:
                import json
                script_data = json.loads(script_meta_json)
                if isinstance(script_data, str):
                    script_data = json.loads(script_data)
                market_snapshot = script_data.get("market_snapshot") or {}
                self.market_snapshot = market_snapshot
                if not scenes_meta:
                    scenes_meta = script_data.get("sections") or script_data.get("scenes") or []
                if not scenes_meta and script_data.get("script"):
                    import re
                    raw_script = script_data.get("script", "").strip()
                    parts = [p.strip() for p in re.split(r'(?m)^##\s*|\n{2,}', raw_script) if p.strip()]
                    total_parts = len(parts)
                    section_keys = ["intro", "background", "data", "scenario", "action", "conclusion"]
                    for idx, part in enumerate(parts):
                        ratio = idx / max(total_parts - 1, 1) if total_parts > 1 else 0
                        section_type = section_keys[min(int(ratio * len(section_keys)), len(section_keys) - 1)]
                        scenes_meta.append({
                            "title": f"Scene {idx + 1}",
                            "content": part,
                            "text": part,
                            "prompt": "A Korean finance editorial comic scene with one clear visual metaphor and specific business context.",
                            "section": section_type
                        })
                logger.info(f"script_meta_json에서 {len(scenes_meta)}개 씬 복원 성공")
            except Exception as e:
                logger.error(f"script_meta_json에서 씬 목록 추출 실패: {e}")
                scenes_meta = []

        if not scenes_meta:
            scenes_meta = []

        if scenes_meta and bool(runtime_config.value("article_evidence_auto_enabled")):
            try:
                from app.services.article.evidence_planner import (
                    ArticleEvidencePlanner,
                    NarrationHashMismatch,
                )

                planned = ArticleEvidencePlanner().attach(
                    job_id=job_id,
                    scenes=scenes_meta,
                    verified_facts=list(script_data.get("verified_facts") or []),
                )
                scenes_meta = planned.scenes
                self.evidence_audit = planned.audit
            except NarrationHashMismatch:
                raise
            except Exception as exc:
                # Public news is an optional evidence enhancement.  Search,
                # publisher, or capture failures preserve the approved scene.
                logger.warning("automatic article evidence planning skipped: %s", exc)
                self.evidence_audit = {
                    "job_id": job_id,
                    "status": "unavailable",
                    "reason": str(exc),
                    "selected": [],
                }

        if scenes_meta and not all(scene.get("art_direction") for scene in scenes_meta):
            scenes_meta = direct_scenes([
                enrich_scene_plan(scene, i, len(scenes_meta))
                for i, scene in enumerate(scenes_meta)
            ])
        budget_preflight = None
        if scenes_meta:
            billable_scenes = [scene for scene in scenes_meta if not _article_evidence_path(scene)]
            # Cost is planned before the first image call.  A high Pro limit
            # is reduced to Flash coverage rather than rejecting a whole job.
            estimated_total_duration = infer_total_duration_seconds(
                scenes_meta,
                float(runtime_config.value("scene_duration_sec")),
            )
            # Each selected scene produces one Fal/Kling request; retain the
            # actual seconds separately for audit because the provider caps a
            # request at five seconds.
            intro_motion_indices, motion_target_seconds, planned_motion_seconds = select_intro_motion_scene_indices(
                billable_scenes,
                estimated_total_duration,
                short_seconds=float(runtime_config.value("intro_motion_seconds_short")),
                long_seconds=float(runtime_config.value("intro_motion_seconds_long")),
                short_threshold=float(runtime_config.value("intro_motion_short_threshold")),
                max_clips=(
                    0
                    if not bool(runtime_config.value("intro_motion_enabled"))
                    else min(
                        2 if bool(runtime_config.value("intro_motion_test_mode")) else int(runtime_config.value("intro_motion_clip_count")),
                        int(runtime_config.value("intro_motion_clip_count")),
                    )
                ),
                clip_seconds=float(runtime_config.value("intro_motion_clip_seconds")),
            )
            budget_preflight = plan_preflight(
                len(billable_scenes),
                str(runtime_config.value("image_quality_tier")),
                int(runtime_config.value("pro_image_max_scenes")),
                len(intro_motion_indices),
            )
            if not billable_scenes:
                # plan_preflight normally reserves one generated thumbnail;
                # an evidence-only job has no generated still at all.
                budget_preflight.update({
                    "pro_scene_count": 0,
                    "flash_scene_count": 0,
                    "kling_clip_count": 0,
                    "estimated_cost_krw": 0,
                    "actions": [],
                    "allowed": True,
                    "reason": None,
                })
            budget_preflight["intro_motion_target_seconds"] = motion_target_seconds
            budget_preflight["intro_motion_planned_seconds"] = planned_motion_seconds
            budget_preflight["intro_motion_estimated_total_seconds"] = estimated_total_duration
            write_preflight(job_id, budget_preflight)
            if not budget_preflight["allowed"]:
                raise RuntimeError(
                    f"Budget preflight blocked this job: expected ₩{budget_preflight['estimated_cost_krw']:,} "
                    f"> limit ₩{budget_preflight['budget_limit_krw']:,} ({budget_preflight['reason']})"
                )
            if budget_preflight["actions"]:
                logger.warning("Budget preflight degraded optional quality: %s", budget_preflight["actions"])
            tiered_billable_scenes = plan_image_quality_tiers(
                billable_scenes,
                runtime_config.value("image_quality_tier"),
                int(budget_preflight["pro_scene_count"]),
            )
            tiered_iter = iter(tiered_billable_scenes)
            scenes_meta = [scene if _article_evidence_path(scene) else next(tiered_iter) for scene in scenes_meta]

        # Visual direction is deliberately separate from script writing. One
        # coordinated request assigns a distinct role/costume/action to every
        # scene; a deterministic fallback keeps the pipeline runnable when
        # the director is temporarily unavailable.
        directed_specs: dict[int, SceneSpec] = {}
        article_evidence_indices = {index for index, scene in enumerate(scenes_meta) if _article_evidence_path(scene)}
        if scenes_meta:
            topic_context = " ".join(
                str(scene.get("title") or scene.get("section") or "") for scene in scenes_meta[:4]
            )
            lines = [
                (str(index), str(scene.get("content") or scene.get("text") or scene.get("prompt") or scene.get("title") or "시장 분석"))
                for index, scene in enumerate(scenes_meta)
                if index not in article_evidence_indices
            ]
            specs = SceneDirector().direct_batch(lines, topic_context=topic_context) if lines else []
            directed_specs = {int(spec.scene_id): spec for spec in specs if str(spec.scene_id).isdigit()}
            for index, scene in enumerate(scenes_meta):
                if spec := directed_specs.get(index):
                    scene["scene_spec"] = spec.to_dict()
                    scene["headline"] = spec.headline

        # A selected channel character is an identity lock, not an additional
        # suggestion next to the legacy Goldie sheet.  Passing both images to
        # Gemini was the source of the unwanted mint/coin character mixture.
        selected_character_exists = bool(character_image_path and Path(character_image_path).exists())
        character_reference_paths = []
        reference_candidates = [character_image_path] if selected_character_exists else [str(DEFAULT_CHARACTER_SHEET)]
        for path in reference_candidates:
            if path and Path(path).exists() and path not in character_reference_paths:
                character_reference_paths.append(path)
        if selected_character_exists or character_poses_dir or lora_model_id:
            # When a real per-channel asset/pose/LoRA is supplied, do not let
            # the provider inject its legacy generic mascot description.
            character_style_prompt = character_style_prompt or "none"

        # [S2-3] 이중 레이어 합성 모드 제어
        # A pose library is a reference resource, not permission to paste a
        # separately rendered mascot over an unrelated background.  Pro 2K
        # scenes must be generated as one integrated illustration.
        # A selected pose library gives us a real pre-character image.  That
        # image is persisted as ``clean_plate_path`` and is the only allowed
        # backdrop for mascot/person thumbnail presets.  Without a pose
        # library we preserve the existing integrated-scene pipeline and the
        # thumbnail planner will select chart/article layouts instead.
        use_composite = bool(character_poses_dir and Path(character_poses_dir).is_dir())
        if use_composite:
            logger.info(f"[합성모드] 이중 레이어 합성 활성화: poses_dir={character_poses_dir}")
        else:
            logger.info("캐릭터 라이브러리 없음 → 일체형 모드")

        # LoRA 사용 여부 로깅
        if lora_model_id:
            logger.info(
                f"[LoRA 모드] 활성화: trigger_word={lora_trigger_word}, scale={lora_scale}"
            )

        # AI 이미지 프로바이더 로드
        ai_provider = None
        try:
            from app.providers.factory import get_image_provider
            ai_provider = get_image_provider()
            logger.info("일러스트 전용 모드 활성화: 모든 씬에 AI 캐릭터 일러스트 생성")
        except Exception as e:
            logger.warning(f"AI 이미지 프로바이더 로드 실패: {e}")

        job_dir = Path(f"/app/data/jobs/{job_id}/images")
        job_dir.mkdir(parents=True, exist_ok=True)

        def build_batch_scene(original: dict, index: int) -> dict:
            scene = enrich_scene_plan(original, index, len(scenes_meta))
            narration = scene.get("content") or scene.get("text") or ""
            spec = directed_specs.get(index)
            base_prompt = scene.get("prompt_en") or scene.get("prompt") or narration or scene.get("title") or ""
            prompt_en = build_prompt(spec, scene.get("market_chart")) if spec else compile_editorial_prompt(scene, base_prompt)
            return {
                **scene,
                "index": index,
                "section": scene.get("section", f"scene_{index}"),
                "prompt_en": prompt_en,
                "prompt_ko": scene.get("prompt_ko") or narration or scene.get("title") or "",
                "prompt": prompt_en,
                "pose": scene.get("pose", "neutral"),
                "visual_type": scene.get("visual_type"),
                "visual_plan": scene.get("visual_plan"),
                "art_direction": scene.get("art_direction") or {},
                "style_profile": scene.get("style_profile", "editorial_comic_2d"),
                "image_profile": scene.get("image_profile") or {},
                "market_snapshot": scene.get("market_snapshot") or market_snapshot,
                "market_chart": scene.get("market_chart"),
                "index_data": scene.get("index_data"),
                "bubble_text": scene.get("bubble_text", ""),
                "motion_type": scene.get("motion_type", ""),
                "text": narration,
                "headline": spec.headline if spec else scene.get("headline", ""),
                "headline_mood": spec.mood if spec else "neutral",
                "scene_spec": spec.to_dict() if spec else scene.get("scene_spec"),
            }

        # Batch is an explicitly selected economy mode. Interactive video
        # creation stays on synchronous Pro rendering and only falls back to
        # Batch after a retry-exhausted direct scene failure.
        use_pro_batch = (
            bool(runtime_config.value("gemini_pro_batch_enabled"))
            and runtime_config.value("image_provider") == "gemini"
            and bool(scenes_meta)
            and not article_evidence_indices
            and all((scene.get("image_profile") or {}).get("tier") == "pro" for scene in scenes_meta)
            and not lora_model_id
        )
        if use_pro_batch:
            batch_scenes = [build_batch_scene(scene, i) for i, scene in enumerate(scenes_meta)]
            logger.info("Gemini Pro Batch submit: job=%s scenes=%s", job_id, len(batch_scenes))
            return gemini_batch.submit(job_id, batch_scenes, character_reference_paths)

        # Direct and character-composite renders use scene-specific files, so
        # both can safely share the same bounded worker pool.
        if (
            ai_provider
            and len(scenes_meta) > 1
            and not article_evidence_indices
            and bool(runtime_config.value("gemini_parallel_enabled"))
        ):
            return self._generate_parallel_scenes(
                scenes_meta=scenes_meta,
                directed_specs=directed_specs,
                market_snapshot=market_snapshot,
                character_reference_paths=character_reference_paths,
                character_style_prompt=character_style_prompt,
                lora_model_id=lora_model_id,
                lora_trigger_word=lora_trigger_word,
                lora_scale=lora_scale,
                ai_provider=ai_provider,
                job_dir=job_dir,
                job_id=job_id,
                use_composite=use_composite,
                character_poses_dir=character_poses_dir,
                budget_preflight=budget_preflight,
            )

        generated = []
        # Keep direct Pro 2K rendering interactive, but do not burst a long
        # sequence of paid requests into a transient rate/availability limit.
        last_pro_request_finished_at = None
        for i, scene in enumerate(scenes_meta):
            if is_job_stopped(job_id):
                raise RuntimeError(f"Job {job_id} stopped by user.")
            evidence_path = _article_evidence_path(scene)
            if evidence_path:
                if not Path(evidence_path).is_file() or Path(evidence_path).stat().st_size < 100:
                    raise RuntimeError(f"article evidence scene {i} has no valid captured image: {evidence_path}")
                # Do not send screenshots to Gemini/Fal or substitute them with
                # a generated still.  This keeps DOM coordinates exact and
                # makes the scene's generation cost objectively zero.
                generated.append({
                    **scene,
                    "index": i,
                    "image_path": evidence_path,
                    "generation_method": "article_evidence",
                    "generation_cost_krw": 0,
                    "use_kling": False,
                    "quality_score": 100,
                })
                logger.info("scene %s uses captured article evidence directly (Gemini/Kling skipped)", i)
                continue
            scene = enrich_scene_plan(scene, i, len(scenes_meta))
            section = scene.get("section", f"scene_{i}")
            narration = scene.get("content") or scene.get("text") or ""

            spec = directed_specs.get(i)
            base_prompt = scene.get("prompt_en") or scene.get("prompt") or narration or scene.get("title") or ""
            prompt_en = build_prompt(spec, scene.get("market_chart")) if spec else compile_editorial_prompt(scene, base_prompt)
            prompt_ko = scene.get("prompt_ko") or narration or scene.get("title") or ""
            pose = scene.get("pose", "neutral")
            art_direction = scene.get("art_direction") or {}
            image_profile = scene.get("image_profile") or {}
            is_direct_pro_scene = (
                image_profile.get("tier") == "pro"
                and runtime_config.value("image_provider") == "gemini"
            )
            scene_market_snapshot = scene.get("market_snapshot") or market_snapshot
            character_required = bool(art_direction.get("character_required", True))
            pose_asset = art_direction.get("pose_asset") or pose
            # Keep a successful composite render on the normal quality path.
            # (The direct AI path assigns this inside its retry loop.)
            quality_score = 0

            img_path = str(job_dir / f"scene_{i:03d}.png")
            raw_img_path = str(job_dir / f"scene_{i:03d}_raw.png")
            background_path = None

            # If a long HTTP request was interrupted after this frame completed,
            # recover from disk instead of charging the image model a second time.
            if os.path.exists(img_path) and os.path.getsize(img_path) > 15000:
                resumed_clean_plate = str(job_dir / f"scene_{i:03d}_bg.png")
                if not Path(resumed_clean_plate).is_file():
                    resumed_clean_plate = None
                generated.append({
                    **scene,
                    "index": i, "section": section, "image_path": img_path,
                    "generation_method": "resumed_existing", "quality_score": 90,
                    "prompt_en": prompt_en, "prompt_ko": prompt_ko, "prompt": prompt_en,
                    "pose": pose, "visual_type": scene.get("visual_type"),
                    "visual_plan": scene.get("visual_plan"), "art_direction": art_direction,
                    "style_profile": scene.get("style_profile", "editorial_comic_2d"),
                    "image_profile": image_profile, "market_snapshot": scene_market_snapshot,
                    "market_chart": scene.get("market_chart"), "index_data": scene.get("index_data"),
                    "bubble_text": scene.get("bubble_text", ""),
                    "motion_type": scene.get("motion_type", ""),
                    "text": narration, "headline": spec.headline if spec else scene.get("headline", ""),
                    "headline_mood": spec.mood if spec else "neutral",
                    "scene_spec": spec.to_dict() if spec else scene.get("scene_spec"),
                    "clean_plate_path": resumed_clean_plate,
                    "asset_layout_metadata": _asset_layout_metadata(scene, resumed_clean_plate),
                })
                logger.info("Reusing completed image scene %s for job %s", i, job_id)
                continue

            if ai_provider:
                try:
                    effective_character_style = character_style_prompt if character_required else "none"
                    if use_composite:
                        # [S2-3] 이중 레이어 합성
                        bg_path = str(job_dir / f"scene_{i:03d}_bg.png")
                        background_path = bg_path
                        self._generate_background_layer(
                            ai_provider, prompt_en, bg_path, section, pose, image_profile
                        )
                        # [버그 수정] 오버레이(데이터 차트 등)는 배경에 먼저 그려야 캐릭터가 패널을 가리지 않음
                        # Keep factual numbers and labels out of the still.  They
                        # are composited after Kling/static assembly, where they
                        # stay crisp and cannot be regenerated by a video model.
                        self._normalize_canvas(bg_path)
                        
                        x_ratio = 0.02 if scene.get("market_chart") else CHAR_OVERLAY_X_RATIO
                        if character_required:
                            self._composite_character(
                                bg_path, character_poses_dir, pose_asset, img_path, job_id,
                                fallback_pose=pose,
                                x_ratio=x_ratio
                            )
                        else:
                            import shutil
                            shutil.copy2(bg_path, img_path)
                            
                        if runtime_config.value("image_headline_overlay"):
                            add_headline(img_path, img_path, spec.headline if spec else scene.get("headline", ""), spec.mood if spec else "neutral")
                    else:
                        # [Sprint 3 & S5] LoRA 또는 기본 일체형 모드 + AI 품질 검수 자동 재생성
                        max_retries = 2
                        for attempt in range(max_retries):
                            if is_direct_pro_scene and last_pro_request_finished_at is not None:
                                delay_seconds = max(
                                    0.0,
                                    float(runtime_config.value("gemini_pro_request_delay_seconds")),
                                )
                                remaining_delay = delay_seconds - (
                                    time.monotonic() - last_pro_request_finished_at
                                )
                                if remaining_delay > 0:
                                    logger.info(
                                        "Pacing Gemini Pro request for job %s scene %s: waiting %.1fs",
                                        job_id, i, remaining_delay,
                                    )
                                    time.sleep(remaining_delay)
                            try:
                                ai_provider.generate_image(
                                    prompt=prompt_en,
                                    output_path=raw_img_path,
                                    section=section,
                                    keyword=prompt_en[:30],
                                    character_image_path=character_reference_paths[0] if character_reference_paths else None,
                                    character_image_paths=character_reference_paths,
                                    character_style_prompt=effective_character_style,
                                    lora_model_id=lora_model_id,
                                    lora_trigger_word=lora_trigger_word,
                                    lora_scale=lora_scale,
                                    image_provider=runtime_config.value("image_provider"),
                                    gemini_model=image_profile.get("model"),
                                    gemini_image_size=image_profile.get("image_size"),
                                    gemini_service_tier=runtime_config.value("gemini_service_tier"),
                                    gemini_max_attempts=runtime_config.value("gemini_pro_max_attempts"),
                                    gemini_retry_base_seconds=runtime_config.value("gemini_pro_retry_base_seconds"),
                                    style_locked=bool(spec),
                                )
                            finally:
                                if is_direct_pro_scene:
                                    last_pro_request_finished_at = time.monotonic()
                            # [S5] AI 품질 자동 검수
                            if os.path.exists(raw_img_path) and os.path.getsize(raw_img_path) > 15000:
                                if runtime_config.value("image_headline_overlay"):
                                    add_headline(raw_img_path, img_path, spec.headline if spec else scene.get("headline", ""), spec.mood if spec else "neutral")
                                else:
                                    # Generated typography distracts from the scene.  Keep
                                    # the clean Pro frame and render spoken text as subtitles.
                                    import shutil
                                    shutil.copy2(raw_img_path, img_path)
                                self._apply_image_overlays(scene, img_path)
                                quality_score = 95 if lora_model_id else 90
                                break
                            else:
                                logger.warning(f"씬 {i} 이미지 품질 미달/손상 (attempt {attempt+1}/{max_retries}), 자동 재생성 시도...")
                        if quality_score == 0:
                            raise RuntimeError("최대 재시도 후에도 고품질 이미지 생성 실패")

                    # Generate variations if hold time exceeds limit
                    duration = scene_duration_seconds(scene, float(runtime_config.value("scene_duration_sec")))
                    max_hold = float(runtime_config.value("max_image_hold_seconds"))
                    if duration > max_hold:
                        import math
                        num_vars = math.ceil(duration / max_hold)
                        for v in range(1, num_vars):
                            var_img_path = str(job_dir / f"scene_{i:03d}_var_{v}.jpg")
                            var_prompt = prompt_en + f", alternate visual angle version {v}"
                            try:
                                if use_composite:
                                    var_bg_path = str(job_dir / f"scene_{i:03d}_bg_var_{v}.png")
                                    self._generate_background_layer(
                                        ai_provider, var_prompt, var_bg_path, section, pose, image_profile
                                    )
                                    self._normalize_canvas(var_bg_path)
                                    
                                    x_ratio = 0.02 if scene.get("market_chart") else CHAR_OVERLAY_X_RATIO
                                    if character_required:
                                        self._composite_character(
                                            var_bg_path, character_poses_dir, pose_asset, var_img_path, job_id,
                                            fallback_pose=pose,
                                            x_ratio=x_ratio
                                        )
                                    else:
                                        import shutil
                                        shutil.copy2(var_bg_path, var_img_path)
                                else:
                                    var_raw_path = str(job_dir / f"scene_{i:03d}_raw_var_{v}.jpg")
                                    ai_provider.generate_image(
                                        prompt=var_prompt,
                                        output_path=var_raw_path,
                                        section=section,
                                        keyword=var_prompt[:30],
                                        character_image_path=character_reference_paths[0] if character_reference_paths else None,
                                        character_style_prompt=effective_character_style,
                                        lora_model_id=lora_model_id,
                                        image_provider=runtime_config.value("image_provider"),
                                        gemini_model=image_profile.get("model"),
                                        gemini_image_size=image_profile.get("image_size"),
                                    )
                                    import shutil
                                    shutil.copy2(var_raw_path, var_img_path)
                                    self._apply_image_overlays(scene, var_img_path)
                                if runtime_config.value("image_headline_overlay"):
                                    add_headline(var_img_path, var_img_path, spec.headline if spec else scene.get("headline", ""), spec.mood if spec else "neutral")
                                logger.info(f"Generated hold-time split variation {v} for scene {i} -> {var_img_path}")
                            except Exception as var_ex:
                                logger.warning(f"Failed to generate hold-time split variation {v} for scene {i}: {var_ex}. Copying original.")
                                import shutil
                                shutil.copy2(img_path, var_img_path)

                    generated.append({
                        **scene,
                        "index": i,
                        "section": section,
                        "image_path": img_path,
                        "background_path": background_path,
                        "clean_plate_path": background_path,
                        "asset_layout_metadata": _asset_layout_metadata(scene, background_path),
                        "generation_method": "composite" if use_composite else ("flux_lora" if lora_model_id else image_profile.get("tier", "flash") + "_gemini"),
                        "quality_score": quality_score or 85,
                        "prompt_en": prompt_en,
                        "prompt_ko": prompt_ko,
                        "prompt": prompt_en,
                        "pose": pose,
                        "visual_type": scene.get("visual_type"),
                        "visual_plan": scene.get("visual_plan"),
                        "art_direction": art_direction,
                        "style_profile": scene.get("style_profile", "editorial_comic_2d"),
                        "image_profile": image_profile,
                        "market_snapshot": scene_market_snapshot,
                        "market_chart": scene.get("market_chart"),
                        "index_data": scene.get("index_data"),
                        "bubble_text": scene.get("bubble_text", ""),
                        "motion_type": scene.get("motion_type", ""),
                        "text": narration,
                        "headline": spec.headline if spec else scene.get("headline", ""),
                        "headline_mood": spec.mood if spec else "neutral",
                        "scene_spec": spec.to_dict() if spec else scene.get("scene_spec"),
                    })
                    logger.info(f"씬 {i} AI 이미지 생성 및 품질 검수 완료 (점수={quality_score or 85})")
                    continue
                except Exception as e:
                    if image_profile.get("tier") == "pro":
                        if bool(runtime_config.value("gemini_pro_batch_fallback_enabled")) and not lora_model_id:
                            remaining = [
                                build_batch_scene(remaining_scene, remaining_index)
                                for remaining_index, remaining_scene in enumerate(scenes_meta[i:], start=i)
                            ]
                            logger.warning(
                                "Gemini Pro direct render exhausted retries at scene %s; "
                                "submitting %s remaining scenes to Batch fallback (completed=%s).",
                                i, len(remaining), len(generated),
                            )
                            return gemini_batch.submit(
                                job_id,
                                remaining,
                                character_reference_paths,
                                completed_scenes=generated,
                            )
                        # Do not publish the text-on-solid-background fallback
                        # when a reference-quality image request failed.
                        raise RuntimeError(f"Pro image scene {i} failed: {e}") from e
                    logger.warning(f"씬 {i} AI 이미지 실패, 폴백 Solid 배경 생성: {e}")


            # 로컬 폴백 (Matplotlib 고체 단색 배경 렌더링)
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            try:
                self._render_fallback(narration, img_path, plt)
                generated.append({
                    **scene,
                    "index": i,
                    "section": section,
                    "image_path": img_path,
                    "generation_method": "fallback_solid",
                    "prompt_en": prompt_en,
                    "prompt_ko": prompt_ko,
                    "prompt": prompt_en,
                    "pose": pose,
                    "visual_type": scene.get("visual_type"),
                    "visual_plan": scene.get("visual_plan"),
                    "art_direction": art_direction,
                    "style_profile": scene.get("style_profile", "editorial_comic_2d"),
                    "image_profile": image_profile,
                    "market_snapshot": scene_market_snapshot,
                    "market_chart": scene.get("market_chart"),
                    "index_data": scene.get("index_data"),
                    "bubble_text": scene.get("bubble_text", ""),
                    "motion_type": scene.get("motion_type", ""),
                    "text": narration,
                })
            except Exception as e:
                logger.error(f"씬 {i} 로컬 폴백 최종 실패: {e}")

        for scene in generated:
            scene["character_regions"] = _character_regions(scene)
        image_quality = assess_images(generated)
        semantic_quality = assess_visual_alignment(
            generated,
            enabled=bool(runtime_config.value("visual_qa_enabled")),
            max_scenes=int(runtime_config.value("visual_qa_max_scenes")),
        )
        semantic_by_index = {item["index"]: item for item in semantic_quality.get("reviewed", [])}
        metrics_by_index = {
            metric["index"]: metric
            for metric in image_quality.get("scene_metrics", [])
        }
        for scene in generated:
            metric = metrics_by_index.get(scene.get("index"), {})
            scene["quality_score"] = metric.get("score", 0)
            scene["quality_flags"] = metric.get("warnings", [])
            scene["retry_recommended"] = metric.get("retry_recommended", False)
            semantic = semantic_by_index.get(scene.get("index"))
            if semantic:
                scene["semantic_score"] = semantic["score"]
                scene["semantic_reason"] = semantic["reason"]
                scene["quality_score"] = min(scene["quality_score"], semantic["score"])
                scene["retry_recommended"] = scene["retry_recommended"] or semantic["retry_recommended"]
                if semantic["retry_recommended"]:
                    scene["quality_flags"] = [*scene["quality_flags"], "semantic_review_recommended"]
        image_quality["art_direction"] = assess_art_diversity(generated)
        image_quality["semantic_alignment"] = semantic_quality
        image_quality["scene_metadata_contract"] = _scene_metadata_contract(scenes_meta, generated)
        persist_quality_report(job_id, "images", image_quality)
        logger.info(f"이미지 생성 완료: {len(generated)}개, quality={image_quality['score']}")
        return {
            "job_id": job_id,
            "scenes": generated,
            "scene_count": len(generated),
            "gifs": [],
            "gif_count": 0,
            "quality_report": {"images": image_quality},
            "evidence_audit": self.evidence_audit,
        }

    def _generate_parallel_scenes(
        self, scenes_meta, directed_specs, market_snapshot,
        character_reference_paths, character_style_prompt,
        lora_model_id, lora_trigger_word, lora_scale,
        ai_provider, job_dir, job_id, use_composite=False, character_poses_dir=None,
        budget_preflight=None,
    ) -> dict:
        """Render independent direct-AI scenes with bounded concurrency.

        Each task writes to a scene-specific raw file and only publishes the
        final path after validating a decodable image. A failed task never
        becomes a scene entry, and the method raises before quality/assembly
        when any scene failed. Re-running the job reuses validated outputs.
        """
        import shutil

        def valid_image(path: str) -> bool:
            try:
                if not os.path.exists(path) or os.path.getsize(path) <= 15000:
                    return False
                try:
                    from PIL import Image
                    with Image.open(path) as image:
                        image.verify()
                except ImportError:
                    pass
                return True
            except (OSError, ValueError):
                return False

        def make_context(original: dict, index: int) -> dict:
            scene = enrich_scene_plan(original, index, len(scenes_meta))
            narration = scene.get("content") or scene.get("text") or ""
            spec = directed_specs.get(index)
            base_prompt = scene.get("prompt_en") or scene.get("prompt") or narration or scene.get("title") or ""
            prompt_en = build_prompt(spec, scene.get("market_chart")) if spec else compile_editorial_prompt(scene, base_prompt)
            image_profile = scene.get("image_profile") or {}
            return {
                **scene,
                "index": index,
                "section": scene.get("section", f"scene_{index}"),
                "prompt_en": prompt_en,
                "prompt_ko": scene.get("prompt_ko") or narration or scene.get("title") or "",
                "pose": scene.get("pose", "neutral"),
                "visual_type": scene.get("visual_type"),
                "visual_plan": scene.get("visual_plan"),
                "art_direction": scene.get("art_direction") or {},
                "style_profile": scene.get("style_profile", "editorial_comic_2d"),
                "image_profile": image_profile,
                "market_snapshot": scene.get("market_snapshot") or market_snapshot,
                "text": narration,
                "headline": spec.headline if spec else scene.get("headline", ""),
                "headline_mood": spec.mood if spec else "neutral",
                "scene_spec": spec.to_dict() if spec else scene.get("scene_spec"),
                "spec": spec,
                # §7: overlay keys — must be propagated or _apply_image_overlays silently skips
                "bubble_text": scene.get("bubble_text", ""),
                "motion_type": scene.get("motion_type", ""),
                "market_chart": scene.get("market_chart"),
                "index_data": scene.get("index_data"),
            }

        contexts = [make_context(scene, index) for index, scene in enumerate(scenes_meta)]
        manifest_path = job_dir / "images_manifest.json"
        try:
            image_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(image_manifest, dict):
                image_manifest = {}
        except (OSError, ValueError, TypeError):
            image_manifest = {}

        def fingerprint(ctx: dict) -> str:
            payload = {
                "prompt_en": ctx["prompt_en"],
                "image_profile": ctx["image_profile"],
                "character_style_prompt": character_style_prompt,
                "character_reference_paths": character_reference_paths,
                "use_composite": use_composite,
                "character_poses_dir": character_poses_dir,
                "lora_model_id": lora_model_id,
                "lora_trigger_word": lora_trigger_word,
                "lora_scale": lora_scale,
            }
            return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()

        def render_one(ctx: dict) -> dict:
            index = ctx["index"]
            img_path = str(job_dir / f"scene_{index:03d}.png")
            raw_img_path = str(job_dir / f"scene_{index:03d}_raw.png")
            background_path = None
            image_profile = ctx["image_profile"]
            tier = image_profile.get("tier", "flash")
            scene_fingerprint = fingerprint(ctx)
            # Legacy files without a manifest remain resumable; once a
            # manifest exists, a changed prompt/profile forces regeneration.
            if valid_image(img_path) and (str(index) not in image_manifest or image_manifest.get(str(index)) == scene_fingerprint):
                resumed_clean_plate = str(job_dir / f"scene_{index:03d}_bg.png")
                if not Path(resumed_clean_plate).is_file():
                    resumed_clean_plate = None
                return {**ctx, "image_path": img_path, "clean_plate_path": resumed_clean_plate,
                        "asset_layout_metadata": _asset_layout_metadata(ctx, resumed_clean_plate),
                        "generation_method": "resumed_existing", "quality_score": 90, "_fingerprint": scene_fingerprint}

            max_retries = max(1, min(int(runtime_config.value("gemini_retry_max")), 8))
            base_backoff = max(0.25, float(runtime_config.value("gemini_pro_retry_base_seconds")))
            last_error = None
            for attempt in range(max_retries):
                if is_job_stopped(job_id):
                    raise RuntimeError(f"Job {job_id} stopped by user.")
                provider_request_started = False
                try:
                    Path(raw_img_path).unlink(missing_ok=True)
                    if use_composite:
                        bg_path = str(job_dir / f"scene_{index:03d}_bg.png")
                        background_path = bg_path
                        self._generate_background_layer(
                            ai_provider, ctx["prompt_en"], bg_path, ctx["section"], ctx["pose"], image_profile,
                        )
                        if not valid_image(bg_path):
                            raise RuntimeError("provider returned a missing, undersized, or invalid background")
                        
                        # TASK 1: 정규화
                        self._normalize_canvas(bg_path)
                        
                        # ① 차트를 배경에 먼저
                        # The final video compositor owns verified graphics and
                        # labels.  Do not bake them into a Kling input frame.
                        # ② 캐릭터 합성
                        x_ratio = 0.02 if ctx.get("market_chart") else CHAR_OVERLAY_X_RATIO
                        if ctx["art_direction"].get("character_required", True):
                            self._composite_character(
                                bg_path, character_poses_dir, ctx["art_direction"].get("pose_asset") or ctx["pose"],
                                img_path, job_id, fallback_pose=ctx["pose"],
                                x_ratio=x_ratio
                            )
                        else:
                            shutil.copy2(bg_path, img_path)
                            
                        # ③ 말풍선은 캐릭터 위에
                        if runtime_config.value("image_headline_overlay"):
                            add_headline(img_path, img_path, ctx["headline"], ctx["headline_mood"])
                    else:
                        gemini_pressure.acquire()
                        provider_request_started = True
                        ai_provider.generate_image(
                            prompt=ctx["prompt_en"],
                            output_path=raw_img_path,
                            section=ctx["section"],
                            keyword=ctx["prompt_en"][:30],
                            character_image_path=character_reference_paths[0] if character_reference_paths else None,
                            character_image_paths=character_reference_paths,
                            character_style_prompt=character_style_prompt if ctx["art_direction"].get("character_required", True) else "none",
                            lora_model_id=lora_model_id,
                            lora_trigger_word=lora_trigger_word,
                            lora_scale=lora_scale,
                            image_provider=runtime_config.value("image_provider"),
                            gemini_model=image_profile.get("model"),
                            gemini_image_size=image_profile.get("image_size"),
                            gemini_service_tier=runtime_config.value("gemini_service_tier"),
                            gemini_max_attempts=1,
                            gemini_retry_base_seconds=runtime_config.value("gemini_pro_retry_base_seconds"),
                            style_locked=bool(ctx["spec"]),
                        )
                        if not valid_image(raw_img_path):
                            raise RuntimeError("provider returned a missing, undersized, or invalid image")
                        gemini_pressure.outcome()
                        provider_request_started = False
                        
                        shutil.copy2(raw_img_path, img_path)
                        
                        self._apply_image_overlays(ctx, img_path)
                        
                        if runtime_config.value("image_headline_overlay"):
                            add_headline(img_path, img_path, ctx["headline"], ctx["headline_mood"])

                    if not valid_image(img_path):
                        raise RuntimeError("final image validation failed")
                    return {
                        **ctx,
                        "image_path": img_path,
                        "background_path": background_path,
                        "clean_plate_path": background_path,
                        "asset_layout_metadata": _asset_layout_metadata(ctx, background_path),
                        "generation_method": "flux_lora" if lora_model_id else f"{tier}_gemini",
                        "quality_score": 95 if lora_model_id else 90,
                        "_fingerprint": scene_fingerprint,
                    }
                except Exception as exc:
                    last_error = exc
                    if provider_request_started:
                        gemini_pressure.outcome(str(exc))
                    decision = classify_image_error(exc)
                    if not decision.retryable:
                        raise NonRetryableImageGenerationError(
                            f"scene {index} stopped: non-retryable ({decision.reason}): {exc}"
                        ) from exc
                    if attempt + 1 >= max_retries:
                        break
                    delay = min(60.0, base_backoff * (2 ** attempt) + random.uniform(0.0, 1.0))
                    logger.warning(
                        "Image scene %s attempt %s/%s failed; retrying in %.1fs: %s",
                        index, attempt + 1, max_retries, delay, exc,
                    )
                    time.sleep(delay)
            raise RuntimeError(f"scene {index} image generation failed after {max_retries} attempts: {last_error}")

        configured_workers = max(1, min(int(runtime_config.value("gemini_max_concurrency")), 32))
        max_workers = gemini_pressure.recommended_concurrency(configured_workers)
        logger.info("Parallel image generation enabled: job=%s scenes=%s concurrency=%s retries=%s", job_id, len(contexts), max_workers, runtime_config.value("gemini_retry_max"))
        results = []
        failures = []
        same_error_counts: Counter[str] = Counter()
        break_count = max(1, int(runtime_config.value("image_same_error_break_count")))
        def persist_manifest() -> None:
            staged = manifest_path.with_suffix(".tmp")
            staged.write_text(json.dumps(image_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(staged, manifest_path)

        with ThreadPoolExecutor(max_workers=min(max_workers, len(contexts)), thread_name_prefix="image") as pool:
            futures = {pool.submit(render_one, ctx): ctx["index"] for ctx in contexts}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    result = future.result()
                    image_manifest[str(index)] = result.pop("_fingerprint", "")
                    persist_manifest()
                    if result.get("generation_method") != "resumed_existing":
                        tier = str((result.get("image_profile") or {}).get("tier") or "flash")
                        record_cost(job_id, "pro" if tier == "pro" else "flash")
                    results.append(result)
                    logger.info("Parallel image scene complete: job=%s scene=%s", job_id, index)
                except Exception as exc:
                    failures.append((index, str(exc)))
                    logger.error("Parallel image scene failed: job=%s scene=%s error=%s", job_id, index, exc)
                    if isinstance(exc, NonRetryableImageGenerationError):
                        for pending in futures:
                            pending.cancel()
                        root_cause = exc.__cause__ or exc
                        decision = classify_image_error(root_cause)
                        if decision.reason == "permanent provider billing/quota response":
                            raise ImageProviderCreditRequiredError(
                                "IMAGE_PROVIDER_CREDIT_REQUIRED: Gemini image credits or quota are unavailable. "
                                "Restore billing, then retry image generation; completed scenes will be reused."
                            ) from exc
                        raise RuntimeError(
                            f"Image generation stopped before recovery: scene {index} has a non-retryable error: {exc}"
                        ) from exc
                    signature = error_signature(exc.__cause__ or exc)
                    same_error_counts[signature] += 1
                    if same_error_counts[signature] >= break_count:
                        for pending in futures:
                            pending.cancel()
                        raise RuntimeError(
                            f"Image generation circuit breaker opened after {same_error_counts[signature]} identical transient failures: {signature}"
                        ) from exc

        # Do not discard hundreds of successful renders because a transient
        # 503 exhausted one scene's local attempts.  Finish the first pass,
        # then give only failed scenes one isolated recovery round.
        if failures:
            logger.warning("Image recovery round: retrying failed scenes only: %s", [index for index, _ in failures])
            context_by_index = {ctx["index"]: ctx for ctx in contexts}
            first_failures = failures
            failures = []
            recovery_workers = min(gemini_pressure.recommended_concurrency(max_workers), len(first_failures))
            with ThreadPoolExecutor(max_workers=max(1, recovery_workers), thread_name_prefix="image-recovery") as pool:
                futures = {pool.submit(render_one, context_by_index[index]): index for index, _ in first_failures}
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        result = future.result()
                        image_manifest[str(index)] = result.pop("_fingerprint", "")
                        persist_manifest()
                        tier = str((result.get("image_profile") or {}).get("tier") or "flash")
                        record_cost(job_id, "pro" if tier == "pro" else "flash")
                        results.append(result)
                        logger.info("Image recovery scene complete: job=%s scene=%s", job_id, index)
                    except Exception as exc:
                        failures.append((index, str(exc)))
                        logger.error("Image recovery scene failed: job=%s scene=%s error=%s", job_id, index, exc)

        if failures:
            failed_indices = ", ".join(str(index) for index, _ in sorted(failures))
            raise RuntimeError(f"Image generation incomplete; failed scenes: {failed_indices}")

        generated = []
        for result in sorted(results, key=lambda item: item["index"]):
            result.pop("spec", None)
            generated.append(result)
        for scene in generated:
            scene["character_regions"] = _character_regions(scene)
        image_quality = assess_images(generated)
        semantic_quality = assess_visual_alignment(
            generated,
            enabled=bool(runtime_config.value("visual_qa_enabled")),
            max_scenes=int(runtime_config.value("visual_qa_max_scenes")),
        )
        semantic_by_index = {item["index"]: item for item in semantic_quality.get("reviewed", [])}
        metrics_by_index = {metric["index"]: metric for metric in image_quality.get("scene_metrics", [])}
        for scene in generated:
            metric = metrics_by_index.get(scene.get("index"), {})
            scene["quality_score"] = metric.get("score", scene.get("quality_score", 0))
            scene["quality_flags"] = metric.get("warnings", [])
            scene["retry_recommended"] = metric.get("retry_recommended", False)
            semantic = semantic_by_index.get(scene.get("index"))
            if semantic:
                scene["semantic_score"] = semantic["score"]
                scene["semantic_reason"] = semantic["reason"]
                scene["quality_score"] = min(scene["quality_score"], semantic["score"])
                scene["retry_recommended"] = scene["retry_recommended"] or semantic["retry_recommended"]
                if semantic["retry_recommended"]:
                    scene["quality_flags"] = [*scene["quality_flags"], "semantic_review_recommended"]
        image_quality["art_direction"] = assess_art_diversity(generated)
        image_quality["semantic_alignment"] = semantic_quality
        image_quality["scene_metadata_contract"] = _scene_metadata_contract(scenes_meta, generated)
        persist_quality_report(job_id, "images", image_quality)
        logger.info("Parallel image generation complete: job=%s scenes=%s quality=%s", job_id, len(generated), image_quality["score"])
        return {
            "job_id": job_id,
            "scenes": generated,
            "scene_count": len(generated),
            "gifs": [],
            "gif_count": 0,
            "quality_report": {"images": image_quality},
            "budget_preflight": budget_preflight,
            "evidence_audit": self.evidence_audit,
        }

    # ============================
    # [S2-3] 배경 레이어 생성
    # ============================
    def _generate_background_layer(self, ai_provider, prompt_en: str, bg_path: str,
                                    section: str, pose: str, image_profile: dict | None = None):
        """
        캐릭터 없는 순수 배경 이미지 생성.
        character_style_prompt="background_only" 를 전달해 캐릭터 주입을 차단.
        """
        gemini_pressure.acquire()
        try:
            ai_provider.generate_image(
            prompt=prompt_en,
            output_path=bg_path,
            section=section,
            keyword=prompt_en[:30],
            character_style_prompt="background_only",
            image_provider=runtime_config.value("image_provider"),
            gemini_model=(image_profile or {}).get("model"),
            gemini_image_size=(image_profile or {}).get("image_size"),
            # Retries are owned by the bounded scene executor.  Keeping a
            # single provider attempt here prevents retry multiplication when
            # a character-composite scene is temporarily rate limited.
            gemini_service_tier=runtime_config.value("gemini_service_tier"),
            gemini_max_attempts=1,
            gemini_retry_base_seconds=runtime_config.value("gemini_pro_retry_base_seconds"),
            )
        except Exception as exc:
            gemini_pressure.outcome(str(exc))
            raise
        else:
            gemini_pressure.outcome()
        logger.info(f"[배경레이어] 생성 완료: {bg_path}")

    # ============================
    # [S2-3] 캐릭터 overlay 합성
    # ============================
    def _run_subprocess(self, cmd: list, job_id: int) -> int:
        import subprocess
        from app.utils.process_manager import register_process, unregister_process
        logger.info(f"Running tracked subprocess (composite): {' '.join(cmd)}")
        p = subprocess.Popen(cmd)
        register_process(job_id, p)
        try:
            ret = p.wait()
            return ret
        finally:
            unregister_process(job_id, p)

    def _composite_character(self, bg_path: str, poses_dir: str, pose: str,
                              output_path: str, job_id: int = 0,
                              fallback_pose: str = None,
                              x_ratio: float = CHAR_OVERLAY_X_RATIO,
                              y_ratio: float = CHAR_OVERLAY_Y_RATIO):
        """
        FFmpeg overlay 필터를 사용해 배경 이미지 위에 캐릭터 투명 PNG를 합성합니다.

        [S2-3] 합성 로직:
          1. 선택된 포즈 PNG (투명 RGBA)를 1080px 높이로 스케일
          2. 배경(1920x1080) 위에 우하단 중앙 위치로 overlay
          3. 합성 실패 시 배경만 출력 (Graceful fallback)
        """
        poses_path = Path(poses_dir)
        pose_file = poses_path / f"{pose}.png"
        if not pose_file.exists() and fallback_pose:
            pose_file = poses_path / f"{fallback_pose}.png"
        if not pose_file.exists():
            pose_file = poses_path / "neutral.png"
        if not pose_file.exists():
            logger.warning(f"[합성] 포즈 파일 없음, 배경만 출력: pose={pose}")
            import shutil
            shutil.copy2(bg_path, output_path)
            return

        # 영상 크기
        # Crop transparent padding before measuring the pose.  Earlier code
        # blindly overlaid a full source canvas at x=1113, so wide pose files
        # were visibly clipped by the right edge.
        from PIL import Image
        trimmed_pose_file = Path(f"{output_path}.character-trim.png")
        try:
            with Image.open(pose_file).convert("RGBA") as pose_image:
                alpha_bounds = pose_image.getchannel("A").getbbox()
                if not alpha_bounds:
                    raise ValueError("pose image has no visible pixels")
                trimmed = pose_image.crop(alpha_bounds)
                trimmed.save(trimmed_pose_file)
                source_width, source_height = trimmed.size

            W, H = 1920, 1080
            is_left = x_ratio <= 0.10
            max_width = int(W * (0.37 if is_left else 0.39))
            max_height = min(int(H * CHAR_HEIGHT_RATIO), H - 140)
            char_h = max(1, min(max_height, int(max_width * source_height / source_width)))
            char_w = max(1, round(source_width * char_h / source_height))
            side_margin = 48
            x_offset = side_margin if is_left else W - char_w - side_margin
            y_offset = H - char_h - 58
        except Exception as exc:
            logger.error("Unable to prepare character composite, using background: %s", exc)
            import shutil
            shutil.copy2(bg_path, output_path)
            trimmed_pose_file.unlink(missing_ok=True)
            return

        # FFmpeg overlay 명령어 (RGBA 투명 합성)
        # 순서: 배경(1920x1080) 실망 스케일 → 캐릭터 크기 조정 → overlay
        pose_file = trimmed_pose_file
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", bg_path,                       # 입력 0: 배경
            "-i", str(pose_file),                 # 입력 1: 캐릭터 투명 PNG
            "-filter_complex",
            (
                # 배경을 1920x1080으로 스케일
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2[bg];"
                # 캐릭터를 높이 char_h px로 스케일 (비율 유지)
                f"[1:v]scale={char_w}:{char_h}[char];"
                # overlay: 우하단 중앙 위치
                f"[bg][char]overlay={x_offset}:{y_offset}[out]"
            ),
            "-map", "[out]",
            "-frames:v", "1",
            "-q:v", "2",
            "-y", output_path
        ]

        try:
            ret = self._run_subprocess(ffmpeg_cmd, job_id=job_id)
            if ret != 0:
                raise RuntimeError(f"FFmpeg process returned non-zero exit code {ret}")
            logger.info(f"[합성] FFmpeg overlay 완료: {output_path}")
        except Exception as e:
            logger.error(f"[합성] FFmpeg overlay 실패, 배경만 사용: {e}")
            import shutil
            shutil.copy2(bg_path, output_path)
        finally:
            trimmed_pose_file.unlink(missing_ok=True)

    # ============================
    # 섹션별 시각화 라우팅
    # ============================
    def _render_section(self, section, text, img_path, plt):
        # AI 이미지가 생성되었을 경우, 기존의 Matplotlib 차트로 덮어씌우지 않습니다.
        # 이 메서드는 이제 사용되지 않지만 하위 호환성을 위해 남겨둡니다.
        pass

    # ── 인트로: 타이틀 카드 ──
    def _render_title_card(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")

        for r, alpha in [(4.5, 0.08), (3.5, 0.12), (2.5, 0.18)]:
            circle = plt.Circle((0.5, 0.55), r/10, color=COLOR_ACCENT_CYAN, alpha=alpha, transform=ax.transAxes)
            ax.add_patch(circle)

        title = self._extract_title(text, max_chars=20)
        ax.text(0.5, 0.55, title, fontsize=52, color=COLOR_TEXT, ha="center", va="center",
                weight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.35, "📈 주식 시장 분석", fontsize=24, color=COLOR_ACCENT_GOLD,
                ha="center", va="center", transform=ax.transAxes)

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 시장 배경: 지수 추이 라인 차트 ──
    def _render_line_chart(self, text, img_path, plt):
        import numpy as np
        signal = _extract_market_signal(text)

        fig, ax2 = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)

        ax2.set_facecolor(COLOR_BG2)
        days = np.arange(30)
        base = 2600
        if signal["direction"] == "up":
            drift = abs(np.random.randn()) * 3 + 1.5
            trend = np.cumsum(np.random.randn(30) * 6 + drift) + base
        elif signal["direction"] == "down":
            drift = -(abs(np.random.randn()) * 3 + 1.5)
            trend = np.cumsum(np.random.randn(30) * 6 + drift) + base
        else:
            trend = np.cumsum(np.random.randn(30) * 8) + base
        color = COLOR_ACCENT_GREEN if trend[-1] > trend[0] else COLOR_ACCENT_RED
        ax2.plot(days, trend, color=color, linewidth=3)
        ax2.fill_between(days, trend, trend.min() - 20, color=color, alpha=0.15)

        if signal["value"]:
            label = signal["value"]
            if signal["pct"] is not None:
                label += f" ({signal['pct']:+.2f}%)"
            ax2.text(0.98, 0.92, label, transform=ax2.transAxes, ha="right", va="top",
                      fontsize=24, color=COLOR_ACCENT_GOLD, weight="bold")

        short_title = self._extract_title(text, max_chars=20)
        ax2.set_title(short_title, color=COLOR_TEXT, fontsize=28, pad=20, weight="bold")
        ax2.tick_params(colors=COLOR_TEXT, labelsize=14)
        ax2.grid(color=COLOR_GRID, alpha=0.3)
        for spine in ax2.spines.values():
            spine.set_color(COLOR_GRID)

        plt.tight_layout()
        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 핵심 데이터: 캔들스틱 스타일 차트 ──
    def _render_candlestick(self, text, img_path, plt):
        import numpy as np
        signal = _extract_market_signal(text)

        fig, ax2 = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)

        ax2.set_facecolor(COLOR_BG2)
        n = 20
        if signal["direction"] == "up":
            drift = abs(np.random.randn()) * 2 + 1.0
        elif signal["direction"] == "down":
            drift = -(abs(np.random.randn()) * 2 + 1.0)
        else:
            drift = 0
        opens = np.cumsum(np.random.randn(n) * 5 + drift) + 2600
        closes = opens + np.random.randn(n) * 15
        if signal["direction"] == "up":
            closes[-1] = opens[-1] + abs(np.random.randn() * 15) + 5
        elif signal["direction"] == "down":
            closes[-1] = opens[-1] - abs(np.random.randn() * 15) - 5
        highs = np.maximum(opens, closes) + np.abs(np.random.randn(n) * 5)
        lows = np.minimum(opens, closes) - np.abs(np.random.randn(n) * 5)

        for i in range(n):
            color = COLOR_ACCENT_GREEN if closes[i] >= opens[i] else COLOR_ACCENT_RED
            ax2.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1.5)
            ax2.add_patch(plt.Rectangle(
                (i - 0.35, min(opens[i], closes[i])), 0.7, abs(closes[i] - opens[i]),
                color=color
            ))

        if signal["value"]:
            label = signal["value"]
            if signal["pct"] is not None:
                label += f" ({signal['pct']:+.2f}%)"
            ax2.text(0.98, 0.92, label, transform=ax2.transAxes, ha="right", va="top",
                      fontsize=24, color=COLOR_ACCENT_GOLD, weight="bold")

        short_title = self._extract_title(text, max_chars=20)
        ax2.set_title(short_title, color=COLOR_TEXT, fontsize=28, pad=20, weight="bold")
        ax2.tick_params(colors=COLOR_TEXT, labelsize=14)
        ax2.grid(color=COLOR_GRID, alpha=0.3)
        for spine in ax2.spines.values():
            spine.set_color(COLOR_GRID)

        plt.tight_layout()
        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 시나리오: 상승/하락 분기 ──
    def _render_scenario_split(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)

        short_title = self._extract_title(text, max_chars=22)
        ax.text(5, 9.2, short_title, fontsize=26, color=COLOR_TEXT, ha="center", weight="bold")

        ax.add_patch(plt.Rectangle((0.5, 1), 4, 6.5, facecolor=COLOR_ACCENT_GREEN, alpha=0.15,
                                     edgecolor=COLOR_ACCENT_GREEN, linewidth=2))
        ax.text(2.5, 6.5, "▲ 상승 시나리오", fontsize=24, color=COLOR_ACCENT_GREEN, ha="center", weight="bold")
        ax.text(2.5, 4, "외국인 순매수 지속\n거래량 증가\n저항선 돌파", fontsize=18, color=COLOR_TEXT, ha="center")

        ax.add_patch(plt.Rectangle((5.5, 1), 4, 6.5, facecolor=COLOR_ACCENT_RED, alpha=0.15,
                                     edgecolor=COLOR_ACCENT_RED, linewidth=2))
        ax.text(7.5, 6.5, "▼ 하락 시나리오", fontsize=24, color=COLOR_ACCENT_RED, ha="center", weight="bold")
        ax.text(7.5, 4, "기관 매도 전환\n거래량 감소\n지지선 이탈", fontsize=18, color=COLOR_TEXT, ha="center")

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 실행 가이드: 체크리스트 ──
    def _render_checklist(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)

        short_title = self._extract_title(text, max_chars=22)
        ax.text(5, 9.2, short_title, fontsize=28, color=COLOR_ACCENT_GOLD, ha="center", weight="bold")

        items = ["거래량 변화 확인", "외국인·기관 매매 동향", "주요 지지·저항선", "글로벌 지수 연동성"]
        for i, item in enumerate(items):
            y = 6.5 - i * 1.5
            ax.add_patch(plt.Circle((1.5, y), 0.3, facecolor=COLOR_ACCENT_CYAN))
            ax.text(1.5, y, "✓", fontsize=20, color=COLOR_BG, ha="center", va="center", weight="bold")
            ax.text(2.5, y, item, fontsize=22, color=COLOR_TEXT, va="center")

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 결론: 요약 카드 ──
    def _render_summary_card(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        ax.set_xlim(0, 10); ax.set_ylim(0, 10)

        ax.text(5, 9.2, "오늘의 핵심 정리", fontsize=36, color=COLOR_ACCENT_GOLD, ha="center", weight="bold")

        points = ["✅ 시장 핵심 데이터 확인", "✅ 상승·하락 시나리오 분석", "✅ 다음 영상도 구독하세요!"]
        for i, pt in enumerate(points):
            y = 6.0 - i * 1.8
            ax.text(5, y, pt, fontsize=26, color=COLOR_TEXT, ha="center", va="center", weight="bold")

        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    # ── 폴백: 단색 배경 ──
    def _render_fallback(self, text, img_path, plt):
        fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor(COLOR_BG)
        ax.set_facecolor(COLOR_BG)
        ax.axis("off")
        wrapped = self._wrap_text(text, 20)
        ax.text(0.5, 0.5, wrapped, fontsize=28, color=COLOR_TEXT, ha="center", va="center",
                transform=ax.transAxes)
        plt.savefig(img_path, facecolor=COLOR_BG, bbox_inches="tight")
        plt.close(fig)

    @staticmethod
    def _extract_title(text: str, max_chars: int = 20) -> str:
        """텍스트에서 첫 문장(또는 첫 max_chars자)만 추출하여 제목으로 사용"""
        import re
        if not text:
            return ""
        first_sent = re.split(r'(?<=[다요죠네.!?])\s', text.strip())[0]
        first_sent = first_sent.strip()
        if len(first_sent) <= max_chars:
            return first_sent
        return first_sent[:max_chars] + "…"

    @staticmethod
    def _wrap_text(text: str, width: int) -> str:
        import textwrap
        return "\n".join(textwrap.wrap(text, width=width))

    def _apply_chart_only(self, scene: dict, img_path: str):
        if scene.get("section") == "data":
            from app.utils.market_charts import extract_market_chart
            from PIL import Image
            chart_data = extract_market_chart(scene)
            if chart_data:
                # 데이터가 확보된 씬에서만 패널을 정리한다.
                self._check_panel_blank_qc(img_path)
                
                pie = chart_data.get("market_cap_pie", [])
                points = chart_data.get("points", [])
                
                payload = {
                    "title": chart_data.get("label", "주요 지표"),
                    "as_of": chart_data.get("source_date", "2026-07-20"),
                    "unit": "%" if pie else "pt",
                }
                if pie:
                    payload["type"] = "donut"
                    payload["items"] = [{"name": item["label"], "value": item["value"]} for item in pie]
                elif len(points) >= 5:
                    payload["type"] = "line_trend"
                    payload["items"] = [{"name": item["date"], "value": item["close"]} for item in points]
                else:
                    payload["type"] = "big_number"
                    payload["value_str"] = f"{chart_data.get('latest', 0):,}"
                    payload["change"] = "up" if chart_data.get("change_pct", 0) >= 0 else "down"
                    payload["change_value"] = f"{abs(chart_data.get('change_pct', 0))}%"
                
                try:
                    overlay_img = render_chart_to_overlay(payload)
                    base_img = Image.open(img_path).convert("RGBA")
                    
                    if base_img.size != overlay_img.size:
                        logger.warning("overlay size mismatch %s vs %s — resizing base",
                                       base_img.size, overlay_img.size)
                        base_img = base_img.resize(overlay_img.size, Image.Resampling.LANCZOS)
                        
                    composited = Image.alpha_composite(base_img, overlay_img)
                    composited.convert("RGB").save(img_path, "JPEG")
                    logger.info(f"Data chart baked into image: {img_path}")
                except Exception as ex:
                    logger.error(f"Failed to render/composite data chart: {ex}")

    def _apply_bubble_only(self, scene: dict, img_path: str):
        bubble_text = scene.get("bubble_text")
        if bubble_text:
            side = "left" if scene.get("market_chart") else "right"
            try:
                draw_speech_bubble(img_path, bubble_text, img_path, character_side=side)
            except TypeError:
                draw_speech_bubble(img_path, bubble_text, img_path)  # 구버전 시그니처 호환
            except Exception as ex:
                logger.error(f"Failed to draw speech bubble: {ex}")

    def _apply_image_overlays(self, scene: dict, img_path: str):
        """Normalize the generated still before final video composition.

        Verified charts, speech bubbles, and subtitles deliberately belong to
        ``LongformWorker``.  Putting factual text into this image would expose
        it to image-to-video distortion and duplicate the later overlay.
        """
        self._normalize_canvas(img_path)

    def _check_panel_blank_qc(self, img_path: str):
        """
        패널 영역(우측 960, 120, 1800, 960)의 픽셀 표준편차를 분석합니다.
        AI 모델이 빈 패널에 글자나 선을 마음대로 그렸을 경우,
        안전하게 Pillow 단색 cream 패널로 강제 덮어쓰기 폴백을 처리합니다.
        """
        try:
            from PIL import Image, ImageStat
            img = Image.open(img_path)
            # Crop the panel area
            panel_crop = img.crop((960, 120, 1800, 960)).convert("L")
            stat = ImageStat.Stat(panel_crop)
            stddev = stat.stddev[0]
            logger.info(f"Panel QC stddev for {img_path}: {stddev:.2f}")
            
            # 픽셀 편차가 크다는 것은(임계값 18.0 초과) 디테일(선, 글자 등)이 채워져 있음을 의미
            if stddev > 18.0:
                logger.warning(f"Panel QC failed (stddev {stddev:.2f} > 18.0). Enforcing cream background overlay.")
                from PIL import ImageDraw
                rgba_img = img.convert("RGBA")
                draw = ImageDraw.Draw(rgba_img)
                from app.services.data_chart_renderer import draw_cream_panel
                draw_cream_panel(draw)
                rgba_img.convert("RGB").save(img_path, "JPEG")
                logger.info(f"Cream panel successfully overwritten for {img_path}")
        except Exception as e:
            logger.warning(f"Failed to run Panel QC: {e}")

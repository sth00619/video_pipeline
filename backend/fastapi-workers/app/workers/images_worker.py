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
import io
import json
import hashlib
import math
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
from app.utils.art_direction import direct_scenes, plan_image_quality_tiers, compile_editorial_prompt, assess_art_diversity, flag_archetype_content_mismatch
from app.utils.scene_entity_binder import bind_scene_entities, compute_grounding_score
from app.utils.visual_qa import assess_visual_alignment
from app.utils import gemini_batch
from app.pipeline.scene_director import SceneDirector, SceneSpec
from app.providers.real.prompt_builder import build_prompt
from app.v5.scene.runtime_contract import (
    attach_v5_scene_contracts,
    is_v5_final_lane_scene,
    prompt_for_scene,
    v5_provider_options,
)
from app.v5.scene.longform_visual_mix import apply_longform_visual_mix
from app.v5.providers.gemini_provider import _load_default_references
from app.utils.budget import ProviderRequestAudit, plan_preflight, record_cost, write_preflight
from app.utils.intro_motion import infer_total_duration_seconds, select_intro_motion_scene_indices, scene_duration_seconds
from app.utils.narration_contract import build_script_contract, verify_tts_against_script_contract
from app.utils.gemini_pressure import gemini_pressure
from app.utils.image_job_lock import acquire_image_job_lock, release_image_job_lock
from app.utils.retry_policy import classify_image_error, error_signature
from app.services.info_surface.info_scene_templates import select_template

logger = logging.getLogger(__name__)


ARCHETYPE_COMPOSITION = {
    # scene_type → 구도 힌트 (무엇을 그릴지가 아니라 어떤 구도인지만)
    "character_hero":      "wide dramatic stage, character spotlight center-right",
    "news_context":        "discovery moment composition, something revealed from behind",
    "data_visual":         "control room or dashboard background, multiple screens",
    "character_explainer": "classroom or lecture hall background, pointer indicated",
    "comparison":          "split stage left vs right, two distinct zones",
    "takeaway":            "podium announcement stage, single strong focal point",
    "general":             "situational metaphor background, no specific constraints",
    "metric":              "data room atmosphere, glowing displays",
    "graph":               "trend visualization environment, flowing data streams",
    "intro":               "opening title card environment, dramatic establishing shot",
    "conclusion":          "closing summary stage, warm resolution lighting",
}

STYLE_SUFFIX = (
    "original 2D Korean finance comic, bold ink outlines, cel shading, "
    "single round gold coin mascot character only, no secondary mascot, no teal mint card mascot, no secondary people, "
    "no readable text, no letters, no words, no UI elements"
)


def _ocr_review_reasons(scenes: list[dict]) -> list[str]:
    """OCR 추정 사실은 AUTO 모드에서도 사용자 확인 없이는 확정할 수 없다."""
    reasons: list[str] = []
    for scene in scenes:
        facts = scene.get("verified_facts") or scene.get("facts") or []
        if not isinstance(facts, list):
            continue
        if any(
            isinstance(fact, dict)
            and str(fact.get("confidence") or fact.get("source_type") or fact.get("provenance") or "").lower() == "ocr_estimate"
            for fact in facts
        ):
            reasons.append(f"OCR_ESTIMATE:scene_{scene.get('index', 'unknown')}")
    return reasons


def _resolved_visual_mode(scene: dict) -> str:
    if _article_evidence_path(scene):
        return "article_evidence"
    contract = scene.get("v5_render_contract") or {}
    mode = str(scene.get("visual_mode") or contract.get("visual_mode") or "").strip()
    if mode:
        return mode
    return "archetype_explainer" if (scene.get("art_direction") or {}).get("character_required") else "semantic_illustration"


def _visual_mix_audit(scenes: list[dict]) -> dict:
    counts = Counter(_resolved_visual_mode(scene) for scene in scenes)
    total = len(scenes)
    failures: list[str] = []
    if total >= 9:
        minimum_article = max(1, math.ceil(total * 0.05))
        minimum_generated = max(1, math.ceil(total * 0.25))
        if counts["article_evidence"] < minimum_article:
            failures.append(f"article_evidence:{counts['article_evidence']}<{minimum_article}")
        for mode in ("semantic_illustration", "archetype_explainer"):
            if counts[mode] < minimum_generated:
                failures.append(f"{mode}:{counts[mode]}<{minimum_generated}")
    return {"passed": not failures, "counts": dict(counts), "failures": failures}


def _manual_review_reasons(scenes: list[dict], image_quality: dict | None = None) -> list[str]:
    """의미 검수·구성 다양성·반복도를 통과하지 못하면 자동 확정을 차단한다."""
    reasons = _ocr_review_reasons(scenes)
    for scene in scenes:
        if scene.get("retry_recommended"):
            reasons.append(f"IMAGE_RETRY_RECOMMENDED:scene_{scene.get('index', 'unknown')}")

    quality = image_quality or {}
    semantic = quality.get("semantic_alignment") or {}
    if bool(runtime_config.value("visual_qa_enabled")) and not semantic.get("reviewed"):
        reasons.append("VISUAL_QA_UNAVAILABLE")
    expected_semantic_reviews = min(len(scenes), int(runtime_config.value("visual_qa_max_scenes")), 24)
    if bool(runtime_config.value("visual_qa_enabled")) and len(semantic.get("reviewed") or []) < expected_semantic_reviews:
        reasons.append(
            f"VISUAL_QA_INCOMPLETE:{len(semantic.get('reviewed') or [])}<{expected_semantic_reviews}"
        )
    for warning in semantic.get("warnings") or []:
        if str(warning).startswith(("visual_qa_http_", "visual_qa_error", "visual_qa_invalid_json")):
            reasons.append(f"VISUAL_QA_ERROR:{warning}")
    for warning in (quality.get("art_direction") or {}).get("warnings") or []:
        reasons.append(f"ART_DIRECTION:{warning}")
    mix = quality.get("visual_mix") or _visual_mix_audit(scenes)
    for failure in mix.get("failures") or []:
        reasons.append(f"VISUAL_MIX:{failure}")

    fingerprints = Counter(
        hashlib.sha256(str(scene.get("prompt_en") or scene.get("prompt") or "").encode("utf-8")).hexdigest()
        for scene in scenes if str(scene.get("prompt_en") or scene.get("prompt") or "").strip()
    )
    duplicate_limit = max(3, math.ceil(len(scenes) * 0.10))
    if fingerprints and max(fingerprints.values()) > duplicate_limit:
        reasons.append(f"PROMPT_LAYOUT_REPETITION:{max(fingerprints.values())}>{duplicate_limit}")
    return sorted(set(reasons))


def _apply_info_scene_template(scene: dict) -> tuple[dict, object | None]:
    """검증 payload 기반으로만 v4 장면 계약을 주입한다."""
    template = select_template(scene, scene.get("proposed_template_id"))
    if template is None:
        return scene, None
    planned = dict(scene)
    direction = dict(planned.get("art_direction") or {})
    direction.update({
        "character_placement": f"{template.character.side} third",
        "pose_asset": template.character.pose_asset,
        "fallback_pose": "present_right" if template.character.side == "left" else "present_left",
        "data_surface_kind": template.surface_kind,
        "board_side": template.board_side,
        "info_scene_template": template.template_id,
    })
    planned["art_direction"] = direction
    planned["info_scene_template"] = template.model_dump()
    return planned, template


def _diagram_spec_from_scene(scene: dict, plan):
    """검증된 구조 필드만 서사 다이어그램 입력으로 변환한다."""
    from app.services.info_surface.narrative_diagrams import DiagramItem, DiagramSpec
    chart = scene.get("market_chart") or {}
    kind = str(plan.diagram_kind or "")
    source = scene.get("stage_items") if kind == "stage_locks" else (
        scene.get("structure_items") if kind == "blueprint_callouts" else (
            chart.get("external_rates") if kind == "map_clouds" else scene.get("causal_nodes")
        )
    )
    items = []
    for raw in list(source or []):
        if not isinstance(raw, dict) or not raw.get("label") or not raw.get("source_refs"):
            continue
        items.append(DiagramItem(label=str(raw["label"]), value=str(raw["value"]) if raw.get("value") is not None else None, state=raw.get("state"), emphasis=bool(raw.get("emphasis"))))
    template = scene.get("info_scene_template") or {}
    if len(items) < int(template.get("min_items", 1)):
        raise ValueError("서사 다이어그램의 검증 항목 수가 템플릿 최소값보다 적습니다")
    title = str(scene.get("embedded_title") or chart.get("label") or scene.get("title") or "핵심 구조")
    # 서사형 다이어그램은 검증 payload의 노드·라벨만 제시한다. v3의 영문
    # 기간 의미줄을 재사용하면 보드 가장자리에서 잘려 정보 소품 문법을 해친다.
    meaning = ""
    return DiagramSpec(kind=kind, title=title, items=items, meaning_line=meaning, stamp=str(scene.get("verdict_stamp") or "") or None, seed=str(chart.get("scene_seed") or plan.scene_id))


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

    def _call_llm(self, system: str, messages: list, max_tokens: int = 200) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return resp.content[0].text

    def _build_prompt_from_narration(
        self,
        narration: str,
        scene_type: str,
        title: str,
        *,
        core_entities: list[str] | None = None,
        core_figures: list[dict] | None = None,
        fictionalized_labels: dict[str, str] | None = None,
        visual_mode: str | None = None,
        character_required: bool = True,
    ) -> str:
        """
        대사(narration)와 바인딩된 엔티티/수치를 읽고 내용에 맞는 시각 은유 배경/캐릭터 프롬프트를 LLM으로 생성한다.
        - core_entities / core_figures가 존재하면 물리적 전광판, 표지판, 소품 표면에 해당 정보가 명시적으로 반영되도록 시스템 프롬프트에 지시한다.
        - character_required=True일 경우 Goldie(금화 마스코트) 캐릭터가 전경의 1/3 크기로 명시 배치된다.
        - 매 씬마다 대사가 다르면 반드시 다른 프롬프트가 나와야 함
        """
        composition = ARCHETYPE_COMPOSITION.get(scene_type, ARCHETYPE_COMPOSITION["general"])
        is_news_mode = (visual_mode == "article_evidence") or (scene_type in ("news_context", "reporter_worried", "news_anchor"))

        if is_news_mode:
            system = (
                "You are a visual director for a Korean 2D financial animation channel. "
                "Convert Korean financial narration into a vivid 2D scene featuring the channel's Goldie (2D gold coin mascot) news reporter. "
                "The scene MUST depict the 2D gold coin mascot character standing as a financial reporter or presenter. "
                "The background features an appropriate display surface (such as a standing presentation screen, wall display board, or weather map) "
                "showing the economic figures, charts, and entity labels mentioned in the narration. "
                "Output only the prompt text, no explanation, no markdown."
            )
            char_rules = (
                "- You MUST depict the 2D gold coin mascot character (Goldie) standing in the scene.\n"
                "- Exactly ONE 2D gold coin mascot character is present. NO extra people, NO secondary mascot characters, NO cyan/green creatures.\n"
                "- The background is tailored to the scene archetype (e.g. standing reporter board, data lab display, or presentation screen)."
            )
        elif character_required and visual_mode != "background_only":
            system = (
                "You are a visual director for a Korean 2D financial animation channel. "
                "Convert Korean financial narration into a vivid English scene description featuring the channel's Goldie (2D gold coin mascot) character. "
                "The 2D gold coin mascot character stands in the foreground observing or presenting the economic situation. "
                "Output only the prompt text, no explanation, no markdown."
            )
            char_rules = (
                "- You MUST depict the 2D gold coin mascot character (Goldie) standing in the scene.\n"
                "- Exactly ONE 2D gold coin mascot character is present in the scene. NO extra people, NO secondary characters, NO green/mint creatures.\n"
                "- The character stands actively reacting to or presenting the economic situation in the scene."
            )
        else:
            system = (
                "You are a visual director for a Korean 2D financial animation channel. "
                "Convert Korean financial narration into a vivid English background scene description. "
                "Never describe characters. Only describe the background environment and symbolic objects. "
                "Output only the prompt text, no explanation, no markdown."
            )
            char_rules = "- No characters, no people, no coin character, background environment only."

        entity_instructions = ""
        if core_entities or core_figures:
            labels_str = ", ".join(
                f"{k} -> {v}" for k, v in (fictionalized_labels or {}).items()
            )
            figures_str = ", ".join(
                f"{f.get('raw')} ({f.get('kind')})" for f in (core_figures or [])
            )
            entity_instructions = (
                f"\nCRITICAL ENTITY GROUNDING INSTRUCTIONS:\n"
                f"- Core Entities: {core_entities or []}\n"
                f"- Core Figures/Metrics: {figures_str}\n"
                f"- Fictionalized Brand Labels (use these instead of real names): {labels_str}\n"
                f"- You MUST incorporate at least one visible signage, ticker board, wall screen, "
                f"or labeled physical prop representing these entities and figures in the scene.\n"
                f"- Abstract metaphor alone is insufficient; combine metaphor with concrete labeled props.\n"
                f"- Do NOT literally translate the Korean narration sentence into English and place it as a large text block on a blackboard. "
                f"Instead, use concrete physical objects and environmental signage (e.g. warning signs, shipping containers, weather maps, receipt screens) matching the reference image style pattern.\n"
            )

        user_content = f"""Korean narration: "{narration}"
Scene type: {scene_type}
Composition hint: {composition}
Visual mode: {visual_mode or "general"}
{entity_instructions}
Convert the narration's core economic situation into a physical visual scene.
Rules:
- Abstract concepts must become concrete physical objects/environments with clear entity labeling
- Each scene must be visually distinct. Never repeat the same background.
- Do NOT translate narration sentences into large blackboard text. Use environmental props and scene-specific backgrounds.
{char_rules}
- NEVER introduce secondary lab technicians, secondary mint characters, or secondary human figures. Depict Goldie (the 2D gold coin mascot) as the ONLY character in the scene.
- Keep under 75 words.
- End with exactly: {STYLE_SUFFIX}"""

        try:
            raw = self._call_llm(system, [{"role": "user", "content": user_content}], max_tokens=250)
            cleaned = raw.strip().strip('"').strip("'")
            if (is_news_mode or character_required) and not cleaned.lower().startswith("the 2d gold coin") and not cleaned.lower().startswith("a 2d gold coin"):
                cleaned = f"The 2D gold coin mascot character (Goldie), {cleaned}"
            if STYLE_SUFFIX not in cleaned:
                cleaned = f"{cleaned}, {STYLE_SUFFIX}"
            logger.info("대사 기반 프롬프트 재생성 완료 (씬: %s): %s...", title, cleaned[:60])
            return cleaned
        except Exception as exc:
            logger.warning("대사 기반 프롬프트 재생성 실패 (씬: %s): %s", title, exc)
            return (
                f"{composition}, Korean financial situation, dramatic lighting, "
                f"{STYLE_SUFFIX}"
            )

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
                 lora_scale: float = 1.0, autonomy_mode: str | None = None,
                 budget_limit_krw: int | None = None, budget_policy_version: str | None = None) -> dict:
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
                autonomy_mode=autonomy_mode,
                budget_limit_krw=budget_limit_krw, budget_policy_version=budget_policy_version,
            )
        finally:
            release_image_job_lock(job_id, lock_token)

    def _generate(self, scenes_meta: list = None, job_id: int = 0,
                  tts_meta_json: str = None, script_meta_json: str = None,
                  character_image_path: str = None, character_style_prompt: str = None,
                  character_poses_dir: str = None,
                  lora_model_id: str = None, lora_trigger_word: str = None,
                  lora_scale: float = 1.0, autonomy_mode: str | None = None,
                  budget_limit_krw: int | None = None, budget_policy_version: str | None = None) -> dict:
        market_snapshot = {}
        self.market_snapshot = {}
        self.evidence_audit = {}
        self.visual_mix_plan: dict = {}
        self.tts_subtitle_sync: dict = {"passed": None, "reason": "tts_metadata_not_supplied"}
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

        # 기존 이미지 생성 경로는 유지한다. 다만 TTS 메타데이터가 함께 온
        # 정상 롱폼 경로에서는 이미지가 다른 대본에서 출발하지 않았는지 먼저 막는다.
        if tts_meta_json and script_data:
            try:
                tts_data = json.loads(tts_meta_json)
                if isinstance(tts_data, str):
                    tts_data = json.loads(tts_data)
                contract = script_data.get("narration_contract") or build_script_contract(
                    str(script_data.get("script") or ""),
                    list(script_data.get("sections") or script_data.get("scenes") or []),
                )
                verify_tts_against_script_contract(tts_data, contract)
            except Exception as exc:
                raise RuntimeError(f"이미지 단계 대본·TTS·자막 계보 검증 실패: {exc}") from exc

        if not scenes_meta:
            scenes_meta = []
        still_image_pilot = bool(script_data.get("still_image_pilot"))
        if still_image_pilot:
            test_budget_limit = int(runtime_config.value("gemini_test_image_budget_krw"))
            if test_budget_limit <= 0:
                raise RuntimeError("정지 이미지 파일럿 예산은 0원보다 커야 합니다.")
            budget_limit_krw = min(
                test_budget_limit,
                int(budget_limit_krw) if budget_limit_krw is not None else test_budget_limit,
            )

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

        # 기사 캡처가 확정된 뒤에만 전체 대본의 장면 계보를 세 유형으로
        # 배정한다. 원문·TTS 문장·장면 순서는 바꾸지 않는다.
        if scenes_meta and not still_image_pilot:
            scenes_meta, self.visual_mix_plan = apply_longform_visual_mix(scenes_meta)

        # V5 visual_mode를 먼저 확정해야 기사형·상황형 장면에 마스코트를
        # 강제로 넣는 기존 art-direction 계약을 피할 수 있다.
        if scenes_meta and all(scene.get("scene_type") for scene in scenes_meta):
            scenes_meta = attach_v5_scene_contracts(scenes_meta)
        if scenes_meta and not all(scene.get("art_direction") for scene in scenes_meta):
            scenes_meta = direct_scenes([
                enrich_scene_plan(scene, i, len(scenes_meta))
                for i, scene in enumerate(scenes_meta)
            ])
        # Stage 1 + Stage 3: Bind entities & figures for all scenes
        verified_facts = list(script_data.get("verified_facts") or [])
        keyword_news = list(script_data.get("keyword_news") or script_data.get("articles") or [])
        entity_bindings = bind_scene_entities(scenes_meta, verified_facts, keyword_news)
        binding_map = {str(b.scene_id): b for b in entity_bindings}
        binding_by_index = {b.scene_index: b for b in entity_bindings}
        # ScriptWorker가 이미 확정한 scene_type을 운영 이미지 경로까지
        # 보존한다. 이 단계는 순수 계획만 만들며 이미지 API를 호출하지 않는다.
        visual_mix_preflight = _visual_mix_audit(scenes_meta)
        if not still_image_pilot and scenes_meta and not visual_mix_preflight["passed"]:
            logger.warning(
                "IMAGE_MIX_PREFLIGHT_WARNING: 기사형·상황형·정보형 구성 비율 경고 (이미지 생성 계속 진행): "
                + ", ".join(visual_mix_preflight["failures"])
            )
        budget_preflight = None
        if scenes_meta:
            billable_scenes = [scene for scene in scenes_meta if not _article_evidence_path(scene)]
            # 재개 실행에서는 이미 검증되어 저장된 PNG를 다시 생성하거나 비용에
            # 포함하지 않는다. Kling은 아직 생성하지 않았으므로 별도로 계속 예약한다.
            pending_billable_scenes = [
                scene for index, scene in enumerate(scenes_meta)
                if not _article_evidence_path(scene)
                and not (
                    (cached_path := Path(f"/app/data/jobs/{job_id}/images/scene_{index:03d}.png")).is_file()
                    and cached_path.stat().st_size > 15000
                )
            ]
            # 모든 Pro 요청 비용을 첫 이미지 호출 전에 확인하며, 초과 시
            # 품질을 낮추지 않고 작업 전체를 거절한다.
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
                    if still_image_pilot or not bool(runtime_config.value("intro_motion_enabled"))
                    else min(
                        2 if bool(runtime_config.value("intro_motion_test_mode")) else int(runtime_config.value("intro_motion_clip_count")),
                        int(runtime_config.value("intro_motion_clip_count")),
                    )
                ),
                clip_seconds=float(runtime_config.value("intro_motion_clip_seconds")),
            )
            template_scene_count = sum(
                1 for scene in pending_billable_scenes
                if select_template(scene, scene.get("proposed_template_id")) is not None
            )

            def make_budget_preflight(kling_count: int) -> dict:
                return plan_preflight(
                    len(pending_billable_scenes),
                    str(runtime_config.value("image_quality_tier")),
                    int(runtime_config.value("pro_image_max_scenes")),
                    kling_count,
                    template_scene_count=template_scene_count,
                    # 썸네일은 본편의 사람 검수·승인 뒤에 별도 단계로 만든다.
                    # 이미지 생성 단계에서 비용을 예약하거나 자동으로 시작하지 않는다.
                    include_thumbnail=False,
                    budget_limit_krw=budget_limit_krw,
                    policy_version=budget_policy_version,
                )

            requested_motion_count = len(intro_motion_indices)
            gemini_image_only_budget = bool(
                budget_policy_version and "gemini-image-only" in budget_policy_version
            )
            # Gemini 정지 이미지 예산에는 Fal 모션을 넣지 않는다. Fal은 이미지
            # 검수 후 조립 단계에서 선택한 장면만 별도 비용으로 실행한다.
            budget_preflight = make_budget_preflight(
                0 if gemini_image_only_budget else requested_motion_count
            )
            # 선행 단계에서 사용한 비용만큼 잔여 예산이 줄면, 본문 이미지 품질은
            # 유지하고 선택 사항인 인트로 Kling만 뒤 장면부터 축소한다.
            while (
                not gemini_image_only_budget
                and not budget_preflight["allowed"]
                and intro_motion_indices
            ):
                intro_motion_indices.remove(max(intro_motion_indices))
                budget_preflight = make_budget_preflight(len(intro_motion_indices))
            if len(intro_motion_indices) != requested_motion_count:
                budget_preflight["actions"].append(
                    "intro_motion_clips_reduced_for_remaining_budget:"
                    f"{requested_motion_count}->{len(intro_motion_indices)}"
                )
            if gemini_image_only_budget:
                budget_preflight["gemini_image_only_budget"] = True
                budget_preflight["fal_motion_clips_reserved_separately"] = requested_motion_count
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
            budget_preflight["still_image_pilot"] = still_image_pilot
            budget_preflight["resumed_scene_count"] = len(billable_scenes) - len(pending_billable_scenes)
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
                len(billable_scenes),
            )
            tiered_iter = iter(tiered_billable_scenes)
            scenes_meta = [scene if _article_evidence_path(scene) else next(tiered_iter) for scene in scenes_meta]
            # 품질 분배기가 적용된 뒤에도 V5 최종 lane의 Gemini Pro 계약은
            # 하향되지 않도록 다시 명시한다.
            if all(scene.get("scene_type") for scene in scenes_meta):
                scenes_meta = attach_v5_scene_contracts(scenes_meta)

            # ── use_kling 씬 마킹 ──────────────────────────────────────────────
            # intro_motion_indices(예산 확정 후의 최종 클립 목록)를 기반으로
            # 각 씬에 use_kling 필드를 기록한다.
            # longform_worker의 _has_manual_kling_selection()이 이 필드를 읽어
            # Kling 호출 여부를 결정한다. 필드가 하나라도 있으면 manual 선택으로
            # 인식하므로, 전체 씬에 True/False를 반드시 채워야 한다.
            # - 기사 캡처 씬: 항상 False (이미 캡처 이미지 사용)
            # - V5 검증 사실 오버레이 씬: 항상 False (수치 변형 방지)
            # - 그 외 intro_motion_indices 해당 씬: True
            _billable_idx_map = {
                orig_idx: bill_idx
                for bill_idx, orig_idx in enumerate(
                    idx for idx, s in enumerate(scenes_meta)
                    if not _article_evidence_path(s)
                )
            }
            for _scene_idx, _scene in enumerate(scenes_meta):
                if _article_evidence_path(_scene):
                    _scene["use_kling"] = False
                    continue
                _v5_overlays = _scene.get("v5_verified_overlays")
                _has_fact_overlay = isinstance(_v5_overlays, list) and bool(_v5_overlays)
                if _has_fact_overlay:
                    _scene["use_kling"] = False
                    continue
                _bill_idx = _billable_idx_map.get(_scene_idx)
                _scene["use_kling"] = (
                    _bill_idx is not None and _bill_idx in intro_motion_indices
                )
            logger.info(
                "use_kling 마킹 완료: 총 %d씬 중 %d씬 True (intro_motion_indices=%s)",
                len(scenes_meta),
                sum(1 for s in scenes_meta if s.get("use_kling")),
                sorted(intro_motion_indices),
            )

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

        # V5 최종 경로는 승인된 캐릭터·화풍 참조 2장을 같은 순서로 반드시 전달한다.
        # 단일 캐릭터 시트만 보내면서 두 번째 스타일 참조를 언급하면 계약이 모순된다.
        is_v5_final_batch = any(is_v5_final_lane_scene(scene) for scene in scenes_meta)
        selected_character_exists = bool(character_image_path and Path(character_image_path).exists())
        character_reference_paths = []
        reference_candidates = (
            [character_image_path] if selected_character_exists
            else _load_default_references()
        )
        for path in reference_candidates:
            if path and Path(path).exists() and path not in character_reference_paths:
                character_reference_paths.append(path)
        if character_reference_paths or selected_character_exists or character_poses_dir or lora_model_id:
            # When reference images/poses/LoRA are supplied, do not let
            # the provider inject its legacy generic mascot description.
            character_style_prompt = "none"

        # V3 canonical scene layers.  A pose library is the character's
        # identity lock: clean plate -> verified physical surface -> alpha
        # foreground character.  The legacy integrated path remains only for
        # old jobs without a library and is never marked identity-locked.
        use_composite = bool(character_poses_dir and Path(character_poses_dir).is_dir())
        if use_composite and any(is_v5_final_lane_scene(scene) for scene in scenes_meta):
            # V5는 Gemini가 완성한 동일 매체의 캐릭터·무대·primary 표면을
            # 한 장으로 받는다. 기존 포즈 PNG 합성은 이 계약을 깨므로 사용하지 않는다.
            use_composite = False
            logger.info("V5 final lane: legacy pose composite를 비활성화하고 Gemini 통합 씬을 사용합니다.")
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
            scene, template = _apply_info_scene_template(scene)
            narration = scene.get("content") or scene.get("text") or ""
            spec = directed_specs.get(index)
            base_prompt = scene.get("prompt_en") or scene.get("prompt") or narration or scene.get("title") or ""
            prompt_en = (
                prompt_for_scene(scene)
                or (build_prompt(spec, scene.get("market_chart"), template) if spec else compile_editorial_prompt(scene, base_prompt))
            )
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
            # V5 운영 씬은 request 단위 가드·표준 tier·max_attempts=1을
            # 유지해야 하므로 기존 Batch 경로로 우회하지 않는다.
            and not any(is_v5_final_lane_scene(scene) for scene in scenes_meta)
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
                entity_bindings=entity_bindings,
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
            scene, template = _apply_info_scene_template(scene)
            scene["_template_regeneration_enabled"] = (
                bool((budget_preflight or {}).get("template_regeneration_enabled"))
                and not is_v5_final_lane_scene(scene)
            )
            section = scene.get("section", f"scene_{i}")
            narration = scene.get("content") or scene.get("text") or ""

            binding = binding_map.get(str(scene.get("scene_id"))) or binding_by_index.get(i)
            core_entities = binding.core_entities if binding else []
            core_figures = binding.core_figures if binding else []
            fictionalized_labels = binding.fictionalized_labels if binding else {}
            b_visual_mode = binding.suggested_visual_type if binding else (scene.get("visual_mode") or "general")

            scene["core_entities"] = core_entities
            scene["core_figures"] = core_figures
            scene["fictionalized_labels"] = fictionalized_labels

            art_direction = scene.get("art_direction") or {}
            character_required = bool(art_direction.get("character_required", True))
            spec = directed_specs.get(i)
            base_prompt = scene.get("prompt_en") or scene.get("prompt") or ""
            mismatch = flag_archetype_content_mismatch(scene)
            needs_rebuild = (
                bool(scene.get("prompt_needs_rebuild"))
                or not str(base_prompt).strip()
                or "Financial editorial scene representing" in str(base_prompt)
                or mismatch is not None
            )
            if needs_rebuild and narration:
                prompt_en = self._build_prompt_from_narration(
                    narration=narration,
                    scene_type=str(scene.get("archetype") or scene.get("scene_type") or scene.get("visual_type") or scene.get("section") or "general"),
                    title=str(scene.get("title") or f"scene_{i}"),
                    core_entities=core_entities,
                    core_figures=core_figures,
                    fictionalized_labels=fictionalized_labels,
                    visual_mode=b_visual_mode,
                    character_required=character_required,
                )
                scene["prompt_en"] = prompt_en
                scene["prompt"] = prompt_en
                scene["grounding_score_pre"] = compute_grounding_score(prompt_en, core_entities)
                logger.info("씬 '%s': 대사 기반 프롬프트로 교체됨 (이유: %s, grounding_pre: %.2f)", scene.get("title"), "아키타입 미스매치 감지" if mismatch else "폴백/빈값 트리거", scene["grounding_score_pre"])
            else:
                prompt_en = (
                    prompt_for_scene(scene)
                    or (build_prompt(spec, scene.get("market_chart"), template) if spec else compile_editorial_prompt(scene, base_prompt))
                )
            prompt_ko = scene.get("prompt_ko") or narration or scene.get("title") or ""
            pose = scene.get("pose", "neutral")
            art_direction = scene.get("art_direction") or {}
            image_profile = scene.get("image_profile") or {}
            is_v5_scene = is_v5_final_lane_scene(scene)
            provider_options = v5_provider_options(scene)
            is_direct_pro_scene = is_v5_scene or (
                image_profile.get("tier") == "pro"
                and runtime_config.value("image_provider") == "gemini"
            )
            scene_market_snapshot = scene.get("market_snapshot") or market_snapshot
            character_required = bool(art_direction.get("character_required", True))
            effective_reference_paths = character_reference_paths if character_required else []
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
                self._apply_image_overlays(scene, img_path)
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
                    if use_composite and character_required:
                        # [S2-3] 이중 레이어 합성
                        bg_path = str(job_dir / f"scene_{i:03d}_bg.png")
                        background_path = bg_path
                        self._generate_background_layer(
                            ai_provider, prompt_en, bg_path, section, pose, image_profile,
                            job_id=job_id, scene_key=f"image:{i}",
                        )
                        self._normalize_canvas(bg_path)
                        self._compose_layered_scene(
                            scene, bg_path, character_poses_dir, pose_asset, img_path, job_id,
                            fallback_pose=(scene.get("art_direction") or {}).get("fallback_pose") or pose,
                        )
                            
                    else:
                        max_retries = max(3, min(int(runtime_config.value("gemini_retry_max")), 8))
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
                                    character_image_path=effective_reference_paths[0] if effective_reference_paths else None,
                                    character_image_paths=effective_reference_paths,
                                    character_style_prompt=effective_character_style,
                                    lora_model_id=lora_model_id,
                                    lora_trigger_word=lora_trigger_word,
                                    lora_scale=lora_scale,
                                image_provider=provider_options.get("image_provider", runtime_config.value("image_provider")),
                                gemini_model=provider_options.get("gemini_model", image_profile.get("model")),
                                gemini_image_size=provider_options.get("gemini_image_size", image_profile.get("image_size")),
                                gemini_service_tier=provider_options.get("gemini_service_tier", runtime_config.value("gemini_service_tier")),
                                gemini_max_attempts=provider_options.get("gemini_max_attempts", runtime_config.value("gemini_pro_max_attempts")),
                                gemini_retry_base_seconds=runtime_config.value("gemini_pro_retry_base_seconds"),
                                gemini_request_audit=ProviderRequestAudit.for_job(
                                    job_id=job_id,
                                    scene_key=f"image:{i}",
                                    model=str(image_profile.get("model") or "gemini-3-pro-image"),
                                ),
                                style_locked=bool(spec) or bool(provider_options.get("style_locked")),
                                suppress_legacy_style_lock=bool(provider_options.get("suppress_legacy_style_lock")),
                                gemini_reference_contract_declared=bool(provider_options.get("gemini_reference_contract_declared")),
                                )
                            finally:
                                if is_direct_pro_scene:
                                    last_pro_request_finished_at = time.monotonic()
                            # [S5] AI 품질 자동 검수
                            if os.path.exists(raw_img_path) and os.path.getsize(raw_img_path) > 15000:
                                # 이미지 위 요약 헤드라인은 소품 표면 계약을 깨고
                                # ASS 자막과 중복되므로 모든 운영 경로에서 합성하지 않는다.
                                import shutil
                                shutil.copy2(raw_img_path, img_path)
                                self._apply_image_overlays(scene, img_path)
                                # v4 보드 검출 실패는 이 경로에서만 한 번 더 생성한다.
                                # 일반 제공자 재시도와 분리해 비용/manifest 의미를 보존한다.
                                if scene.pop("_template_regeneration_request", None):
                                    regen_prompt = prompt_en + " Regenerate this same template with the blank physical board much larger, unobstructed, and clearly separated from the character."
                                    ai_provider.generate_image(
                                        prompt=regen_prompt, output_path=raw_img_path, section=section, keyword=regen_prompt[:30],
                                        character_image_path=effective_reference_paths[0] if effective_reference_paths else None,
                                        character_image_paths=effective_reference_paths, character_style_prompt=effective_character_style,
                                        lora_model_id=lora_model_id, lora_trigger_word=lora_trigger_word, lora_scale=lora_scale,
                                        image_provider=runtime_config.value("image_provider"), gemini_model=image_profile.get("model"),
                                        gemini_image_size=image_profile.get("image_size"), gemini_service_tier=runtime_config.value("gemini_service_tier"),
                                        gemini_max_attempts=1, gemini_retry_base_seconds=runtime_config.value("gemini_pro_retry_base_seconds"),
                                        gemini_request_audit=ProviderRequestAudit.for_job(
                                            job_id=job_id,
                                            scene_key=f"template_regen:{i}",
                                            model=str(image_profile.get("model") or "gemini-3-pro-image"),
                                        ),
                                        style_locked=bool(spec),
                                    )
                                    self._replace_with_regenerated_surface_source(scene, raw_img_path, img_path)
                                    # ProviderRequestAudit가 이 Gemini Pro 요청을 이미 원장에
                                    # 기록한다. 여기서 다시 record_cost를 호출하면 한 요청이
                                    # 두 번 합산된다.
                                    self._apply_image_overlays(scene, img_path)
                                quality_score = 95 if lora_model_id else 90
                                break
                            else:
                                logger.warning(f"씬 {i} 이미지 품질 미달/손상 (attempt {attempt+1}/{max_retries}), 자동 재생성 시도...")
                        if quality_score == 0:
                            raise RuntimeError("최대 재시도 후에도 고품질 이미지 생성 실패")

                    # Generate variations if hold time exceeds limit
                    duration = scene_duration_seconds(scene, float(runtime_config.value("scene_duration_sec")))
                    # V5 운영 씬은 한 요청이 한 검증 단위다. 노출 길이 때문에
                    # 자동 변주 이미지를 추가 호출하지 않고, 영상 조립 단계가 시간을 처리한다.
                    max_hold = float("inf") if is_v5_scene else float(runtime_config.value("max_image_hold_seconds"))
                    if duration > max_hold:
                        import math
                        num_vars = math.ceil(duration / max_hold)
                        for v in range(1, num_vars):
                            var_img_path = str(job_dir / f"scene_{i:03d}_var_{v}.jpg")
                            var_prompt = prompt_en + f", alternate visual angle version {v}"
                            try:
                                if use_composite and character_required:
                                    var_bg_path = str(job_dir / f"scene_{i:03d}_bg_var_{v}.png")
                                    self._generate_background_layer(
                                        ai_provider, var_prompt, var_bg_path, section, pose, image_profile,
                                        job_id=job_id, scene_key=f"image:{i}:variation:{v}",
                                    )
                                    self._normalize_canvas(var_bg_path)
                                    
                                    self._compose_layered_scene(
                                        # A variation owns a distinct clean-plate source and
                                        # must not reuse the main still's detector provenance.
                                        dict(scene), var_bg_path, character_poses_dir, pose_asset, var_img_path, job_id,
                                        fallback_pose=(scene.get("art_direction") or {}).get("fallback_pose") or pose,
                                    )
                                else:
                                    var_raw_path = str(job_dir / f"scene_{i:03d}_raw_var_{v}.jpg")
                                    ai_provider.generate_image(
                                        prompt=var_prompt,
                                        output_path=var_raw_path,
                                        section=section,
                                        keyword=var_prompt[:30],
                                        character_image_path=effective_reference_paths[0] if effective_reference_paths else None,
                                        character_style_prompt=effective_character_style,
                                        lora_model_id=lora_model_id,
                                        image_provider=runtime_config.value("image_provider"),
                                        gemini_model=image_profile.get("model"),
                                        gemini_image_size=image_profile.get("image_size"),
                                        gemini_request_audit=ProviderRequestAudit.for_job(
                                            job_id=job_id,
                                            scene_key=f"image:{i}:variation:{v}",
                                            model=str(image_profile.get("model") or "gemini-3-pro-image"),
                                        ),
                                    )
                                    import shutil
                                    shutil.copy2(var_raw_path, var_img_path)
                                    self._apply_image_overlays(scene, var_img_path)
                                logger.info(f"Generated hold-time split variation {v} for scene {i} -> {var_img_path}")
                            except Exception as var_ex:
                                logger.warning(f"Failed to generate hold-time split variation {v} for scene {i}: {var_ex}. Copying original.")
                                import shutil
                                shutil.copy2(img_path, var_img_path)

                    # Gemini Pro 직접 호출은 ProviderRequestAudit가 단일 비용 원장이다.
                    generated.append({
                        **scene,
                        "index": i,
                        "section": section,
                        "image_path": img_path,
                        "background_path": background_path,
                        "clean_plate_path": background_path,
                        "asset_layout_metadata": _asset_layout_metadata(scene, background_path),
                        "generation_method": "composite" if use_composite else "pro_gemini",
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
        image_quality["visual_mix"] = _visual_mix_audit(generated)
        persist_quality_report(job_id, "images", image_quality)
        logger.info(f"이미지 생성 완료: {len(generated)}개, quality={image_quality['score']}")
        review_reasons = _manual_review_reasons(generated, image_quality)
        return {
            "job_id": job_id,
            "scenes": generated,
            "scene_count": len(generated),
            "gifs": [],
            "gif_count": 0,
            "quality_report": {"images": image_quality},
            "tts_subtitle_sync": self.tts_subtitle_sync,
            "evidence_audit": self.evidence_audit,
            "visual_mix_plan": self.visual_mix_plan,
            "requires_manual_review": bool(review_reasons),
            "review_reasons": review_reasons,
        }

    def _generate_parallel_scenes(
        self, scenes_meta, directed_specs, market_snapshot,
        character_reference_paths, character_style_prompt,
        lora_model_id, lora_trigger_word, lora_scale,
        ai_provider, job_dir, job_id, use_composite=False, character_poses_dir=None,
        budget_preflight=None, entity_bindings=None,
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
            binding_map = {str(b.scene_id): b for b in (entity_bindings or [])}
            binding_by_index = {b.scene_index: b for b in (entity_bindings or [])}
            binding = binding_map.get(str(original.get("scene_id"))) or binding_by_index.get(index)

            core_entities = binding.core_entities if binding else []
            core_figures = binding.core_figures if binding else []
            fictionalized_labels = binding.fictionalized_labels if binding else {}
            b_visual_mode = binding.suggested_visual_type if binding else (original.get("visual_mode") or "general")

            scene = enrich_scene_plan(original, index, len(scenes_meta))
            scene["core_entities"] = core_entities
            scene["core_figures"] = core_figures
            scene["fictionalized_labels"] = fictionalized_labels

            scene, template = _apply_info_scene_template(scene)
            scene["_template_regeneration_enabled"] = (
                bool((budget_preflight or {}).get("template_regeneration_enabled"))
                and not is_v5_final_lane_scene(scene)
            )
            narration = scene.get("content") or scene.get("text") or ""
            art_direction = scene.get("art_direction") or {}
            character_required = bool(art_direction.get("character_required", True))
            spec = directed_specs.get(index)
            base_prompt = scene.get("prompt_en") or scene.get("prompt") or ""
            mismatch = flag_archetype_content_mismatch(scene)
            needs_rebuild = (
                bool(scene.get("prompt_needs_rebuild"))
                or not str(base_prompt).strip()
                or "Financial editorial scene representing" in str(base_prompt)
                or mismatch is not None
            )
            if needs_rebuild and narration:
                prompt_en = self._build_prompt_from_narration(
                    narration=narration,
                    scene_type=str(scene.get("archetype") or scene.get("scene_type") or scene.get("visual_type") or scene.get("section") or "general"),
                    title=str(scene.get("title") or f"scene_{index}"),
                    core_entities=core_entities,
                    core_figures=core_figures,
                    fictionalized_labels=fictionalized_labels,
                    visual_mode=b_visual_mode,
                    character_required=character_required,
                )
                scene["prompt_en"] = prompt_en
                scene["prompt"] = prompt_en
                scene["grounding_score_pre"] = compute_grounding_score(prompt_en, core_entities)
                logger.info("씬 '%s': 대사 기반 프롬프트로 교체됨 (이유: %s, grounding_pre: %.2f)", scene.get("title"), "아키타입 미스매치 감지" if mismatch else "폴백/빈값 트리거", scene["grounding_score_pre"])
            else:
                prompt_en = (
                    prompt_for_scene(scene)
                    or (build_prompt(spec, scene.get("market_chart"), template) if spec else compile_editorial_prompt(scene, base_prompt))
                )
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
                "v5_provider_options": v5_provider_options(scene),
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
            provider_options = ctx.get("v5_provider_options") or {}

            # 씬 유형 -> 아키타입 기본 구도 주입 및 프롬프트 검증
            SCENE_TYPE_TO_ARCHETYPE = {
                "character_hero": "briefing podium on stage, spotlight, financial presenter at center",
                "news_context": "retail shock market backdrop, news event setting, breaking news headline banner",
                "data_visual": "risk control room, glowing financial chart monitors and data screens",
                "character_explainer": "classroom chalkboard, conceptual financial explanation backdrop",
                "comparison": "trade calculator, giant golden balance scale stage with market weights",
                "takeaway": "briefing podium, illuminated presentation stage",
            }
            prompt_en = ctx.get("prompt_en", "")
            if not prompt_en or "Financial editorial scene representing 장면" in prompt_en or "Financial editorial scene representing" in prompt_en:
                logger.warning("scene %s has generic or empty prompt_en; applying archetype mapping & keyword visual metaphors", index)
                scene_type = ctx.get("visual_type") or ctx.get("section") or "character_hero"
                archetype_setting = SCENE_TYPE_TO_ARCHETYPE.get(scene_type, "briefing podium on stage, spotlight")
                narration_text = ctx.get("text") or ctx.get("prompt_ko") or ""
                
                metaphors = []
                if any(k in narration_text for k in ["패닉", "무너졌", "폭락", "급락"]):
                    metaphors.append("dark stormy market chaos with red falling arrows")
                elif any(k in narration_text for k in ["반등", "회복", "만회"]):
                    metaphors.append("golden recovery arc rising dramatically from cliff edge")
                elif any(k in narration_text for k in ["저울", "비교", "대비"]):
                    metaphors.append("giant golden balance scale with two glowing market orbs")
                elif any(k in narration_text for k in ["반도체", "amd", "실적"]):
                    metaphors.append("glowing semiconductor chip facility and circuit pathways")
                elif any(k in narration_text for k in ["금리"]):
                    metaphors.append("massive interest rate dial and financial gauge pointing up")
                elif any(k in narration_text for k in ["지수", "포인트", "마감"]):
                    metaphors.append("giant illuminated scoreboard displaying stock market results")
                elif any(k in narration_text for k in ["전망", "방향"]):
                    metaphors.append("foggy financial crossroads with glowing directional signs")

                metaphor_str = ", ".join(metaphors) if metaphors else f"editorial financial visualization for {narration_text[:30]}"
                prompt_en = f"{archetype_setting}, {metaphor_str}, dark navy tone, original 2D Korean comic, bold ink outlines, cel shading, no readable text, no letters"
                ctx["prompt_en"] = prompt_en

            character_required = bool(ctx["art_direction"].get("character_required", True))
            effective_reference_paths = character_reference_paths if character_required else []
            tier = image_profile.get("tier", "pro")
            scene_fingerprint = fingerprint(ctx)
            # Legacy files without a manifest remain resumable; once a
            # manifest exists, a changed prompt/profile forces regeneration.
            if valid_image(img_path) and (str(index) not in image_manifest or image_manifest.get(str(index)) == scene_fingerprint):
                # Validate/recreate the final composited still from its saved
                # source image on every resume entry point.
                # V5 검증 수치 오버레이는 원본 Gemini 출력 위에만 한 번 적용한다.
                # 이미 합성된 PNG에 재개 실행이 겹쳐 쓰면 값이 누적되므로, 보존한
                # raw 이미지를 먼저 복원한 뒤 최신 검증 사실을 다시 반영한다.
                if is_v5_final_lane_scene(ctx) and valid_image(raw_img_path):
                    shutil.copy2(raw_img_path, img_path)
                self._apply_image_overlays(ctx, img_path)
                resumed_clean_plate = str(job_dir / f"scene_{index:03d}_bg.png")
                if not Path(resumed_clean_plate).is_file():
                    resumed_clean_plate = None
                return {**ctx, "image_path": img_path, "clean_plate_path": resumed_clean_plate,
                        "asset_layout_metadata": _asset_layout_metadata(ctx, resumed_clean_plate),
                        "generation_method": "resumed_existing", "quality_score": 90, "_fingerprint": scene_fingerprint}

            max_retries = max(3, min(int(runtime_config.value("gemini_retry_max")), 8))
            base_backoff = max(0.5, float(runtime_config.value("gemini_pro_retry_base_seconds")))
            last_error = None
            for attempt in range(max_retries):
                if is_job_stopped(job_id):
                    raise RuntimeError(f"Job {job_id} stopped by user.")
                provider_request_started = False
                try:
                    Path(raw_img_path).unlink(missing_ok=True)
                    if use_composite and character_required:
                        bg_path = str(job_dir / f"scene_{index:03d}_bg.png")
                        background_path = bg_path
                        self._generate_background_layer(
                            ai_provider, ctx["prompt_en"], bg_path, ctx["section"], ctx["pose"], image_profile,
                            job_id=job_id, scene_key=f"image:{index}",
                        )
                        if not valid_image(bg_path):
                            raise RuntimeError("provider returned a missing, undersized, or invalid background")
                        
                        self._normalize_canvas(bg_path)
                        self._compose_layered_scene(
                            ctx, bg_path, character_poses_dir,
                            ctx["art_direction"].get("pose_asset") or ctx["pose"], img_path, job_id,
                            fallback_pose=ctx["art_direction"].get("fallback_pose") or ctx["pose"],
                        )
                            
                    else:
                        gemini_pressure.acquire()
                        provider_request_started = True
                        ai_provider.generate_image(
                            prompt=ctx["prompt_en"],
                            output_path=raw_img_path,
                            section=ctx["section"],
                            keyword=ctx["prompt_en"][:30],
                            character_image_path=effective_reference_paths[0] if effective_reference_paths else None,
                            character_image_paths=effective_reference_paths,
                            character_style_prompt=character_style_prompt if character_required else "none",
                            lora_model_id=lora_model_id,
                            lora_trigger_word=lora_trigger_word,
                            lora_scale=lora_scale,
                            image_provider=provider_options.get("image_provider", runtime_config.value("image_provider")),
                            gemini_model=provider_options.get("gemini_model", image_profile.get("model")),
                            gemini_image_size=provider_options.get("gemini_image_size", image_profile.get("image_size")),
                            gemini_service_tier=provider_options.get("gemini_service_tier", runtime_config.value("gemini_service_tier")),
                            gemini_max_attempts=provider_options.get("gemini_max_attempts", 1),
                            gemini_retry_base_seconds=runtime_config.value("gemini_pro_retry_base_seconds"),
                            gemini_request_audit=ProviderRequestAudit.for_job(
                                job_id=job_id,
                                scene_key=f"image:{index}",
                                model=str(image_profile.get("model") or "gemini-3-pro-image"),
                            ),
                            style_locked=bool(ctx["spec"]) or bool(provider_options.get("style_locked")),
                            suppress_legacy_style_lock=bool(provider_options.get("suppress_legacy_style_lock")),
                            gemini_reference_contract_declared=bool(provider_options.get("gemini_reference_contract_declared")),
                        )
                        if not valid_image(raw_img_path):
                            raise RuntimeError("provider returned a missing, undersized, or invalid image")
                        gemini_pressure.outcome()
                        provider_request_started = False
                        
                        shutil.copy2(raw_img_path, img_path)
                        
                        self._apply_image_overlays(ctx, img_path)
                        if ctx.pop("_template_regeneration_request", None):
                            regen_prompt = ctx["prompt_en"] + " Regenerate this same template with the blank physical board much larger, unobstructed, and clearly separated from the character."
                            ai_provider.generate_image(
                                prompt=regen_prompt, output_path=raw_img_path, section=ctx["section"], keyword=regen_prompt[:30],
                                character_image_path=effective_reference_paths[0] if effective_reference_paths else None,
                                character_image_paths=effective_reference_paths, character_style_prompt=character_style_prompt if character_required else "none",
                                lora_model_id=lora_model_id, lora_trigger_word=lora_trigger_word, lora_scale=lora_scale,
                                image_provider=runtime_config.value("image_provider"), gemini_model=image_profile.get("model"),
                                gemini_image_size=image_profile.get("image_size"), gemini_service_tier=runtime_config.value("gemini_service_tier"),
                                gemini_max_attempts=1, gemini_retry_base_seconds=runtime_config.value("gemini_pro_retry_base_seconds"),
                                gemini_request_audit=ProviderRequestAudit.for_job(
                                    job_id=job_id,
                                    scene_key=f"template_regen:{index}",
                                    model=str(image_profile.get("model") or "gemini-3-pro-image"),
                                ),
                                style_locked=bool(ctx["spec"]),
                            )
                            self._replace_with_regenerated_surface_source(ctx, raw_img_path, img_path)
                            # 재생성 요청도 ProviderRequestAudit가 이미 기록한다.
                            self._apply_image_overlays(ctx, img_path)
                        

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
            futures = {}
            for i, ctx in enumerate(contexts):
                if i > 0:
                    time.sleep(0.8)  # 3개 동시 파이프라인 처리를 위한 최적화 딜레이 (0.8초)
                futures[pool.submit(render_one, ctx)] = ctx["index"]
            for future in as_completed(futures):
                index = futures[future]
                try:
                    result = future.result()
                    image_manifest[str(index)] = result.pop("_fingerprint", "")
                    persist_manifest()
                    # 병렬 Gemini Pro 요청의 비용은 ProviderRequestAudit가 기록한다.
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
                        # 복구 요청 역시 ProviderRequestAudit가 비용을 기록한다.
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
        image_quality["visual_mix"] = _visual_mix_audit(generated)
        persist_quality_report(job_id, "images", image_quality)
        logger.info("Parallel image generation complete: job=%s scenes=%s quality=%s", job_id, len(generated), image_quality["score"])
        review_reasons = _manual_review_reasons(generated, image_quality)
        return {
            "job_id": job_id,
            "scenes": generated,
            "scene_count": len(generated),
            "gifs": [],
            "gif_count": 0,
            "quality_report": {"images": image_quality},
            "tts_subtitle_sync": self.tts_subtitle_sync,
            "budget_preflight": budget_preflight,
            "evidence_audit": self.evidence_audit,
            "visual_mix_plan": self.visual_mix_plan,
            "requires_manual_review": bool(review_reasons),
            "review_reasons": review_reasons,
        }

    # ============================
    # [S2-3] 배경 레이어 생성
    # ============================
    def _generate_background_layer(self, ai_provider, prompt_en: str, bg_path: str,
                                    section: str, pose: str, image_profile: dict | None = None,
                                    *, job_id: int = 0, scene_key: str = "background:unknown"):
        """
        캐릭터 없는 순수 배경 이미지 생성.
        character_style_prompt="background_only" 를 전달해 캐릭터 주입을 차단.
        """
        gemini_pressure.acquire()
        try:
            ai_provider.generate_image(
            prompt=(
                f"{prompt_en} "
                "CLEAN PLATE REQUIREMENT: render the illustrated location and the physical blank information prop only. "
                "No mascot, no person, no face, no arms, no hands, no fingers, no pointer, and no character silhouette. "
                "A separately composited canonical foreground character will occupy the planned character side."
            ),
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
            gemini_request_audit=ProviderRequestAudit.for_job(
                job_id=job_id,
                scene_key=scene_key,
                model=str((image_profile or {}).get("model") or "gemini-3-pro-image"),
            ),
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
        from app.services.scene_layers import compose_character_foreground

        placement = "left third" if x_ratio <= 0.10 else "right third"
        try:
            metadata = compose_character_foreground(
                bg_path, poses_dir, pose, output_path,
                fallback_pose=fallback_pose,
                placement=placement,
            )
            logger.info("[합성] alpha foreground 완료: %s", output_path)
            return metadata
        except Exception as exc:
            # Do not silently produce a different, model-generated character.
            # The clean plate remains usable, but the caller can record that
            # the canonical foreground layer was unavailable.
            logger.error("[합성] canonical foreground failed, using clean plate: %s", exc)
            import shutil
            shutil.copy2(bg_path, output_path)
            return None

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
        # v4 템플릿 장면은 검출한 보드에 직접 워프한다. 레거시 크림 패널
        # 정리 함수가 호출되면 안 된다.
        if scene.get("info_scene_template"):
            return
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

    def _apply_image_overlays(self, scene: dict, img_path: str):
        """Finalize a still before any Ken Burns/video composition.

        A verified data visual is written into its detected physical prop here
        so the entire image moves together. Longform must never add a fixed
        coordinate chart over a moving background.
        """
        from app.services.scene_layers import load_layer_manifest

        # Resume must rebuild the final image from the prepared surface, not
        # write chart ink over an already-composited hand or finger.
        layered = scene.get("layered_scene") or load_layer_manifest(img_path)
        if isinstance(layered, dict) and layered.get("surface_image_path"):
            self._resume_layered_scene(scene, img_path, layered)
            self._apply_verified_fact_overlay(scene, img_path)
            return
        self._normalize_canvas(img_path)
        # V5는 이미지 모델이 만든 글자를 쓰지 않는다. 대본의 짧은 문구만
        # 후처리로 합성하여 화풍과 캐릭터의 일관성을 유지한다.
        if isinstance(scene.get("v5_render_contract"), dict):
            self._apply_verified_fact_overlay(scene, img_path)
            return
        # 기존 chart warp/data-cutaway 경로는 운영 이미지 생성에서 사용하지 않는다.
        return

    def _apply_verified_fact_overlay(self, scene: dict, img_path: str) -> None:
        """검증 수치 오버레이 계획이 있는 V5 장면에만 소품 표면 텍스트를 합성한다.

        ``v5_verified_overlays``는 ``runtime_contract.attach_v5_scene_contracts``가
        이 장면이 실제로 그려진 archetype의 primary 표면 안에서만 만든 계획이다.
        여기서는 좌표·값을 가공하지 않고, 렌더 직전 마지막 검증
        (``facts_from_verified_scene``)을 통과해야만 실제로 합성한다. 검증
        실패는 조용히 삼키지 않는다: 00 문서의 "조용한 폴백 금지" 원칙에 따라
        예외를 그대로 올려 이 씬의 이미지 생성이 실패로 이어지게 한다.
        """
        overlays = scene.get("v5_verified_overlays")
        if not isinstance(overlays, list) or not overlays:
            return
        from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts

        with open(img_path, "rb") as handle:
            source_bytes = handle.read()
        with Image.open(io.BytesIO(source_bytes)) as probe:
            original_format = probe.format or "PNG"
        rendered_png = apply_verified_scene_facts(source_bytes, scene)
        with Image.open(io.BytesIO(rendered_png)) as rendered:
            if original_format in {"JPEG", "JPG"}:
                rendered.convert("RGB").save(img_path, "JPEG", quality=95)
            else:
                rendered.save(img_path, original_format)
        logger.info(
            "scene %s verified fact overlay baked: %d surface value(s) -> %s",
            scene.get("scene_id") or scene.get("id") or "?",
            len(overlays),
            img_path,
        )

    def _replace_with_regenerated_surface_source(self, scene: dict, raw_img_path: str, img_path: str) -> None:
        """재생성된 보드를 다음 검출·워프의 새 원본으로 확정한다.

        v4 보드 검출 실패 뒤 재생성하는 경우 이전 ``*_source`` 파일을 계속
        사용하면 새 보드를 검사하지 못하고 빈 패널이 최종 PNG에 남는다.
        재생성본을 최종 캔버스로 정규화한 뒤 source와 fingerprint를 함께
        교체해, 한 번만 허용된 재생성도 실제 합성 결과로 이어지게 한다.
        """
        import shutil

        shutil.copy2(raw_img_path, img_path)
        self._normalize_canvas(img_path)
        final_path = Path(img_path)
        source_path = final_path.with_name(f"{final_path.stem}_source{final_path.suffix}")
        shutil.copy2(final_path, source_path)
        scene["source_image_path"] = str(source_path)
        scene.pop("info_surface_final_fingerprint", None)
        scene.pop("info_surface_final_sha256", None)
        scene.pop("final_image_path", None)

    def _compose_layered_scene(
        self,
        scene: dict,
        background_path: str,
        poses_dir: str,
        pose_asset: str,
        output_path: str,
        job_id: int,
        *,
        fallback_pose: str | None = None,
    ) -> str:
        """Assemble `plate -> verified surface -> canonical foreground`.

        This is intentionally the only path for a pose-library scene.  The
        foreground alpha layer is placed *after* the chart warp, so a palm,
        glove, finger, or pointer cannot be painted over by a later graphic.
        """
        import shutil
        from app.services.scene_layers import write_layer_manifest

        self._normalize_canvas(background_path)
        direction = scene.get("art_direction") or {}
        if direction.get("character_required", True):
            placement_x = 0.02 if "left" in str(direction.get("character_placement") or "").lower() else CHAR_OVERLAY_X_RATIO
            metadata = self._composite_character(
                background_path, poses_dir, pose_asset, output_path, job_id,
                fallback_pose=fallback_pose,
                x_ratio=placement_x,
            )
        else:
            shutil.copy2(background_path, output_path)
            metadata = {
                "version": "3.0",
                "surface_image_path": background_path,
                "foreground_mask_path": None,
                "character_regions": [],
                "z_order": ["clean_background", "verified_info_surface", "editorial_text"],
            }
        metadata = dict(metadata or {})
        metadata.update({
            "surface_image_path": str(background_path),
            "output_path": str(output_path),
            "pose_asset": pose_asset,
            "fallback_pose": fallback_pose,
            "character_placement": direction.get("character_placement", "right third"),
        })
        metadata["manifest_path"] = write_layer_manifest(output_path, metadata)
        scene["layered_scene"] = metadata
        scene["character_regions"] = metadata.get("character_regions", [])
        plan = scene.get("info_surface_plan")
        if isinstance(plan, dict):
            plan["surface_image_path"] = str(background_path)
            plan["final_image_path"] = str(output_path)
        scene["final_image_path"] = str(output_path)
        return str(output_path)

    def _resume_layered_scene(self, scene: dict, output_path: str, layered: dict) -> str:
        """Recompose a layered still from its clean/surface plate on resume."""
        surface_path = str(layered.get("surface_image_path") or "")
        foreground_asset = str(layered.get("foreground_asset_path") or "")
        if not Path(surface_path).is_file():
            logger.warning("Layer manifest has no usable surface plate for %s", output_path)
            return output_path
        # 검증 사실은 생성 직후 V5 슬롯 renderer가 적용한다. 재개 시에는
        # 기존 합성 결과를 다시 warp하지 않아 캐릭터 영역을 보존한다.
        if foreground_asset and Path(foreground_asset).is_file():
            from app.services.scene_layers import compose_character_foreground, write_layer_manifest
            placement = str(layered.get("character_placement") or "right third")
            pose_name = Path(foreground_asset).stem
            metadata = compose_character_foreground(
                surface_path, str(Path(foreground_asset).parent), pose_name, output_path,
                fallback_pose=layered.get("fallback_pose"), placement=placement,
            )
            metadata.update({
                "surface_image_path": surface_path,
                "output_path": str(output_path),
                "pose_asset": layered.get("pose_asset") or pose_name,
                "fallback_pose": layered.get("fallback_pose"),
                "character_placement": placement,
            })
            metadata["manifest_path"] = write_layer_manifest(output_path, metadata)
            scene["layered_scene"] = metadata
            scene["character_regions"] = metadata.get("character_regions", [])
        else:
            import shutil
            shutil.copy2(surface_path, output_path)
        plan = scene.get("info_surface_plan")
        if isinstance(plan, dict):
            plan["surface_image_path"] = surface_path
            plan["final_image_path"] = str(output_path)
        scene["final_image_path"] = str(output_path)
        return str(output_path)

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

"""명시적으로 검증된 장면 표면에 승인 문구를 합성하는 선택 경로."""
from __future__ import annotations

import copy
import hashlib
import io
import os
import re
import tempfile

from PIL import Image, ImageDraw

from app.services.surface_text_manifest import (
    contract_digest, draw_text_cell, normalized_bbox, planned_text_bbox, set_manifest, validate_manifest,
    expected_cells, SEMANTIC_TEXT_POLICY,
)
from app.services.surface_binding_attestation import attest_scene_surfaces, bind_single_local_surface


_FACT_REF = re.compile(r"^(?:facts|verified_facts)\[(\d+)]$")


def _require_numeric_plan_evidence(scene: dict, item: dict) -> None:
    """수치 셀도 결정론 렌더 전에 장면 로컬 검증 사실과 정확히 연결한다."""
    from app.v5.overlay.fact_value_contract import verified_fact_contains_value

    match = _FACT_REF.fullmatch(str(item.get("source_ref") or ""))
    facts = scene.get("verified_facts")
    if match is None or not isinstance(facts, list):
        raise ValueError("수치 문구에는 장면 로컬 검증 사실 source_ref가 필요합니다.")
    index = int(match.group(1))
    if index >= len(facts) or not isinstance(facts[index], dict):
        raise ValueError("수치 문구가 존재하지 않는 검증 사실을 참조합니다.")
    if not verified_fact_contains_value(facts[index], str(item.get("text") or ""),
                                        require_structured_value_match=True):
        raise ValueError("수치 문구는 참조한 검증 사실의 완전한 값과 일치해야 합니다.")


def render_semantic_surface_text(scene: dict, image_path: str) -> None:
    """검증 전에는 원본 이미지/scene을 덮어쓰지 않는다. 공급자를 호출하지 않는다."""
    from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts
    from app.v5.overlay.korean_overlay import _load_font
    from app.services.final_frame_text_integrity import require_final_frame_text_integrity

    if scene.get("text_render_policy") != SEMANTIC_TEXT_POLICY:
        raise ValueError("의미형 문자 렌더러에는 명시적인 버전 선택이 필요합니다.")
    with open(image_path, "rb") as handle:
        source = handle.read()
    source_sha = hashlib.sha256(source).hexdigest()
    previous = scene.get("surface_text_manifest") or {}
    if previous.get("final_frame_sha256") == source_sha and previous.get("contract_sha256") == contract_digest(scene):
        scene["final_frame_text_integrity"] = require_final_frame_text_integrity(image_path, scene)
        return
    candidate = copy.deepcopy(scene)
    plan = candidate.get("screen_text_plan") or []
    bindings = candidate.get("surface_bindings") or {}
    # 승인 문구는 일반 문자 셀 또는 검증 사실의 역할 셀 중 하나로 연결돼야 한다.
    # 숫자가 screen_texts에도 있는 기존 계약을 불필요하게 중복 렌더하지 않는다.
    expected_cells(candidate)
    with Image.open(io.BytesIO(source)) as original:
        size, original_format = original.size, original.format or "PNG"
    bind_single_local_surface(image_path, candidate)
    attest_scene_surfaces(image_path, candidate)
    bindings = candidate.get("surface_bindings") or {}
    for item in plan:
        # 수치가 포함된 일반 셀도 오버레이와 같은 장면 로컬 사실 계약을 거친다.
        # 실제 그리기는 Pillow이며 이미지 모델에는 이 문자열을 전달하지 않는다.
        if any(char.isdigit() for char in item["text"]):
            _require_numeric_plan_evidence(candidate, item)
        binding = bindings.get(item.get("surface"))
        if not isinstance(binding, dict) or binding.get("image_sha256") != source_sha:
            raise ValueError("물리 표면 연결 증거가 없거나 원본 이미지가 변경됐습니다.")
        planned_text_bbox(item, binding, size)
    # 새 경로의 수치 표면도 같은 최종 원본 이미지에 승인된 연결이어야 한다.
    for overlay in candidate.get("v5_verified_overlays") or []:
        binding = bindings.get(overlay.get("surface"))
        if not isinstance(binding, dict) or binding.get("image_sha256") != source_sha:
            raise ValueError("수치 오버레이 물리 표면 연결이 승인되지 않았습니다.")
        a = normalized_bbox(binding["bbox"], size)
        b = normalized_bbox([overlay["anchor"][k] for k in ("x", "y", "width", "height")], size)
        if not (a[0] <= b[0] < b[2] <= a[2] and a[1] <= b[1] < b[3] <= a[3]):
            raise ValueError("수치 오버레이가 승인 표면 바깥에 있습니다.")
    rendered = apply_verified_scene_facts(source, candidate)
    image = Image.open(io.BytesIO(rendered)).convert("RGB")
    draw = ImageDraw.Draw(image)
    cells = list((candidate.get("surface_text_manifest") or {}).get("cells") or [])
    for index, item in enumerate(plan):
        anchor = planned_text_bbox(item, bindings[item["surface"]], size)
        l, t, r, b = anchor
        text = item["text"]
        chosen = None
        for font_size in range(min(72, max(24, (b - t) // 3)), 23, -1):
            font = _load_font(font_size)
            box = draw.textbbox((0, 0), text, font=font, stroke_width=2)
            if box[2] - box[0] + 16 <= r - l and box[3] - box[1] + 16 <= b - t:
                chosen = font, box
                break
        if chosen is None:
            raise ValueError("승인 표면에 문구를 읽을 수 있는 크기로 넣을 수 없습니다.")
        font, box = chosen
        xy = (l + (r - l - box[2] + box[0]) / 2 - box[0],
              t + (b - t - box[3] + box[1]) / 2 - box[1])
        draw_text_cell(draw, xy, text, font=font, cells=cells, cell_id=f"plan:{index}:text",
                       role="text", anchor_bbox=anchor, fill=(245, 251, 255), stroke_width=2,
                       stroke_fill=(12, 18, 28))
    set_manifest(candidate, size, cells)
    validate_manifest(candidate, size)
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(os.path.abspath(image_path)), suffix=".png", delete=False) as handle:
        temp_path = handle.name
    try:
        image.save(temp_path, original_format, **({"quality": 95} if original_format == "JPEG" else {}))
        report = require_final_frame_text_integrity(temp_path, candidate)
        with open(temp_path, "rb") as handle:
            candidate["surface_text_manifest"]["final_frame_sha256"] = hashlib.sha256(handle.read()).hexdigest()
        candidate["final_frame_text_integrity"] = report
        os.replace(temp_path, image_path)
        scene.update(candidate)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

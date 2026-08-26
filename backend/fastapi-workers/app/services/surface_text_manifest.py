"""렌더러의 실제 문자열 좌표와 승인 계약을 최종 OCR에 연결한다."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

SEMANTIC_TEXT_POLICY = "semantic_roles_v1"


def contract_digest(scene: dict) -> str:
    keys = ("text_render_policy", "screen_texts", "screen_text_validation", "screen_text_plan",
            "surface_bindings", "v5_verified_overlays", "verified_facts")
    payload = {key: scene.get(key) for key in keys}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def expected_cells(scene: dict) -> dict[str, str]:
    expected = {}
    for index, item in enumerate(scene.get("v5_verified_overlays") or []):
        roles = ["label", "value"]
        if item.get("visualization") == "upward_trend":
            roles += ["start_value", "end_value"]
        for role in roles:
            expected[f"overlay:{index}:{role}"] = str(item.get(role) or "")
    if scene.get("text_render_policy") == SEMANTIC_TEXT_POLICY:
        from app.utils.image_text_contract import build_scene_text_contract
        route = build_scene_text_contract(scene)
        planned = {item["text"] for item in route["surface_plan"]}
        if set(route["deterministic_texts"]) - planned - set(expected.values()):
            raise ValueError("승인 문구 중 문자 위치 계획에서 누락된 항목이 있습니다.")
        for index, item in enumerate(scene.get("screen_text_plan") or []):
            expected[f"plan:{index}:text"] = str(item.get("text") or "")
    return expected


def normalized_bbox(region, size) -> list[int]:
    if not isinstance(region, (list, tuple)) or len(region) != 4:
        raise ValueError("표면 bbox는 x/y/너비/높이 4개여야 합니다.")
    x, y, w, h = (float(value) for value in region)
    if not all(math.isfinite(v) for v in (x, y, w, h)) or not (
        0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x + w <= 1 and y + h <= 1
    ):
        raise ValueError("표면 bbox가 프레임 범위를 벗어났습니다.")
    return [round(x * size[0]), round(y * size[1]), round((x + w) * size[0]), round((y + h) * size[1])]


def draw_text_cell(draw, xy, text, *, font, cells, cell_id, role, anchor_bbox, **kwargs):
    """기존 글꼴·색·좌표는 그대로 쓰고 실제 잉크 bbox를 함께 기록한다."""
    draw.text(xy, text, font=font, **kwargs)
    if cells is None:
        return
    bbox = draw.textbbox(xy, text, font=font, stroke_width=kwargs.get("stroke_width", 0))
    cells.append({"id": cell_id, "role": role, "text": text,
                  "bbox": [math.floor(bbox[0]) - 2, math.floor(bbox[1]) - 2,
                           math.ceil(bbox[2]) + 2, math.ceil(bbox[3]) + 2],
                  "anchor_bbox": list(anchor_bbox), "font_size": getattr(font, "size", 0),
                  "psm_modes": [6] if "\n" in text else [6, 7]})


def set_manifest(scene: dict, size, cells: list[dict]) -> None:
    scene["surface_text_manifest"] = {
        "version": 1, "frame_size": list(size), "contract_sha256": contract_digest(scene), "cells": cells,
    }


def validate_manifest(scene: dict, size) -> list[dict[str, Any]]:
    manifest = scene.get("surface_text_manifest")
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("문자별 실제 렌더 위치 원장이 없습니다.")
    if manifest.get("frame_size") != list(size) or manifest.get("contract_sha256") != contract_digest(scene):
        raise ValueError("렌더 이후 표면·문구 계약 또는 프레임 크기가 바뀌었습니다.")
    cells = manifest.get("cells")
    expected = expected_cells(scene)
    if not isinstance(cells, list) or len(cells) != len(expected):
        raise ValueError("문자별 위치 원장의 항목이 누락되거나 중복됐습니다.")
    seen = set()
    for cell in cells:
        if not isinstance(cell, dict):
            raise ValueError("문자별 위치 원장의 항목은 객체여야 합니다.")
        key = cell.get("id")
        if not isinstance(key, str):
            raise ValueError("문자별 위치 원장에는 문자열 ID가 필요합니다.")
        if key in seen or key not in expected or cell.get("text") != expected[key] or not expected[key].strip():
            raise ValueError("문자별 위치 원장의 문구/역할이 승인 계약과 다릅니다.")
        seen.add(key)
        if key.startswith("overlay:"):
            anchor = scene["v5_verified_overlays"][int(key.split(":")[1])]["anchor"]
            region = [anchor[name] for name in ("x", "y", "width", "height")]
        else:
            item = scene["screen_text_plan"][int(key.split(":")[1])]
            region = scene["surface_bindings"][item["surface"]]["bbox"]
        anchor_bbox = normalized_bbox(region, size)
        if cell.get("anchor_bbox") != anchor_bbox:
            raise ValueError("문자 위치가 다른 표면에 연결됐습니다.")
        bbox = cell.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4 or not all(type(v) is int for v in bbox):
            raise ValueError("문자 픽셀 좌표 형식이 잘못됐습니다.")
        l, t, r, b = bbox
        if not (anchor_bbox[0] <= l < r <= anchor_bbox[2] and anchor_bbox[1] <= t < b <= anchor_bbox[3]):
            raise ValueError("문자가 승인 표면 밖에 있거나 잘렸습니다.")
        if cell.get("psm_modes") != ([6] if "\n" in expected[key] else [6, 7]):
            raise ValueError("문자 판독 모드가 계약과 다릅니다.")
    for index, cell in enumerate(cells):
        a = cell["bbox"]
        for other in cells[index + 1:]:
            b = other["bbox"]
            if max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3]):
                raise ValueError("서로 다른 승인 문구의 픽셀 영역이 겹칩니다.")
    return cells

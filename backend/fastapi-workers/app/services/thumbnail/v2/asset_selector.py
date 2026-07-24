"""Select assets by pipeline provenance before using inexpensive pixel scoring."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from .layout_planner import laplacian_variance


def scene_kind(scene: dict[str, Any]) -> str:
    return str(scene.get("scene_kind") or scene.get("visual_kind") or scene.get("generation_method") or "ai_bg")


def _score(scene: dict[str, Any]) -> float:
    path = Path(str(scene.get("image_path") or scene.get("path") or ""))
    if not path.is_file():
        return float("-inf")
    try:
        with Image.open(path) as source:
            image = source.convert("L").resize((160, 90))
            mean = ImageStat.Stat(image).mean[0]
            edge = ImageStat.Stat(image.filter(ImageFilter.FIND_EDGES)).var[0]
        sharpness = laplacian_variance(path)
        relevance = float(scene.get("thumbnail_relevance_score") or scene.get("semantic_score") or 0)
        return (
            30
            - abs(mean - 128) * .20
            + min(edge, 2200) / 65
            + min(sharpness, 480) / 8
            + min(max(relevance, 0), 100) * .35
        )
    except OSError:
        return float("-inf")


def choose(candidates: list[dict[str, Any]], template_id: str) -> dict[str, Any] | None:
    selected = choose_many(candidates, template_id, limit=1)
    return selected[0] if selected else None


def choose_many(
    candidates: list[dict[str, Any]],
    template_id: str,
    limit: int = 3,
    preferred_scene_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return a primary scene and supporting scenes already used in-video."""
    wants = {
        "article_evidence": {"article_frame", "article_scene"},
        "chart_warning": {"chart", "market_chart"},
        "mascot_headline": {"chart", "market_chart", "ai_bg", "person_composite"},
        "person_headline": {"person_composite", "person"},
        "product_earnings": {"product", "ai_bg"},
    }[template_id]
    matching = [item for item in candidates if scene_kind(item) in wants]
    preferred_ids = {id(item) for item in matching}
    preferred_scene_ids = preferred_scene_ids or set()
    ranked = []
    for item in candidates:
        scene_id = str(item.get("scene_id") or item.get("id") or item.get("index") or "")
        score = _score(item)
        if id(item) in preferred_ids:
            score += 70
        if scene_id in preferred_scene_ids:
            score += 55
        ranked.append((item, score))
    ranked = [(item, score) for item, score in ranked if math.isfinite(score)]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [item for item, _ in ranked[:max(1, min(int(limit or 1), 3))]]

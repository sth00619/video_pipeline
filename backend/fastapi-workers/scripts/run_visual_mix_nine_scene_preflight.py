#!/usr/bin/env python3
"""기사형·상황형·정보형 3장씩의 9장 롱폼 시각 혼합 테스트를 사전검증한다."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent.parent / ".env")

from app.utils.budget import plan_preflight
from app.config import GEMINI_TEST_IMAGE_BUDGET_KRW
from app.v5.scene.runtime_contract import VISUAL_MODE_CONTRACTS, attach_v5_scene_contracts


MODES = frozenset({"article_evidence", "semantic_illustration", "archetype_explainer"})


def _resolve_evidence_path(raw_path: str) -> Path:
    """호스트 캡처 자산을 컨테이너 마운트 경로에서도 안전하게 찾는다."""
    direct = Path(raw_path)
    if direct.is_file():
        return direct
    mount_root = os.getenv("EVIDENCE_CAPTURE_ROOT", "").strip()
    normalized = raw_path.replace("\\", "/")
    marker = "/app/"
    if marker in normalized:
        container_candidate = Path("/app") / normalized.split(marker, 1)[1]
        if container_candidate.is_file():
            return container_candidate
    if mount_root and marker in normalized:
        return Path(mount_root) / normalized.split(marker, 1)[1]
    return direct


def build_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    scenes = list(payload.get("scenes") or [])
    if len(scenes) != 9:
        raise ValueError("시각 혼합 테스트는 정확히 9개 장면이어야 합니다.")
    ids = [str(scene.get("scene_id") or "") for scene in scenes]
    if not all(ids) or len(set(ids)) != len(ids):
        raise ValueError("scene_id는 비어 있지 않고 서로 달라야 합니다.")
    modes = [str(scene.get("visual_mode") or "") for scene in scenes]
    if set(modes) - MODES or Counter(modes) != Counter({mode: 3 for mode in MODES}):
        raise ValueError("기사형·상황형·정보형은 각각 정확히 3개여야 합니다.")

    article_scenes = [scene for scene in scenes if scene["visual_mode"] == "article_evidence"]
    article_assets: list[dict[str, Any]] = []
    missing_article_assets: list[str] = []
    source_urls: set[str] = set()
    for scene in article_scenes:
        metadata_path = _resolve_evidence_path(str(scene.get("article_capture_json") or ""))
        if not metadata_path.is_file():
            missing_article_assets.append(str(scene["scene_id"]))
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source_url = str(metadata.get("source_url") or "")
        image_path = _resolve_evidence_path(str(metadata.get("local_path") or ""))
        if not source_url or not image_path.is_file() or source_url in source_urls:
            missing_article_assets.append(str(scene["scene_id"]))
            continue
        source_urls.add(source_url)
        article_assets.append({
            "scene_id": scene["scene_id"],
            "source_url": source_url,
            "image_path": str(image_path),
            "metadata_path": str(metadata_path),
        })

    generated = [scene for scene in scenes if scene["visual_mode"] != "article_evidence"]
    planned = attach_v5_scene_contracts(generated)
    motion_eligible_scene_ids = [
        scene["scene_id"]
        for scene in planned
        if scene["v5_render_contract"]["motion_contract"]["eligible"]
    ]
    preflight = plan_preflight(
        len(planned), "pro", 0, 0,
        include_thumbnail=False,
        budget_limit_krw=GEMINI_TEST_IMAGE_BUDGET_KRW,
    )
    return {
        "status": "ready" if not missing_article_assets else "article_assets_required",
        "mode_counts": dict(Counter(modes)),
        "article_assets": article_assets,
        "article_scenes": [
            {
                "scene_id": scene["scene_id"],
                "visual_mode": "article_evidence",
                **VISUAL_MODE_CONTRACTS["article_evidence"],
            }
            for scene in article_scenes
        ],
        "missing_article_assets": missing_article_assets,
        "gemini_image_count": len(planned),
        "gemini_budget_preflight": preflight,
        "motion_preflight": {
            "external_request_started": False,
            "requires_explicit_editor_selection": True,
            "eligible_scene_ids": motion_eligible_scene_ids,
            "blocked_scene_ids": [
                scene["scene_id"]
                for scene in planned
                if not scene["v5_render_contract"]["motion_contract"]["eligible"]
            ] + [scene["scene_id"] for scene in article_scenes],
        },
        "generated_scenes": [
            {
                "scene_id": scene["scene_id"],
                "visual_mode": scene["v5_render_contract"]["visual_mode"],
                "archetype": scene["v5_render_contract"]["selection"]["archetype"],
                "caption": (scene["v5_render_contract"].get("surface_caption") or {}).get("english"),
                "overlay_policy": scene["v5_render_contract"]["visual_mode_contract"]["overlay_policy"],
                "numeric_visual_policy": scene["v5_render_contract"]["visual_mode_contract"]["numeric_visual_policy"],
                "character_policy": scene["v5_render_contract"]["visual_mode_contract"]["character_policy"],
                "motion_contract": scene["v5_render_contract"]["motion_contract"],
            }
            for scene in planned
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = build_preflight(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

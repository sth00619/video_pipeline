"""실제 원본 프레임을 API 호출 없이 v4 합성기로 재처리한다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.services.info_surface.contracts import plan_from_scene
from app.workers.images_worker import ImagesWorker


JOB = Path("/app/data/jobs/94301")
RAW = JOB / "images" / "scene_000_raw.png"
OUT = JOB / "debug" / "vault_stages_warped.png"
REPORT = JOB / "debug" / "vault_stages_replay_manifest.json"

if not RAW.is_file():
    raise RuntimeError(f"원본 PNG가 없습니다: {RAW}")

# 이 재생성은 검출기 단위 검증용이다. 외부 API, 비용 원장 기록, 원본 변경을 하지 않는다.
scene = {
    "scene_id": "vault-stages-94301-replay",
    "claim_shape": "stages",
    "stage_items": [
        {"label": "\uac00\uc785", "state": "done", "source_refs": ["v4_live_validation.fixture"]},
        {"label": "\ubcf4\uc7a5", "state": "locked", "source_refs": ["v4_live_validation.fixture"]},
        {"label": "\uc218\ub839", "state": "locked", "emphasis": True, "source_refs": ["v4_live_validation.fixture"]},
    ],
    "market_chart": {
        "verified": True,
        "source": "v4_live_validation.fixture",
        "source_ref": "v4_live_validation.fixture",
        "source_date": "2026-07-26",
        "label": "\ud1f4\uc9c1\uc5f0\uae08 3\ub2e8\uacc4",
        "latest": 100,
        "change_pct": 2.5,
        "points": [
            {"date": "2026-07-24", "close": 96},
            {"date": "2026-07-25", "close": 98},
            {"date": "2026-07-26", "close": 100},
        ],
    },
    "source_image_path": str(RAW),
    "_template_regeneration_enabled": False,
    "_template_regeneration_attempted": True,
}

expected = plan_from_scene(scene)
if expected is None or expected.surface is None:
    raise RuntimeError("현재 v4 vault_stages 표면 계약을 만들지 못했습니다")

worker = ImagesWorker()
worker._apply_info_surface_plan(scene, str(OUT))
plan = scene.get("info_surface_plan") or {}
payload = {
    "source_png": str(RAW),
    "final_png": str(OUT),
    "api_calls": 0,
    "record_cost_calls": 0,
    "template_id": plan.get("template_id"),
    "render_mode": plan.get("render_mode"),
    "fallback_chain": plan.get("fallback_chain"),
    "render_attempts": plan.get("render_attempts"),
    "detection": plan.get("detection"),
    "surface_contract": plan.get("surface"),
    "raw_sha256": hashlib.sha256(RAW.read_bytes()).hexdigest(),
    "final_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest() if OUT.is_file() else None,
}
REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))

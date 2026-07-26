"""저장된 script_worker payload를 그대로 production 합성 메서드에 넣는다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.workers.images_worker import ImagesWorker


ROOT = Path("/app/data/jobs")
MANIFEST = ROOT / "v4_live_validation_manifest.json"
RAW = ROOT / "94301" / "images" / "scene_000_raw.png"
OUT = ROOT / "94301" / "debug" / "vault_stages_warped_original_payload.png"
REPORT = ROOT / "94301" / "debug" / "production_path_revalidation.json"

reports = json.loads(MANIFEST.read_text(encoding="utf-8"))
scene = reports[0]["scene"]
scene["source_image_path"] = str(RAW)
scene.pop("info_surface_final_fingerprint", None)
scene.pop("info_surface_final_sha256", None)
scene["_template_regeneration_enabled"] = False
scene["_template_regeneration_attempted"] = True

worker = ImagesWorker()
worker._apply_info_surface_plan(scene, str(OUT))
plan = scene.get("info_surface_plan") or {}
payload = {
    "path": "ImagesWorker._apply_info_surface_plan -> detect_surface_quad -> render_diagram -> composite_planar",
    "source_png": str(RAW),
    "final_png": str(OUT),
    "api_calls": 0,
    "record_cost_calls": 0,
    "source_stage_items": scene.get("stage_items"),
    "render_mode": plan.get("render_mode"),
    "fallback_chain": plan.get("fallback_chain"),
    "detection": plan.get("detection"),
    "chart_render_metadata": plan.get("chart_render_metadata"),
    "source_sha256": hashlib.sha256(RAW.read_bytes()).hexdigest(),
    "final_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest() if OUT.is_file() else None,
}
REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))

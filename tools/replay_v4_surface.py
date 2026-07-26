"""외부 호출 없이 저장된 v4 원본에 최신 검출·워프 계약을 재적용한다."""
from __future__ import annotations
import json
from pathlib import Path
from app.workers.images_worker import ImagesWorker

manifest = Path("/app/data/jobs/v4_live_validation_manifest.json")
reports = json.loads(manifest.read_text(encoding="utf-8"))
worker = ImagesWorker()
for report in reports:
    scene = report["scene"]
    source = scene["source_image_path"]
    worker._apply_info_surface_plan(scene, source)
    report["scene"] = scene
Path("/app/data/jobs/v4_live_validation_replay.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")

"""vault_stages의 payload 문자열과 stage_locks 슬롯을 재처리 없이 기록한다."""
from __future__ import annotations

import json
import math
from pathlib import Path

from app.services.info_surface.contracts import plan_from_scene
from app.workers.images_worker import _diagram_spec_from_scene


MANIFEST = Path("/app/data/jobs/v4_live_validation_manifest.json")
OUT = Path("/app/data/jobs/94301/debug/vault_stage_spec_diagnostic.json")

reports = json.loads(MANIFEST.read_text(encoding="utf-8"))
scene = reports[0]["scene"]
plan = plan_from_scene(scene)
if plan is None:
    raise RuntimeError("scene에서 InfoSurfacePlan을 만들 수 없습니다")
spec = _diagram_spec_from_scene(scene, plan)

# 실제 DIEGETIC_WARP manifest에 저장된 검출 quad를 사용한다.
detection = scene.get("info_surface_plan", {}).get("detection") or {
    "quad": [[1411.31, 332.93], [2240.38, 199.69], [2356.08, 919.59], [1527.01, 1052.84]]
}
quad = detection["quad"]
horizontal = max(math.dist(quad[1], quad[0]), math.dist(quad[2], quad[3]))
vertical = max(math.dist(quad[3], quad[0]), math.dist(quad[2], quad[1]))
w = max(96, int(horizontal * 1.7))
h = max(72, int(vertical * 1.7))
r = min(w, h) // 11
margin = .10
usable = w * (1 - 2 * margin)
slots = []
for i in range(4):
    cx = int(w * margin + usable * ((i % 2) * .5 + .25))
    cy = int(h * ((i // 2) * .36 + .36))
    slots.append({
        "item_index": i,
        "label": spec.items[i].label if i < len(spec.items) else None,
        "cx": cx,
        "cy": cy,
        "radius": r,
        "arc_bbox": [cx-r, cy-int(r*1.45), cx+r, cy+int(r*.1)],
        "lock_bbox": [cx-r, cy, cx+r, cy+r*2],
        "label_anchor": [cx, cy + r*2.55],
        "display_text_calls": ([
            {"text": spec.title, "xy": [w//2, int(h*.08)], "px": h//10, "role": "support", "align": "center"},
            {"text": spec.items[i].label, "xy": [cx, cy+r*2.55], "px": r//2, "role": "support", "align": "center"},
        ] if i < len(spec.items) else []),
    })

payload = {
    "source_manifest": str(MANIFEST),
    "diagram_kind": spec.kind,
    "diagram_title": spec.title,
    "stage_items_count": len(scene.get("stage_items") or []),
    "diagram_spec_items": [
        {"index": i, "label": item.label, "value": item.value, "state": item.state, "emphasis": item.emphasis}
        for i, item in enumerate(spec.items)
    ],
    "render_size": [w, h],
    "side_margin": margin,
    "slots": slots,
    "source_stage_items": scene.get("stage_items") or [],
    "reprocess_performed": False,
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))

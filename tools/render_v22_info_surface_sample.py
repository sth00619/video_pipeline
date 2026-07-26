"""Render a deterministic v2.2 composition sample from an existing scene plate.

Run inside the fastapi-workers container so its OpenCV/Pillow dependencies
match production:

    python /app/tools/render_v22_info_surface_sample.py input.png output.png

An unmarked or ambiguous plate intentionally produces a full-frame
``DATA_CUTAWAY``.  That is the expected safe result for legacy/generated
screens that already contain unverified lettering or charts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# In the repository the worker package lives below ``backend/fastapi-workers``;
# in the production container it is installed at ``/app``.
for package_root in (Path(__file__).resolve().parents[1] / "backend" / "fastapi-workers", Path("/app")):
    if (package_root / "app").is_dir():
        sys.path.insert(0, str(package_root))
        break

from app.workers.images_worker import ImagesWorker


def main(input_path: str, output_path: str) -> None:
    source = Path(input_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(source.read_bytes())
    scene = {
        "scene_id": "v22-real-sample",
        "market_chart": {
            "verified": True,
            "source": "sample_payload",
            "source_ref": "sample_payload:market-cap-comparison",
            "visual_kind": "indexed_comparison",
            "label": "시가총액 비교",
            "comparison_baseline": 100,
            "comparison_values": [
                {"label": "기준", "value": 100},
                {"label": "비교", "value": 112},
            ],
        },
        # The v2.2 marker is deliberately absent from a legacy practical
        # plate.  This exercises the deterministic chart fallback instead of
        # laying a new rectangle over model-generated screen content.
        "art_direction": {
            "surface_contract": {
                "surface_kind": "monitor",
                "geometry": "planar_quad",
                "marker_rgb": (224, 208, 174),
                "border_rgb": (72, 48, 30),
                "area_ratio_min": 0.05,
                "area_ratio_max": 0.35,
                "preferred_region": {"x": 0.42, "y": 0.06, "width": 0.52, "height": 0.70},
            },
        },
    }
    ImagesWorker()._apply_image_overlays(scene, str(output))
    print(json.dumps({
        "output": str(output),
        "mode": scene["info_surface_plan"]["render_mode"],
        "timeline_mode": scene["info_surface_plan"]["timeline_mode"],
        "source": scene["source_image_path"],
        "final_fingerprint": scene["info_surface_final_fingerprint"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: render_v22_info_surface_sample.py INPUT OUTPUT")
    main(sys.argv[1], sys.argv[2])

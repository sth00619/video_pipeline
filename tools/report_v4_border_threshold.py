"""검출 fixture의 대비 점수와 두 팔레트 충돌 임계값을 표로 기록한다."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.services.info_surface import detector


TEST_FILE = Path("/app/tests/test_info_surface_detector.py")
spec = importlib.util.spec_from_file_location("detector_fixtures", TEST_FILE)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def metal_scene():
    import cv2
    import numpy as np
    image = np.full((600, 1000, 3), (38, 35, 30), dtype=np.uint8)
    cv2.rectangle(image, (660, 100), (890, 310), (74, 93, 128), -1)
    cv2.rectangle(image, (668, 108), (882, 302), module.MARKER[::-1], -1)
    return image


def rounded_scene():
    import numpy as np
    image = np.full((600, 1000, 3), (38, 35, 30), dtype=np.uint8)
    module._rounded_rect(image, (660, 100), (890, 310), 28, (74, 93, 128))
    module._rounded_rect(image, (668, 108), (882, 302), 22, module.MARKER[::-1])
    return image


def vault_contract():
    return module.SurfaceContract(
        surface_kind="vault_panel", marker_rgb=module.MARKER, border_rgb=(7, 26, 58),
        area_ratio_min=.02, area_ratio_max=.20, preferred_side="right",
        preferred_region={"x": .60, "y": .06, "width": .34, "height": .56},
    )


fixtures = [
    ("cream_4_surface_collision", lambda: module._scene(), module._contract),
    ("cream_4_surface_texture", lambda: module._scene(texture=True), module._contract),
    ("cream_4_surface_chain", lambda: module._scene(chain=True), module._contract),
    ("cream_4_surface_antialias", lambda: module._scene(), module._contract),
    ("metal_border_hint_mismatch", metal_scene, vault_contract),
    ("rounded_physical_board", rounded_scene, vault_contract),
]

rows = []
for name, image_factory, contract_factory in fixtures:
    image = image_factory(); contract = contract_factory()
    values = {"fixture": name}
    for threshold in (.70, .65):
        detector.PALETTE_COLLISION_MIN_BORDER_CONTRAST = threshold
        detection = detector.detect_surface_quad(image, contract)
        values[f"border_match_{threshold:.2f}"] = None if detection is None else round(detection.border_match, 4)
        values[f"accepted_{threshold:.2f}"] = detection is not None
        values[f"confidence_{threshold:.2f}"] = None if detection is None else round(detection.confidence, 4)
    rows.append(values)

out = Path("/app/data/jobs/94301/debug/border_threshold_distribution.json")
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(rows, ensure_ascii=False, indent=2))

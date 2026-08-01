"""V5 파일럿 입력은 출처·사실·좌표가 모두 있을 때만 통과해야 한다."""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "validate_v5_pilot_input.py"
SPEC = importlib.util.spec_from_file_location("v5_pilot_input", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _scene(image: Path) -> dict:
    return {
        "scene_id": "pilot-01",
        "background_path": str(image),
        "verified_facts": [{
            "fact": "관세율은 15%로 확인됐다.",
            "figure": "15%",
            "source_url": "https://example.com/source",
        }],
        "v5_verified_overlays": [{
            "label": "확인 관세율",
            "value": "15%",
            "source_ref": "facts[0]",
            "anchor": {"x": .1, "y": .2, "width": .26, "height": .14, "kind": "placard"},
        }],
    }


def test_pilot_validator_accepts_provenanced_fact_and_surface(tmp_path: Path):
    image = tmp_path / "background.png"
    Image.new("RGB", (1280, 720), "#334155").save(image)
    result = MODULE.validate_payload({"scenes": [_scene(image)]})
    assert result[0]["overlay_count"] == 1


def test_pilot_validator_rejects_missing_source_url(tmp_path: Path):
    image = tmp_path / "background.png"
    Image.new("RGB", (1280, 720), "#334155").save(image)
    scene = _scene(image)
    scene["verified_facts"][0].pop("source_url")
    try:
        MODULE.validate_payload({"scenes": [scene]})
        assert False, "출처 없는 수치는 파일럿에 들어가면 안 됩니다."
    except ValueError as exc:
        assert "source_url" in str(exc)

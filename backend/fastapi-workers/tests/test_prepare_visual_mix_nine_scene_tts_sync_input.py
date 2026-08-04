import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "backend/fastapi-workers/scripts/prepare_visual_mix_nine_scene_tts_sync_input.py"
SPEC = importlib.util.spec_from_file_location("prepare_nine_scene_tts_sync", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_prepared_input_has_exactly_nine_asset_bound_narration_sections(monkeypatch, tmp_path):
    output = tmp_path / "input.json"
    monkeypatch.setattr(MODULE, "OUTPUT_PATH", output)

    assert MODULE.main() == 0

    result = json.loads(output.read_text(encoding="utf-8"))
    assert len(result["sections"]) == 9
    assert result["narration_contract"]["section_count"] == 9
    assert all(item["source_section_indexes"] for item in result["sections"])
    assert result["kling_started"] is False

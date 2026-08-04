import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "backend/fastapi-workers/scripts/run_visual_mix_nine_scene_tts_sync_preflight.py"
SPEC = importlib.util.spec_from_file_location("nine_scene_tts_sync_preflight", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_tts_sync_preflight_does_not_start_paid_or_assembly_stages(monkeypatch, tmp_path):
    output = tmp_path / "sync.json"
    monkeypatch.setattr(MODULE, "OUTPUT_PATH", output)

    assert MODULE.main() == 2

    report = output.read_text(encoding="utf-8")
    assert '"tts_api_called": false' in report
    assert '"kling_started": false' in report
    assert '"mp4_assembly_started": false' in report
    assert '"thumbnail_started": false' in report
    assert '"result": "blocked"' in report

import runpy
from pathlib import Path


def test_kling_preflight_never_invokes_external_api():
    script = Path(__file__).resolve().parent.parent / "scripts" / "run_three_goals_kling_preflight.py"
    namespace = runpy.run_path(str(script), run_name="three_goals_kling_preflight")
    result = namespace["run"]()

    assert result["mode"] == "preflight_only"
    assert result["checks"]["external_api_called"] is False
    assert result["checks"]["all_scene_metadata_reflected"] is True
    assert len(result["motion_contracts"]) == 4

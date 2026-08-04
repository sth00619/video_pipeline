import runpy
from pathlib import Path


def test_preflight_never_invokes_external_api(monkeypatch):
    script = Path(__file__).resolve().parent.parent / "scripts" / "run_three_goals_images_preflight.py"
    namespace = runpy.run_path(str(script), run_name="three_goals_preflight")
    result = namespace["run"]()
    assert result["mode"] == "preflight_only"
    assert result["scene_types"] == ["standard", "chart", "diagram", "article"]
    assert "budget_preflight" in result

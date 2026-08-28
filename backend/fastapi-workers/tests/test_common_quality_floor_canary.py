import json
from pathlib import Path

from app.workers.images_worker import IMAGE_LINEAGE_FINGERPRINT_VERSION
from scripts.run_common_quality_floor_canary import prepare_rows, validate_spec


REPO = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO / "docs/evidence/common_quality_floor_canary_20260828/common-quality-floor-canary-spec.json"


def _inputs():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    source_path = REPO / spec["source"]["path"]
    scenes = json.loads(source_path.read_text(encoding="utf-8"))
    return spec, scenes


def test_canary_spec_limits_three_diverse_sequential_single_attempts():
    spec, _ = _inputs()

    validate_spec(spec)

    auth = spec["authorization"]
    assert auth["approved_total_reserved_krw"] == 4800
    assert auth["reserved_per_scene_krw"] == 1600
    assert auth["attempts_per_scene"] == 1
    assert auth["retry_on_failure"] is False
    assert auth["stop_remaining_after_provider_failure"] is True
    assert [item["index"] for item in spec["scenes"]] == [7, 28, 36]
    assert len({item["scene_type_group"] for item in spec["scenes"]}) == 3
    assert spec["scene42_frozen_and_excluded"] is True


def test_preflight_uses_one_common_floor_with_three_distinct_scene_roles():
    spec, scenes = _inputs()

    rows = prepare_rows(spec, scenes)

    assert [row["index"] for row in rows] == [7, 28, 36]
    assert {row["quality_contract"]["version"] for row in rows} == {
        "scene-visual-quality-floor-v2"
    }
    assert len({row["quality_contract"]["scene_variables"]["wardrobe"] for row in rows}) == 3
    assert len({row["quality_contract"]["scene_variables"]["emotion"] for row in rows}) == 3
    assert len({row["quality_contract"]["scene_variables"]["action"] for row in rows}) == 3
    assert [
        row["quality_contract"]["deterministic_surface"]["max_single_surface_frame_ratio"]
        for row in rows
    ] == [0.22, 0.16, 0.16]
    assert all(row["references"][0] == spec["face_reference"] for row in rows)
    assert all(len(row["references"]) == 3 for row in rows)


def test_preflight_removes_conflicting_legacy_surface_and_wardrobe_signals():
    spec, scenes = _inputs()
    rows = prepare_rows(spec, scenes)
    by_index = {row["index"]: row for row in rows}

    assert "massive central monitor" not in by_index[7]["bounded_prompt"].lower()
    assert "bounded central monitor" in by_index[7]["bounded_prompt"].lower()
    assert "large monitor wall" not in by_index[28]["bounded_prompt"].lower()
    assert "bounded monitor wall" in by_index[28]["bounded_prompt"].lower()
    assert "industrial safety helmet" not in by_index[28]["bounded_prompt"].lower()
    assert "sharp navy market analyst jacket" in by_index[28]["bounded_prompt"].lower()
    assert "neutral analyst outfit" not in by_index[36]["bounded_prompt"].lower()
    assert "magician tailcoat" in by_index[36]["bounded_prompt"].lower()
    assert "silver" not in by_index[36]["bounded_prompt"].lower()


def test_prompt_policy_change_invalidates_legacy_image_cache():
    assert IMAGE_LINEAGE_FINGERPRINT_VERSION == 10

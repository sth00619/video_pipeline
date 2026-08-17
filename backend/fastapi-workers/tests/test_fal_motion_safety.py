from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.services.fal_motion_safety import (
    assess_fal_motion_safety,
    fal_motion_safety_is_current,
)
from app.workers.images_worker import _apply_fal_motion_safety_contract
from app.workers.longform_worker import (
    _build_kling_motion_plan,
    _should_request_kling_for_scene,
)


def _png(tmp_path: Path, name: str = "scene.png") -> Path:
    path = tmp_path / name
    Image.new("RGB", (32, 32), "white").save(path)
    return path


@pytest.mark.parametrize(
    ("field", "payload", "reason"),
    [
        ("core_figures", [{"value": "6,813"}], "core_figures"),
        ("market_chart", {"series": [1, 2]}, "market_chart"),
        ("v5_verified_overlays", [{"value": "+3.56%"}], "v5_verified_overlays"),
        ("info_surface_plan", {"template": "rank"}, "info_surface_plan"),
    ],
)
def test_factual_surface_metadata_blocks_fal(tmp_path, field, payload, reason):
    result = assess_fal_motion_safety(
        {field: payload},
        str(_png(tmp_path)),
        ocr_rows=[],
    )

    assert result["eligible"] is False
    assert reason in result["reasons"]
    assert result["ocr"]["status"] == "skipped_metadata_block"


def test_textless_character_scene_is_eligible(tmp_path):
    result = assess_fal_motion_safety(
        {"character_required": True},
        str(_png(tmp_path)),
        ocr_rows=[],
    )

    assert result["eligible"] is True
    assert result["motion_target"] == "character"


def test_textless_physical_prop_scene_is_eligible(tmp_path):
    result = assess_fal_motion_safety(
        {"character_required": False},
        str(_png(tmp_path)),
        ocr_rows=[],
    )

    assert result["eligible"] is True
    assert result["motion_target"] == "non_text_prop"


@pytest.mark.parametrize(
    "row",
    [
        {"text": "6,813", "conf": "40"},
        {"text": "KOSPI", "conf": "90"},
        {"text": "램메모리", "conf": "90"},
    ],
)
def test_visible_text_or_number_blocks_fal(tmp_path, row):
    result = assess_fal_motion_safety(
        {},
        str(_png(tmp_path)),
        ocr_rows=[row],
    )

    assert result["eligible"] is False
    assert result["reasons"] == ["visible_text_or_number"]
    assert result["ocr"]["visible_tokens"] == [row["text"]]


def test_short_low_confidence_ocr_noise_is_ignored(tmp_path):
    result = assess_fal_motion_safety(
        {},
        str(_png(tmp_path)),
        ocr_rows=[
            {"text": "—", "conf": "95"},
            {"text": "A", "conf": "95"},
            {"text": "RAM", "conf": "50"},
            {"text": "7", "conf": "20"},
        ],
    )

    assert result["eligible"] is True


def test_ocr_unavailable_fails_closed(tmp_path):
    with patch("app.services.fal_motion_safety.shutil.which", return_value=None):
        result = assess_fal_motion_safety({}, str(_png(tmp_path)))

    assert result["eligible"] is False
    assert result["reasons"] == ["ocr_unavailable"]


def test_cached_safety_is_bound_to_the_exact_final_png(tmp_path):
    image = _png(tmp_path)
    scene = {}
    scene["fal_motion_safety"] = assess_fal_motion_safety(
        scene,
        str(image),
        ocr_rows=[],
    )

    assert fal_motion_safety_is_current(scene, str(image)) is True
    image.write_bytes(image.read_bytes() + b"changed")
    assert fal_motion_safety_is_current(scene, str(image)) is False


@pytest.mark.parametrize("field", ["core_figures", "market_chart"])
def test_manual_motion_selection_cannot_bypass_factual_surface(field):
    scene = {
        "use_kling": True,
        "motion_contract": {"eligible": True, "requires_explicit_selection": True},
        field: {"value": "100"},
    }

    assert _should_request_kling_for_scene(
        scene,
        selected_for_intro_motion=True,
        has_manual_kling_selection=True,
    ) is False


def test_image_stage_turns_selected_factual_scene_static(tmp_path):
    scene = {
        "index": 0,
        "image_path": str(_png(tmp_path)),
        "use_kling": True,
        "core_figures": [{"value": "6,813"}],
    }

    audit = _apply_fal_motion_safety_contract([scene])

    assert audit == {"selected": 1, "blocked": 1, "eligible": 0}
    assert scene["use_kling"] is False
    assert scene["fal_motion_safety"]["reasons"] == ["core_figures"]


def test_motion_plan_records_candidates_removed_by_text_number_gate():
    plan = _build_kling_motion_plan(
        scenes=[{"duration": 5}, {"duration": 5}],
        total_duration=10,
        target_seconds=10,
        selected_seconds=5,
        candidate_indices={0, 1},
        selected_indices={1},
        requested_indices={1},
        protected_fact_indices={0},
        protected_motion_indices={0},
        motion_block_reasons={0: ["visible_text_or_number"]},
        clip_modes={0: "static", 1: "kling"},
        failures={},
        has_manual_selection=False,
    )

    assert plan["candidate_scene_indices"] == [0, 1]
    assert plan["selected_scene_indices"] == [1]
    assert plan["protected_verified_fact_scene_indices"] == [0]
    assert plan["protected_text_number_scene_indices"] == [0]
    assert plan["motion_block_reasons"] == {"0": ["visible_text_or_number"]}

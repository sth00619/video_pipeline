import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.services.fal_motion_safety import (
    _targeted_exact_text_retry,
    assess_fal_motion_safety,
    fal_motion_safety_is_current,
    inspect_visible_text,
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
        ("screen_texts", ["삼성전자", "110조 원"], "screen_texts"),
        ("screen_text_plan", {"approved": ["코스피"]}, "screen_text_plan"),
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


def test_visual_qa_text_blocks_fal_when_local_ocr_misses_it(tmp_path):
    scene = {
        "visual_qa_review": {
            "raw": {"visible_texts": ["STOCK CERTIFICATE"]},
        },
    }

    result = assess_fal_motion_safety(scene, str(_png(tmp_path)), ocr_rows=[])

    assert result["eligible"] is False
    assert "visual_qa_visible_text" in result["reasons"]
    assert result["ocr"]["status"] == "skipped_metadata_block"


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


def test_digit_like_geometry_requires_second_ocr_mode_confirmation(tmp_path):
    primary = ({
        "text": "1111", "conf": "76", "left": "880", "top": "290",
        "width": "55", "height": "24",
    },)
    with patch(
        "app.services.fal_motion_safety._read_tesseract_rows",
        side_effect=[("completed", list(primary)), ("completed", [])],
    ):
        result = inspect_visible_text(str(_png(tmp_path)))

    assert result["visible_tokens"] == []
    assert result["numeric_confirmation_status"] == "completed"


def test_real_digit_is_kept_when_second_ocr_mode_confirms_same_location(tmp_path):
    primary = [{
        "text": "6813", "conf": "76", "left": "100", "top": "80",
        "width": "80", "height": "30",
    }]
    confirmation = [{
        "text": "6813", "conf": "88", "left": "96", "top": "76",
        "width": "90", "height": "38",
    }]
    with patch(
        "app.services.fal_motion_safety._read_tesseract_rows",
        side_effect=[("completed", primary), ("completed", confirmation)],
    ):
        result = inspect_visible_text(str(_png(tmp_path)))

    assert result["visible_tokens"] == ["6813"]


def test_surface_occurrences_count_distinct_panels_not_scan_variants(tmp_path):
    evidence = [
        {"candidate_index": 1, "variant": "upper", "texts": ["엇갈림"]},
        {"candidate_index": 1, "variant": "tight_interior", "texts": ["엇갈림"]},
        {"candidate_index": 3, "variant": "tight_interior", "texts": ["엇갈림"]},
    ]
    rows = [
        {"text": "엇갈림", "conf": "96", "surface_scan": "1:upper:7"},
        {"text": "엇갈림", "conf": "96", "surface_scan": "3:tight_interior:7"},
    ]
    with patch(
        "app.services.fal_motion_safety._read_tesseract_rows",
        return_value=("completed", []),
    ), patch(
        "app.services.fal_motion_safety._read_tesseract_surface_rows",
        return_value=("completed", rows, evidence),
    ):
        result = inspect_visible_text(
            str(_png(tmp_path)), expected_texts=["엇갈림"], surface_text_recall=True,
        )

    assert result["surface_occurrence_counts"] == {"엇갈림": 2}


def test_different_digits_at_same_location_are_not_numeric_confirmation(tmp_path):
    primary = [{
        "text": "09", "conf": "69", "left": "720", "top": "72",
        "width": "32", "height": "16",
    }]
    confirmation = [{
        "text": "7)", "conf": "44", "left": "730", "top": "53",
        "width": "37", "height": "22",
    }]
    with patch(
        "app.services.fal_motion_safety._read_tesseract_rows",
        side_effect=[("completed", primary), ("completed", confirmation)],
    ):
        result = inspect_visible_text(str(_png(tmp_path)))

    assert result["visible_tokens"] == []
    assert result["numeric_confirmation_status"] == "completed"


def test_targeted_exact_retry_uses_finer_original_resolution_tiles_after_coarse_miss(tmp_path):
    image = tmp_path / "wide-scene.png"
    Image.new("RGB", (2752, 1536), "white").save(image)
    target_box = (1376, 768, 2064, 1280)

    def fake_region_rows(_path, box, *, psm=6):
        if box == target_box:
            return "completed", [{
                "text": "질문", "conf": "96", "word_num": "1",
                "block_num": "1", "par_num": "1", "line_num": "1",
            }]
        return "completed", []

    with patch(
        "app.services.fal_motion_safety._read_tesseract_region_rows",
        side_effect=fake_region_rows,
    ):
        status, hits, evidence = _targeted_exact_text_retry(str(image), ["질문"])

    assert status == "completed"
    assert hits == ["질문"]
    assert evidence == [{
        "source": "local_overlap_4x4_psm6",
        "tile": list(target_box),
        "texts": ["질문"],
    }]


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
    original_stat = image.stat()
    original = image.read_bytes()
    replacement = bytes([original[0] ^ 1]) + original[1:]
    image.write_bytes(replacement)
    os.utime(image, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert image.stat().st_size == original_stat.st_size
    assert image.stat().st_mtime_ns == original_stat.st_mtime_ns
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

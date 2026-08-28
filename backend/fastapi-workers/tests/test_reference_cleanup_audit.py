"""정리 후보와 활성 자산을 구분하되 새로운 자산을 자동 삭제 대상으로 삼지 않는다."""
from pathlib import Path

import pytest

from scripts.audit_reference_cleanup import TOOL_INPUTS, classify, runtime_names
from app.v5.providers import gemini_provider


def test_runtime_whitelist_matches_real_loader():
    active = runtime_names(Path(gemini_provider.__file__))
    assert len(active) == 9
    assert active == {
        gemini_provider._FACE_RANGE_REF_NAME,
        *gemini_provider._FACE_ROLE_REF_NAMES.values(),
        *gemini_provider._SCENE_STYLE_REF_NAMES,
    }
    assert all(classify(name, active) == "runtime_required" for name in active)


@pytest.mark.parametrize("name", sorted(TOOL_INPUTS))
def test_tool_inputs_not_mistaken_for_default_runtime_assets(name):
    assert classify(name, set()) == "tool_input"


def test_rebuild_pixel_source_is_distinct_from_unused_extracted_frames():
    assert classify("source_05s.png", set()) == "rebuild_input"
    for seconds in (20, 35, 50):
        assert classify(f"source_{seconds}s.png", set()) == "unused_rebuild_output"


def test_new_asset_is_not_silently_classified_for_cleanup():
    with pytest.raises(ValueError, match="미분류"):
        classify("new_character.png", set())


def test_v1_face_reference_is_preserved_as_superseded_rollback_asset():
    assert classify("channel_character_face_range_v1.png", set()) == "superseded_face_reference"

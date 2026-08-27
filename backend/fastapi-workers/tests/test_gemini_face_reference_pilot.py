import copy
import json
from pathlib import Path

import pytest

from scripts.run_gemini_face_reference_pilot import (
    AUTHORIZED_TOTAL_KRW,
    EXPECTED_INDICES,
    EXPECTED_SCENE_KEYS,
    validate_spec,
)


SPEC = Path(__file__).resolve().parents[3] / "docs/evidence/wo_img01_d_face_reference_20260828/face-pilot-spec.json"


def load_spec():
    return json.loads(SPEC.read_text(encoding="utf-8"))


def test_face_pilot_spec_is_exactly_three_new_keys_and_budget():
    spec = load_spec()
    validate_spec(spec)
    assert {item["index"] for item in spec["scenes"]} == EXPECTED_INDICES
    assert {item["scene_key"] for item in spec["scenes"]} == EXPECTED_SCENE_KEYS
    assert spec["authorization"]["approved_total_reserved_krw"] == AUTHORIZED_TOTAL_KRW
    assert spec["scene42_frozen_and_excluded"] is True


@pytest.mark.parametrize("change", ["budget", "scene42", "duplicate_key", "v1"])
def test_face_pilot_rejects_any_expansion(change):
    spec = copy.deepcopy(load_spec())
    if change == "budget":
        spec["authorization"]["approved_total_reserved_krw"] = 6400
    elif change == "scene42":
        spec["scenes"][0]["index"] = 42
    elif change == "duplicate_key":
        spec["scenes"][0]["scene_key"] = spec["scenes"][1]["scene_key"]
    elif change == "v1":
        spec["face_reference"]["name"] = "channel_character_face_range_v1.png"
    with pytest.raises(RuntimeError):
        validate_spec(spec)

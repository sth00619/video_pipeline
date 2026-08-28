import json
from pathlib import Path

import pytest

from app.v5.providers.gemini_provider import ensure_gemini_reference_contract
from scripts.run_gemini_scene07_surfacefix_canary import prepare_row, validate_spec


REPO = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO / "docs/evidence/wo_img01_g_surfacefix_canary_20260828/scene07-surfacefix-canary-spec.json"


def spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_surfacefix_canary_allows_one_post_and_stops_for_user_review():
    value = spec()
    validate_spec(value)
    assert value["authorization"]["external_post_limit"] == 1
    assert value["authorization"]["prior_ledger_exposure_krw"] == 9600
    assert value["authorization"]["cumulative_exposure_cap_krw"] == 11200
    assert value["authorization"]["continuation"] == "stop_after_one_for_user_visual_review"


def test_surfacefix_canary_isolates_two_fixes_and_preserves_known_surface_mismatch():
    value = spec()
    row = prepare_row(value)
    assert row["references"] == value["expected_references"]
    assert "calm uniform interior" in row["prompt"]
    assert "non-linguistic shapes" not in row["prompt"]
    assert "Two unlettered containers" in row["prompt"]
    assert {item["surface"] for item in row["scene"]["screen_text_plan"]} == {"main"}
    assert [item["text"] for item in row["scene"]["screen_text_plan"]] == [
        "삼성전자", "SK하이닉스", "코스피", "143조 원"
    ]
    assert row["final_prompt"] == ensure_gemini_reference_contract(
        row["prompt"], row["reference_paths"]
    )


def test_surfacefix_canary_rejects_semantic_binding_or_budget_drift():
    value = spec()
    value["causal_isolation"]["semantic_object_surface_binding_change_forbidden"] = False
    with pytest.raises(RuntimeError, match="의미 표면 바인딩"):
        validate_spec(value)

    value = spec()
    value["authorization"]["cumulative_exposure_cap_krw"] = 12800
    with pytest.raises(RuntimeError, match="11,200"):
        validate_spec(value)

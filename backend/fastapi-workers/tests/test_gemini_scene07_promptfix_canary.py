import json
from pathlib import Path

import pytest

from scripts.run_gemini_scene07_promptfix_canary import prepare_row, validate_spec


REPO = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO / "docs/evidence/wo_provider_01_reopen_runtime_20260828/scene07-promptfix-canary-spec.json"


def spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_promptfix_canary_spec_keeps_one_call_and_cumulative_budget():
    value = spec()
    validate_spec(value)
    assert value["authorization"]["external_post_limit"] == 1
    assert value["authorization"]["prior_ledger_exposure_krw"] == 8000
    assert value["authorization"]["cumulative_exposure_cap_krw"] == 9600


def test_promptfix_canary_uses_clean_prompt_and_preserves_two_excluded_props():
    # 이 spec은 이미 실행된 과거 canary의 승인 입력이다. 공통 해부학 계약이
    # 변경되면 같은 spec으로 조용히 재실행하지 않고 새 spec을 발급해야 한다.
    with pytest.raises(RuntimeError, match="프롬프트 해시"):
        prepare_row(spec())
    row = prepare_row(spec(), verify_expected_hash=False)
    assert row["prompt_sha256"] != spec()["expected_prompt_sha256"]
    assert "Two unlettered containers" in row["prompt"]
    assert "shapesinguistic" not in row["prompt"]
    assert "bold digits" not in row["prompt"]
    assert row["references"][0]["name"] == "channel_character_face_range_v2.png"


def test_promptfix_canary_rejects_budget_drift():
    value = spec()
    value["authorization"]["cumulative_exposure_cap_krw"] = 11200
    with pytest.raises(RuntimeError, match="9,600"):
        validate_spec(value)

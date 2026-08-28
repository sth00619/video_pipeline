import json
from pathlib import Path

import pytest

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


def test_historical_surfacefix_canary_refuses_replay_after_common_prompt_contract_changes():
    value = spec()
    # 이 사양은 당시 두 변수만 격리한 유료 canary의 불변 증거다. 이후 공통
    # 운영 프롬프트가 바뀌면 과거 해시를 새 결과처럼 재사용하지 않아야 한다.
    with pytest.raises(RuntimeError, match="bounded 프롬프트 해시"):
        prepare_row(value)


def test_surfacefix_canary_rejects_semantic_binding_or_budget_drift():
    value = spec()
    value["causal_isolation"]["semantic_object_surface_binding_change_forbidden"] = False
    with pytest.raises(RuntimeError, match="의미 표면 바인딩"):
        validate_spec(value)

    value = spec()
    value["authorization"]["cumulative_exposure_cap_krw"] = 12800
    with pytest.raises(RuntimeError, match="11,200"):
        validate_spec(value)

import json
from pathlib import Path

import pytest

from scripts import run_gemini_scene07_eye_layers_canary as eye_runner


REPO = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO / "docs/evidence/wo_img01_h_eye_layers_canary_20260829/scene07-eye-layers-canary-spec.json"


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_eye_layers_canary_is_one_new_scene07_request_and_stops_for_review():
    spec = _spec()
    eye_runner.validate_spec(spec)
    # 역사적 유료 canary 명세의 고정 해시는 보존한다. 현재 공통 프롬프트를
    # 재구성하는 회귀에서는 의도적 계약 변경만 허용하고 외부 POST 경로는
    # 계속 과거 해시를 엄격히 요구한다.
    row = eye_runner.prepare_row(spec, verify_expected_hash=False)

    assert spec["scene"]["scene_key"] == "wo-img01-h-eye-layers:7"
    assert spec["authorization"]["external_post_limit"] == 1
    assert spec["authorization"]["cumulative_exposure_cap_krw"] == 30_400
    assert spec["authorization"]["continuation"] == "stop_after_one_for_user_visual_review"
    assert "job52-range-v2-operational-v3-eye-layers" in row["final_prompt"]
    assert "solid black oval does not count as sclera" in row["final_prompt"]


def test_eye_layers_canary_rejects_budget_or_scene42_drift():
    spec = _spec()
    spec["authorization"]["cumulative_exposure_cap_krw"] += 1
    with pytest.raises(RuntimeError, match="30,400"):
        eye_runner.validate_spec(spec)

    spec = _spec()
    spec["scene42_frozen_and_excluded"] = False
    with pytest.raises(RuntimeError, match="scene42"):
        eye_runner.validate_spec(spec)

import copy
from datetime import datetime
import json
from pathlib import Path

import pytest

from scripts.run_gemini_face_reference_reopen_canary import (
    CUMULATIVE_EXPOSURE_CAP_KRW,
    INCREMENTAL_RESERVED_KRW,
    validate_prior_state,
    validate_reopen_spec,
)


SPEC = (
    Path(__file__).resolve().parents[3]
    / "docs/evidence/wo_provider_01_reopen_runtime_20260828/scene07-reopen-canary-spec.json"
)


def load_spec():
    return json.loads(SPEC.read_text(encoding="utf-8"))


def prior_ledger():
    spec = load_spec()
    state = spec["request_state"]
    common = {
        "provider": "gemini",
        "model": spec["model"],
        "scene_key": state["scene_key"],
        "status": state["prior_status"],
        "status_code": state["prior_status_code"],
        "request_evidence": {"payload_sha256": state["prior_payload_sha256"]},
        "contract_fingerprint": state["prior_contract_fingerprint"],
    }
    return {
        "items": [
            {
                **common,
                "attempt_id": state["approved_reopen_first_needs_review_attempt_id"],
                "completed_at": "2026-08-27T16:42:49.574858+00:00",
                "request_control": {"failure_n": 1, "status": "needs_review"},
            },
            {
                **common,
                "attempt_id": state["approved_retry_of"],
                "completed_at": "2026-08-27T17:41:06.077450+00:00",
                "request_control": {
                    "failure_n": state["approved_retry_failure_n"],
                    "status": "needs_review",
                },
            },
        ],
        "reserved_exposure_krw": 6400,
    }


def test_reopen_canary_is_one_scene07_request_with_standing_authorization():
    spec = load_spec()
    validate_reopen_spec(spec, now=datetime.fromisoformat("2026-08-28T06:40:00+09:00"))
    assert spec["scene"]["index"] == 7
    assert spec["authorization"]["approved_incremental_reserved_krw"] == INCREMENTAL_RESERVED_KRW
    assert spec["authorization"]["cumulative_ledger_exposure_cap_krw"] == CUMULATIVE_EXPOSURE_CAP_KRW
    assert spec["request_state"]["approved_reopen_override_cooldown"] is True


@pytest.mark.parametrize("change", ["budget", "scene", "scene42", "face", "continuation", "status_source"])
def test_reopen_canary_rejects_scope_or_lineage_expansion(change):
    spec = copy.deepcopy(load_spec())
    if change == "budget":
        spec["authorization"]["approved_incremental_reserved_krw"] = 3200
    elif change == "scene":
        spec["scene"]["index"] = 2
    elif change == "scene42":
        spec["scene42_frozen_and_excluded"] = False
    elif change == "face":
        spec["face_reference"]["name"] = "channel_character_face_range_v1.png"
    elif change == "continuation":
        spec["authorization"]["on_http_200"] = "continue_scene02"
    elif change == "status_source":
        spec["provider_status_check"]["source"] = "https://example.com/"
    with pytest.raises(RuntimeError):
        validate_reopen_spec(spec, now=datetime.fromisoformat("2026-08-28T06:40:00+09:00"))


def test_reopen_canary_requires_current_window_first_review_and_latest_503():
    spec = load_spec()
    ledger = prior_ledger()
    first, previous = validate_prior_state(spec, ledger)
    assert first["attempt_id"] == spec["request_state"]["approved_reopen_first_needs_review_attempt_id"]
    assert previous["attempt_id"] == spec["request_state"]["approved_retry_of"]

    ledger["items"][0]["completed_at"] = "2026-08-27T16:42:50+00:00"
    with pytest.raises(RuntimeError, match="최초 검수 완료 시각"):
        validate_prior_state(spec, ledger)


def test_reopen_canary_preserves_existing_reserved_exposure():
    spec = load_spec()
    ledger = prior_ledger()
    ledger["reserved_exposure_krw"] = 0
    with pytest.raises(RuntimeError, match="예약 노출"):
        validate_prior_state(spec, ledger)

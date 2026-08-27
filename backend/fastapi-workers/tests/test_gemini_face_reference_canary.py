import copy
import json
from pathlib import Path

import pytest

from scripts.run_gemini_face_reference_canary import (
    CUMULATIVE_EXPOSURE_CAP_KRW,
    INCREMENTAL_RESERVED_KRW,
    validate_canary_spec,
    validate_prior_state,
)


SPEC = Path(__file__).resolve().parents[3] / "docs/evidence/wo_img01_d_face_reference_20260828/face-scene07-canary-spec.json"


def load_spec():
    return json.loads(SPEC.read_text(encoding="utf-8"))


def prior_ledger():
    spec = load_spec()
    state = spec["request_state"]
    return {
        "items": [{
            "provider": "gemini",
            "model": spec["model"],
            "scene_key": state["scene_key"],
            "attempt_id": state["approved_retry_of"],
            "status": state["prior_status"],
            "status_code": state["prior_status_code"],
            "request_evidence": {"payload_sha256": state["prior_payload_sha256"]},
            "contract_fingerprint": state["prior_contract_fingerprint"],
            "request_control": {"failure_n": state["approved_retry_failure_n"]},
        }],
        "reserved_exposure_krw": 4800,
    }


def test_canary_is_exactly_one_scene07_request_with_incremental_cap():
    spec = load_spec()
    validate_canary_spec(spec)
    assert spec["scene"]["index"] == 7
    assert spec["scene"]["scene_key"] == "face-v2:7"
    assert spec["authorization"]["approved_incremental_reserved_krw"] == INCREMENTAL_RESERVED_KRW
    assert spec["authorization"]["cumulative_ledger_exposure_cap_krw"] == CUMULATIVE_EXPOSURE_CAP_KRW


@pytest.mark.parametrize("change", ["budget", "scene", "scene42", "v1", "continuation"])
def test_canary_rejects_scope_or_lineage_expansion(change):
    spec = copy.deepcopy(load_spec())
    if change == "budget":
        spec["authorization"]["approved_incremental_reserved_krw"] = 3200
    elif change == "scene":
        spec["scene"]["index"] = 2
    elif change == "scene42":
        spec["scene42_frozen_and_excluded"] = False
    elif change == "v1":
        spec["face_reference"]["name"] = "channel_character_face_range_v1.png"
    elif change == "continuation":
        spec["authorization"]["on_http_200"] = "continue_scene02"
    with pytest.raises(RuntimeError):
        validate_canary_spec(spec)


def test_canary_requires_exact_prior_attempt_payload_and_failure_counter():
    spec = load_spec()
    ledger = prior_ledger()
    validate_prior_state(spec, ledger)
    ledger["items"][0]["request_evidence"]["payload_sha256"] = "0" * 64
    with pytest.raises(RuntimeError):
        validate_prior_state(spec, ledger)


def test_canary_requires_existing_reserved_exposure_to_be_preserved():
    spec = load_spec()
    ledger = prior_ledger()
    ledger["reserved_exposure_krw"] = 0
    with pytest.raises(RuntimeError):
        validate_prior_state(spec, ledger)

"""승인된 503 재시도는 같은 계약/원장의 다음 1회만 실행한다. 전부 가짜 HTTP다."""
import base64
import copy
from io import BytesIO
import json

import pytest
from PIL import Image

from app import runtime_config
from app.providers.real.image import NanaBananaProvider
from app.utils.budget import ProviderRequestAudit, ProviderRequestBudgetExceeded
from app.utils.image_request_control import ImageRequestHeld


@pytest.fixture
def retry_case(tmp_path, monkeypatch):
    calls = []
    status = [503]
    data = BytesIO()
    Image.new("RGB", (4, 4), "blue").save(data, "PNG")

    class Response:
        headers = {}
        text = "UNAVAILABLE"

        @property
        def status_code(self):
            return status[0]

        def json(self):
            if status[0] != 200:
                return {"error": {"status": "UNAVAILABLE"}}
            return {"usageMetadata": {"promptTokenCount": 5, "thoughtsTokenCount": 7},
                    "candidates": [{"content": {"parts": [{"inlineData": {
                        "data": base64.b64encode(data.getvalue()).decode()}}]}}]}

    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        return Response()

    monkeypatch.setattr("requests.post", post)
    path = tmp_path / "ledger.json"

    def owner(metadata=None, budget=3200):
        result = ProviderRequestAudit.for_path(path=path, scene_key="image:42", model="gemini-3-pro-image",
            unit_usd=1.6, usd_krw=1000, budget_limit_krw=budget,
            request_metadata=metadata or {"contract_fingerprint": "same-contract"})
        result._control.clock = lambda: 1000.
        return result

    def run(audit, prompt="same prompt"):
        return NanaBananaProvider()._generate_gemini_api(prompt, str(tmp_path / "image.png"), "fake-key",
            model="gemini-3-pro-image", image_size="2K", request_audit=audit)

    monkeypatch.setitem(runtime_config._state, "gemini_scene_request_limit", 1)
    first = owner()
    first._control.clock = lambda: 0.
    with pytest.raises(ImageRequestHeld):
        run(first)
    old = copy.deepcopy(first.summary()["entries"][0])
    metadata = {"contract_fingerprint": "same-contract", "approved_retry_of": old["attempt_id"],
                "approved_retry_prior_count": 1, "approved_retry_failure_n": 1}
    monkeypatch.setitem(runtime_config._state, "gemini_scene_request_limit", 2)
    return owner, run, metadata, calls, status, old, path


@pytest.mark.parametrize("response_status", [200, 503])
def test_one_approved_post_preserves_history_usage_and_blocks_reuse(retry_case, response_status):
    owner, run, metadata, calls, status, old, path = retry_case
    status[0] = response_status
    second = owner(metadata)
    if response_status == 503:
        with pytest.raises(ImageRequestHeld):
            run(second)
    else:
        assert run(second) is True
    entries = second.summary()["entries"]
    assert len(calls) == len(entries) == 2
    assert calls[0] == calls[1]
    assert entries[0] == old
    assert entries[1]["request_control"]["scene_attempt"] == 2
    assert entries[1]["request_control"]["failure_n"] == (2 if response_status == 503 else 1)
    if response_status == 503:
        assert entries[1]["request_control"]["status"] == "needs_review"
        assert 1020 <= entries[1]["request_control"]["next_allowed_at"] <= 1040
    else:
        assert entries[1]["usage_metadata"] == {"promptTokenCount": 5, "thoughtsTokenCount": 7}
    assert json.loads(path.read_text())["reserved_exposure_krw"] == 3200
    # 다른 객체나 더 넓은 예산도 소비된 동일 승인으로 추가 POST를 할 수 없다.
    with pytest.raises(ImageRequestHeld):
        run(owner(metadata, budget=10000))
    assert len(calls) == 2


@pytest.mark.parametrize("change", ["prompt", "contract", "previous", "failure_n", "count", "budget", "cooldown", "unresolved"])
def test_invalid_retry_never_posts_or_changes_first_record(retry_case, change):
    owner, run, metadata, calls, status, old, path = retry_case
    prompt = "same prompt"
    if change == "prompt":
        prompt = "different prompt"
    if change == "contract":
        metadata["contract_fingerprint"] = "different"
    if change == "previous":
        metadata["approved_retry_of"] = "different"
    if change == "failure_n":
        metadata["approved_retry_failure_n"] = 0
    if change == "count":
        metadata["approved_retry_prior_count"] = 0
    if change == "unresolved":
        ledger = json.loads(path.read_text())
        ledger["items"][0]["status"] = "reserved"
        path.write_text(json.dumps(ledger))
    before = path.read_bytes()
    second = owner(metadata, budget=1600 if change == "budget" else 3200)
    if change == "cooldown":
        second._control.clock = lambda: 0.
    with pytest.raises((ImageRequestHeld, ProviderRequestBudgetExceeded)):
        run(second, prompt)
    assert len(calls) == 1
    assert path.read_bytes() == before

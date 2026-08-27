"""유료 호출 없이 실제 HTTP 경로에서 원장까지 사용량 객체가 보존되는지 확인한다."""
import base64
import hashlib
from io import BytesIO
import json

from PIL import Image
import pytest

from app.providers.real.image import NanaBananaProvider
from app.utils.budget import ProviderRequestAudit
from app.utils.image_request_control import ImageRequestHeld


USAGE = {
    "promptTokenCount": 2450,
    "candidatesTokenCount": 1120,
    "thoughtsTokenCount": 321,
    "totalTokenCount": 3891,
    "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 770}, {"modality": "IMAGE", "tokenCount": 1680}],
    "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}],
    "serviceTier": "STANDARD",
}


def call_provider(tmp_path, monkeypatch, *, body, status=200):
    class Response:
        status_code = status
        headers = {"x-goog-request-id": "test-usage-request"}
        text = "provider error body is not persisted"

        def json(self):
            if isinstance(body, Exception):
                raise body
            return body

    payloads = []
    def post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return Response()
    monkeypatch.setattr("requests.post", post)
    ledger = tmp_path / "request.json"
    owner = ProviderRequestAudit.for_path(path=ledger, scene_key="image:42", model="gemini-3-pro-image",
        unit_usd=.1, usd_krw=1000, budget_limit_krw=1600)
    failure = None
    try:
        NanaBananaProvider()._generate_gemini_api("unchanged prompt", str(tmp_path / "image.png"), "SECRET-TEST-KEY",
            model="gemini-3-pro-image", image_size="2K", request_audit=owner, max_attempts=20)
    except ImageRequestHeld as exc:
        failure = exc
    assert len(payloads) == 1
    assert payloads[0] == {"contents": [{"parts": [{"text": "unchanged prompt"}]}],
                          "generationConfig": {"responseModalities": ["IMAGE"],
                                               "imageConfig": {"aspectRatio": "16:9", "imageSize": "2K"}}}
    saved = json.loads(ledger.read_text())
    assert len(saved["items"]) == 1
    assert "SECRET-TEST-KEY" not in ledger.read_text()
    return saved["items"][0], failure


def image_body(**extra):
    data = BytesIO()
    Image.new("RGB", (3, 3), "blue").save(data, "PNG")
    return {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(data.getvalue()).decode()}}]}}], **extra}


def test_usage_metadata_roundtrips_with_attempt_and_image_hash(tmp_path, monkeypatch):
    item, error = call_provider(tmp_path, monkeypatch, body=image_body(usageMetadata=USAGE))
    assert error is None
    assert item["usage_metadata_status"] == "present"
    assert item["usage_metadata"] == USAGE
    assert item["usage_metadata_sha256"] == hashlib.sha256(json.dumps(USAGE, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert item["attempt_id"] and item["image_sha256"]
    assert item["request_id"] == "test-usage-request"
    assert item["cost_status"] == "unverified_until_console_reconciliation"


@pytest.mark.parametrize("usage", [{}, {"totalTokenCount": 15}, {**USAGE, "futureNumericField": 7}])
def test_no_synthetic_counters_or_dropped_future_fields(tmp_path, monkeypatch, usage):
    item, error = call_provider(tmp_path, monkeypatch, body=image_body(usageMetadata=usage))
    assert error is None
    assert item["usage_metadata"] == usage
    assert item["usage_metadata_status"] == "present"


def test_absent_usage_is_not_zero_usage_or_image_failure(tmp_path, monkeypatch):
    item, error = call_provider(tmp_path, monkeypatch, body=image_body())
    assert error is None
    assert item["usage_metadata"] is None
    assert item["usage_metadata_status"] == "absent"


@pytest.mark.parametrize("usage", [None, [], "invalid usage"])
def test_malformed_usage_is_flagged_without_corrupting_image(tmp_path, monkeypatch, usage):
    item, error = call_provider(tmp_path, monkeypatch, body=image_body(usageMetadata=usage))
    assert error is None
    assert item["usage_metadata_status"] == "invalid"
    assert item["usage_metadata"] is None


@pytest.mark.parametrize("body,status", [
    ({"usageMetadata": USAGE, "candidates": []}, 200),
    ({"usageMetadata": USAGE, "error": {"status": "UNAVAILABLE"}}, 503),
])
def test_usage_survives_failed_image_or_http_error(tmp_path, monkeypatch, body, status):
    item, error = call_provider(tmp_path, monkeypatch, body=body, status=status)
    assert error is not None
    assert item["usage_metadata"] == USAGE
    assert item["status_code"] == status
    assert item["status"] == ("invalid_image" if status == 200 else "http_503")


@pytest.mark.parametrize("status", [200, 503])
def test_non_json_response_does_not_trigger_nested_retry(tmp_path, monkeypatch, status):
    item, error = call_provider(tmp_path, monkeypatch, body=ValueError("not JSON"), status=status)
    assert error is not None
    assert item["usage_metadata_status"] == "absent"

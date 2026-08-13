"""외부 이미지 요청 단위의 예산 예약과 감사 기록을 검증한다."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.utils import budget
from app.utils.budget import ProviderRequestAudit, ProviderRequestBudgetExceeded, record_cost
from app.providers.real.image import GeminiImageGenerationError, NanaBananaProvider


def test_each_http_attempt_is_reserved_and_persisted(tmp_path: Path):
    path = tmp_path / "request_ledger.json"
    audit = ProviderRequestAudit.for_path(
        path=path,
        scene_key="scene-01",
        model="gemini-3-pro-image",
        unit_usd=0.1,
        usd_krw=1000,
        budget_limit_krw=300,
        request_metadata={"reference_contract": "v2_textless", "reference_artifacts": [{"role": "character", "sha256": "abc"}]},
    )

    first = audit.before_attempt(attempt=1)
    audit.after_attempt(first, status_code=503, request_id="req-503", outcome="http_503")
    second = audit.before_attempt(attempt=2)
    audit.after_attempt(second, status_code=200, request_id="req-200", outcome="http_200")

    ledger = json.loads(path.read_text(encoding="utf-8"))

    # 503 실패는 과금되지 않으므로 합계는 성공한 1건(100원)만 포함한다.
    assert ledger["total_krw"] == 100

    assert [(item["attempt"], item["status"], item["status_code"]) for item in ledger["items"]] == [
        (1, "http_503", 503),
        (2, "http_200", 200),
    ]

    # 503 항목: Google 과금 없음 → 0원 취소 처리
    assert ledger["items"][0]["amount_krw"] == 0
    assert ledger["items"][0]["cost_status"] == "cancelled_due_to_failure"

    # 200 항목: 성공 → 과금 미확정 상태로 유지
    assert ledger["items"][1]["cost_status"] == "unverified_until_console_reconciliation"

    assert ledger["items"][0]["request_metadata"]["reference_contract"] == "v2_textless"


def test_reservation_blocks_post_before_a_network_call(tmp_path: Path):
    path = tmp_path / "request_ledger.json"
    audit = ProviderRequestAudit.for_path(
        path=path,
        scene_key="scene-01",
        model="gemini-3-pro-image",
        unit_usd=0.1,
        usd_krw=1000,
        budget_limit_krw=99,
    )

    try:
        audit.before_attempt(attempt=1)
        assert False, "예약 상한을 넘는 HTTP 요청은 차단돼야 합니다."
    except ProviderRequestBudgetExceeded:
        pass
    assert not path.exists()


def test_v4_success_record_does_not_duplicate_a_reserved_gemini_attempt(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(budget, "_job_path", lambda _job_id, _name: tmp_path / _name)
    monkeypatch.setattr(budget.runtime_config, "get", lambda: {
        "img_cost_flash_1k_usd": 0.05,
        "img_cost_pro_2k_usd": 0.1,
        "kling_cost_per_clip_usd": 0.35,
        "usd_krw": 1000,
        "max_budget_per_video_krw": 1000,
    })
    audit = ProviderRequestAudit.for_job(
        job_id=1,
        scene_key="image:0",
        model="gemini-3-pro-image",
    )
    token = audit.before_attempt(attempt=1)
    audit.after_attempt(token, status_code=200, outcome="http_200")

    ledger = record_cost(1, "pro", scene_key="image:0")
    assert ledger["total_krw"] == 100
    assert len(ledger["items"]) == 1
    assert ledger["items"][0]["kind"] == "gemini_pro_request"


def test_kling_success_record_does_not_duplicate_a_reserved_request(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(budget, "_job_path", lambda _job_id, _name: tmp_path / _name)
    monkeypatch.setattr(budget.runtime_config, "get", lambda: {
        "img_cost_flash_1k_usd": 0.05,
        "img_cost_pro_2k_usd": 0.1,
        "kling_cost_per_clip_usd": 0.35,
        "usd_krw": 1000,
        "max_budget_per_video_krw": 1000,
    })
    audit = ProviderRequestAudit.for_kling(job_id=1, scene_key="kling:0")
    token = audit.before_attempt(attempt=1)
    audit.after_attempt(token, status_code=200, outcome="succeeded")

    ledger = record_cost(1, "kling", scene_key="kling:0")
    assert ledger["total_krw"] == 350
    assert len(ledger["items"]) == 1
    assert ledger["items"][0]["kind"] == "kling_request"


def test_provider_records_each_retry_before_post(tmp_path: Path, monkeypatch):
    class Response:
        def __init__(self, status_code: int, request_id: str):
            self.status_code = status_code
            self.headers = {"x-goog-request-id": request_id}
            self.text = "provider test response"

    responses = [Response(503, "retry-1"), Response(404, "final-2")]
    calls = []

    def fake_post(*_args, **_kwargs):
        calls.append(True)
        return responses.pop(0)

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    path = tmp_path / "request_ledger.json"
    audit = ProviderRequestAudit.for_path(
        path=path,
        scene_key="scene-01",
        model="gemini-3-pro-image",
        unit_usd=0.1,
        usd_krw=1000,
        budget_limit_krw=300,
    )

    with pytest.raises(GeminiImageGenerationError):
        NanaBananaProvider()._generate_gemini_api(
            "test", str(tmp_path / "unused.png"), "not-a-real-key", [],
            model="gemini-3-pro-image", image_size="2K", max_attempts=2,
            retry_base_seconds=1, request_audit=audit,
        )

    ledger = json.loads(path.read_text(encoding="utf-8"))

    # 핵심 검증: HTTP 시도가 2번 모두 원장에 기록됐는가
    assert len(calls) == 2
    assert len(ledger["items"]) == 2, "재시도 포함 모든 attempt가 원장에 기록돼야 한다"

    assert [(item["status"], item["request_id"]) for item in ledger["items"]] == [
        ("http_503", "retry-1"),
        ("http_404", "final-2"),
    ]

    # 503·404 둘 다 non-2xx → 과금 없음, 합계 0원
    assert ledger["total_krw"] == 0

    # 두 항목 모두 취소 처리됐는지 확인
    assert all(item["cost_status"] == "cancelled_due_to_failure" for item in ledger["items"])
    assert all(item["amount_krw"] == 0 for item in ledger["items"])


def test_reference_payload_order_matches_the_v3_declared_contract(tmp_path: Path, monkeypatch):
    import base64
    from io import BytesIO

    from PIL import Image

    source = BytesIO()
    Image.new("RGB", (2, 2), "white").save(source, "PNG")
    generated = base64.b64encode(source.getvalue()).decode()
    captured = {}

    class Response:
        status_code = 200
        headers = {}
        text = "ok"

        @staticmethod
        def json():
            return {"candidates": [{"content": {"parts": [{"inlineData": {"data": generated}}]}}]}

    def fake_post(_endpoint, *, json, **_kwargs):
        captured["payload"] = json
        return Response()

    monkeypatch.setattr("requests.post", fake_post)
    references = []
    for name, payload in (("character", b"character"), ("style", b"style")):
        path = tmp_path / f"{name}.png"
        path.write_bytes(payload)
        references.append(str(path))

    output = tmp_path / "result.png"
    assert NanaBananaProvider()._generate_gemini_api(
        "contract prompt", str(output), "not-a-real-key", references,
        model="gemini-3-pro-image", image_size="2K", max_attempts=1,
        reference_contract_declared=True,
    )
    parts = captured["payload"]["contents"][0]["parts"]
    assert [base64.b64decode(part["inlineData"]["data"]) for part in parts[:2]] == [
        b"character", b"style",
    ]
    assert len(parts) == 3  # 두 참조 이미지와 하나의 텍스트 프롬프트

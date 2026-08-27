"""단일 실측 실행의 승인 소비와 중앙 가격 읽기를 오프라인 검증한다."""
from pathlib import Path
import json

import pytest

from scripts.run_gemini_usage_pilot import claim_once, read_prices, claim_retry, validate_retry


def test_pilot_claim_cannot_be_reused(tmp_path):
    claim_once(tmp_path)
    with pytest.raises(FileExistsError):
        claim_once(tmp_path)


def test_existing_ledger_blocks_even_without_claim(tmp_path):
    (tmp_path / "request_ledger.json").write_text("{}")
    with pytest.raises(RuntimeError, match="기존 요청"):
        claim_once(tmp_path)
    assert not (tmp_path / "execute_once.claim").exists()


def test_prices_are_read_from_supplied_central_declarations(tmp_path):
    source = tmp_path / "PricingConfig.java"
    source.write_text("GEMINI_3_PRO_IMAGE_2K_USD = BigDecimal.valueOf(0.123D);\n"
                      "USD_TO_KRW_BUDGET_RATE = BigDecimal.valueOf(1_234L);")
    price, fx = read_prices(source)
    assert str(price) == "0.123"
    assert str(fx) == "1234"


def test_missing_central_price_does_not_fall_back(tmp_path):
    source = tmp_path / "PricingConfig.java"
    source.write_text("// 가격 없음")
    with pytest.raises(ValueError, match="중앙 가격"):
        read_prices(source)


def test_retry_claim_is_exclusive_and_preserves_original_claim(tmp_path):
    original = tmp_path / "execute_once.claim"
    original.write_text("first")
    claim_retry(tmp_path, {"approved_retry_of": "first"})
    with pytest.raises(FileExistsError):
        claim_retry(tmp_path, {"approved_retry_of": "first"})
    assert original.read_text() == "first"


@pytest.mark.parametrize("change", [None, "model", "references", "status", "count", "claimed"])
def test_retry_preflight_checks_original_contract_and_single_failure(tmp_path, change):
    prior = {"status": "request_failed_no_retry", "model": "gemini-3-pro-image", "references": [{"sha256": "x"}]}
    manifest = dict(prior)
    items = [{"attempt_id": "first", "status": "http_503", "status_code": 503}]
    if change in {"model", "references"}:
        manifest[change] = "changed"
    if change == "status":
        items[0]["status"] = "reserved"
    if change == "count":
        items *= 2
    if change == "claimed":
        claim_retry(tmp_path, {})
    (tmp_path / "manifest.json").write_text(json.dumps(prior))
    (tmp_path / "request_ledger.json").write_text(json.dumps({"items": items}))
    if change:
        with pytest.raises(RuntimeError):
            validate_retry(tmp_path, manifest, "first")
    else:
        assert validate_retry(tmp_path, manifest, "first")["attempt_id"] == "first"

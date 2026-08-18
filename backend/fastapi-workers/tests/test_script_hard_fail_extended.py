import pytest

from app.workers.script_worker import (
    ScriptWorker,
    _ensure_no_unverified_financial_numbers,
    _has_unverified_financial_numbers,
    _parse_verified_facts_from_text,
    _requires_script_manual_review,
)


def test_trailing_comma_json_is_recovered():
    malformed = '[{"fact": "value",}]'

    result = _parse_verified_facts_from_text(malformed)

    assert len(result) == 1
    assert result[0]["fact"] == "value"


def test_unrecoverable_json_raises_not_returns_empty():
    broken = "[invalid json {"

    with pytest.raises(RuntimeError, match="파싱 불가"):
        _parse_verified_facts_from_text(broken)


def test_unverified_financial_number_raises():
    script = "삼성전자의 영업이익은 640억 달러를 기록했습니다."

    with pytest.raises(RuntimeError, match="AGENTS.md 안전 계약 위반"):
        _ensure_no_unverified_financial_numbers(script, [])


def test_verified_facts_present_allows_financial_numbers():
    script = "영업이익은 640억 달러입니다."
    verified = [{"source": "한국경제", "fact": "영업이익은 640억 달러입니다."}]

    assert not _has_unverified_financial_numbers(script, verified)
    _ensure_no_unverified_financial_numbers(script, verified)


def test_auto_mode_requires_manual_review_when_flow_qa_fails():
    requires_review = _requires_script_manual_review(
        rejected_scenes=[],
        provider_log=[],
        house_style_quality={"passed": True},
        flow_qa={"passed": False},
        unverified_numbers=False,
        autonomy_mode="AUTO",
    )

    assert requires_review is True


def test_api_key_missing_still_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ScriptWorker().generate(
            keyword="삼성전자",
            category="INDIVIDUAL_STOCK",
            target_minutes=1,
            market_data={"source": "test"},
            job_id=999,
        )

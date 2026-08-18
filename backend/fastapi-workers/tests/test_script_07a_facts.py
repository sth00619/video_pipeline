import pytest

from app.workers.script_worker import (
    _build_fact_check_summary,
    _ensure_no_unverified_financial_numbers,
    _script_audit_fields,
    _split_verified_facts,
)


def test_contradicted_facts_are_removed_from_verified_facts():
    all_facts = [
        {"fact": "정상 사실", "cross_verified": True, "contradiction_detected": False},
        {"fact": "모순 사실", "cross_verified": False, "contradiction_detected": True},
    ]

    clean, suspect = _split_verified_facts(all_facts)

    assert [fact["fact"] for fact in clean] == ["정상 사실"]
    assert [fact["fact"] for fact in suspect] == ["모순 사실"]


def test_single_source_facts_remain_in_verified_facts():
    all_facts = [
        {"fact": "단일 출처 사실", "cross_verified": False, "contradiction_detected": False},
    ]

    clean, suspect = _split_verified_facts(all_facts)

    assert clean == all_facts
    assert suspect == []


def test_all_contradicted_facts_keep_hard_fail_contract():
    all_facts = [
        {"fact": "모순 1", "contradiction_detected": True},
        {"fact": "모순 2", "contradiction_detected": True},
    ]

    clean, suspect = _split_verified_facts(all_facts)

    assert clean == []
    assert len(suspect) == 2
    with pytest.raises(RuntimeError, match="AGENTS.md 안전 계약 위반"):
        _ensure_no_unverified_financial_numbers("영업이익은 640억 달러입니다.", clean)


def test_news_articles_are_included_with_urls_only():
    audit = _script_audit_fields(
        [],
        [],
        [
            {
                "title": "뉴스 1",
                "url": "https://yna.co.kr/a1",
                "source": "연합뉴스",
                "publishedAt": "2026-08-18T09:00:00+09:00",
            },
            {"title": "URL 없음", "link": "", "outlet": "기타"},
        ],
    )

    assert audit["news_articles"] == [
        {
            "title": "뉴스 1",
            "link": "https://yna.co.kr/a1",
            "outlet": "연합뉴스",
            "pubDate": "2026-08-18T09:00:00+09:00",
        }
    ]


def test_news_articles_are_deduplicated_and_capped_for_audit():
    articles = [
        {
            "title": f"뉴스 {index}",
            "link": f"https://news.example/{index}",
            "outlet": "한국경제",
        }
        for index in range(13)
    ]
    articles.insert(1, dict(articles[0]))

    audit = _script_audit_fields([], [], articles)

    assert len(audit["news_articles"]) == 12
    assert len({article["link"] for article in audit["news_articles"]}) == 12


def test_fact_check_summary_counts_clean_single_and_contradicted_facts():
    all_facts = [
        {"cross_verified": True, "contradiction_detected": False},
        {"cross_verified": False, "contradiction_detected": False},
        {"cross_verified": False, "contradiction_detected": True},
    ]

    summary = _build_fact_check_summary(all_facts, suspect_count=1)

    assert summary == {
        "total": 3,
        "cross_verified": 1,
        "single_source": 1,
        "contradicted": 1,
    }

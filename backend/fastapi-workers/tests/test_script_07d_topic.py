from app.workers.script_worker import (
    _TOPIC_SCOPE_MIN_RATIO,
    _all_search_terms,
    _validate_topic_scope,
)


def test_job187_scenario_passes_at_fifteen_percent():
    paragraphs = (
        ["삼성전자 주가가 움직였습니다."] * 21
        + ["배당 공시가 나왔습니다."] * 50
        + ["시장 전반의 흐름입니다."] * 51
    )

    result = _validate_topic_scope("\n".join(paragraphs), "삼성전자")

    assert _TOPIC_SCOPE_MIN_RATIO == 0.15
    assert result["passed"] is True
    assert result["total_paragraphs"] == 122
    assert result["keyword_paragraphs"] == 21
    assert abs(result["keyword_mention_ratio"] - 0.172) < 0.01


def test_compound_keyword_parts_count_as_match():
    paragraphs = (
        ["삼성전자 특별배당 발표"] * 5
        + ["특별배당 규모는 다음과 같습니다."] * 20
        + ["시장 반응입니다."] * 75
    )

    result = _validate_topic_scope("\n".join(paragraphs), "삼성전자 특별배당")

    assert result["passed"] is True
    assert result["keyword_paragraphs"] == 25


def test_severe_topic_drift_still_blocked():
    paragraphs = (
        ["오늘 삼성전자를 살펴보겠습니다."] * 3
        + ["로봇 ETF가 주목받고 있습니다."] * 30
        + ["부동산 시장이 변동 중입니다."] * 30
        + ["ETF 포트폴리오 전략입니다."] * 37
    )

    result = _validate_topic_scope("\n".join(paragraphs), "삼성전자")

    assert result["passed"] is False
    assert result["keyword_paragraphs"] == 3
    assert result["keyword_mention_ratio"] <= 0.05


def test_alias_terms_increase_match_count():
    paragraphs = (
        ["미국주식 시장 동향입니다."] * 5
        + ["S&P500이 상승했습니다."] * 20
        + ["나스닥 기술주가 반등했습니다."] * 20
        + ["시장 전반 분석입니다."] * 55
    )

    result = _validate_topic_scope("\n".join(paragraphs), "미국주식")

    assert result["passed"] is True
    assert result["keyword_paragraphs"] == 45


def test_all_search_terms_includes_parts_and_aliases():
    terms = _all_search_terms("삼성전자 특별배당")

    assert "삼성전자 특별배당" in terms
    assert "삼성전자" in terms
    assert "특별배당" in terms
    assert "삼성" in terms


def test_empty_script_reports_search_term_contract():
    result = _validate_topic_scope("", "미국주식 전망")

    assert result == {
        "passed": False,
        "keyword_mention_ratio": 0.0,
        "required_ratio": 0.15,
        "total_paragraphs": 0,
        "keyword_paragraphs": 0,
        "search_terms_used": len(_all_search_terms("미국주식 전망")),
    }

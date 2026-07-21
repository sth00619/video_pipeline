from app.workers.script_worker import (
    ScriptResearchRequiredError,
    _selected_keyword_terms,
    _validate_keyword_coverage,
)


def test_korean_postpositions_and_connective_words_do_not_create_false_missing_terms():
    topic = "코스피 급락 이후 반등과 빅테크 실적 영향"
    script = "코스피는 고점에서 급락했습니다. 빅테크 실적 발표 뒤 반등 가능성을 살펴봅니다."
    validation = _validate_keyword_coverage(script, _selected_keyword_terms(topic))
    assert validation["passed"]
    assert validation["missing_terms"] == []


def test_research_required_error_keeps_explicit_missing_terms():
    error = ScriptResearchRequiredError("근거 확인 필요", ["삼성전자", "HBM"])
    assert error.missing_terms == ["삼성전자", "HBM"]


def test_market_semantic_equivalents_cover_text_flow_conclusion():
    topic = "코스피 급락 이후 반등과 빅테크 실적 영향"
    script = (
        "코스피는 외국인 매도로 낙폭이 크게 확대됐습니다. "
        "이후 지수는 손실을 일부 회복했고, 빅테크 실적이 방향을 좌우했습니다."
    )
    validation = _validate_keyword_coverage(script, _selected_keyword_terms(topic))
    assert validation["passed"]
    assert validation["missing_terms"] == []


def test_market_crash_can_be_narrated_as_index_collapse():
    topic = "코스피 급락 이후 반등과 빅테크 실적 영향"
    script = "코스피가 한 달 사이 무너졌습니다. 이후 회복 흐름에는 빅테크 실적이 영향을 줬습니다."
    validation = _validate_keyword_coverage(script, _selected_keyword_terms(topic))
    assert validation["passed"]

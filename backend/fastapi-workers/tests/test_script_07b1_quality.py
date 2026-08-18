from app.workers.script_worker import (
    _apply_flow_qa_contract,
    _split_verified_facts,
    _synthesize_revision_instruction,
    _validate_topic_scope,
)


def _passing_deterministic() -> dict:
    return {
        "repetitions": [],
        "rhetorical_rhythm": {"passed": True},
        "spoken_pacing": {"passed": True},
        "topic_scope": {"passed": True},
    }


def test_synthesize_instruction_for_repeat_failure():
    deterministic = _passing_deterministic()
    deterministic["repetitions"] = ["투자 판단은 반드시 스스로"]

    instruction = _synthesize_revision_instruction(deterministic, "삼성전자")

    assert "반복" in instruction
    assert "투자 판단은" in instruction


def test_empty_instruction_is_synthesized_when_deterministic_fails():
    flow_qa = {
        # Claude 판정이 통과여도 결정론 리듬 검사가 최종 실패를 추가한다.
        "passed": True,
        "revision_instruction": "",
        "deterministic": {
            "repetitions": [],
            "rhetorical_rhythm": {"passed": False},
            "spoken_pacing": {"passed": True},
        },
    }
    script = "\n".join(["삼성전자 실적을 확인합니다."] * 4)

    result = _apply_flow_qa_contract(flow_qa, script, "삼성전자")

    assert result["passed"] is False
    assert "종결 어미" in result["revision_instruction"]


def test_topic_scope_passes_when_keyword_in_30pct_paragraphs():
    script = "\n".join(
        ["삼성전자 주가가 하락했습니다."] * 4
        + ["시장 전반이 약세입니다."] * 6
    )

    result = _validate_topic_scope(script, "삼성전자")

    assert result["passed"] is True
    assert result["keyword_mention_ratio"] == 0.4


def test_topic_scope_fails_and_builds_keyword_instruction():
    script = "삼성전자 관련\n" + "\n".join(["로봇 ETF 분석입니다."] * 9)
    scope = _validate_topic_scope(script, "삼성전자")
    deterministic = _passing_deterministic()
    deterministic["topic_scope"] = scope

    instruction = _synthesize_revision_instruction(deterministic, "삼성전자")

    assert scope["passed"] is False
    assert scope["keyword_mention_ratio"] == 0.1
    assert "삼성전자" in instruction
    assert "90%" in instruction


def test_keyword_alias_counts_in_topic_scope():
    cases = [
        ("삼성전자", "삼성 주가 현황입니다."),
        ("미국주식 전망", "S&P500과 나스닥을 확인합니다."),
        ("금리 전망", "연준과 FOMC 결정을 봅니다."),
        ("환율 전망", "원달러와 USD 흐름을 봅니다."),
        ("ETF 전망", "KODEX와 TIGER 수급을 봅니다."),
        ("2차전지 전망", "배터리와 리튬 가격을 봅니다."),
        ("인공지능 전망", "생성형 AI와 GPU 수요를 봅니다."),
        ("국제유가 전망", "WTI와 OPEC 결정을 봅니다."),
    ]

    for keyword, related_sentence in cases:
        script = "\n".join([related_sentence] * 5 + ["시장 분석입니다."] * 5)
        result = _validate_topic_scope(script, keyword)
        assert result["keyword_mention_ratio"] == 0.5, keyword
        assert result["required_ratio"] == 0.3, keyword
        assert result["passed"] is True, keyword

    unregistered = _validate_topic_scope(
        "\n".join(["테슬라 실적을 확인합니다."] * 2 + ["시장 분석입니다."] * 8),
        "테슬라 실적 전망",
    )
    assert unregistered["keyword_mention_ratio"] == 0.2
    assert unregistered["required_ratio"] == 0.15
    assert unregistered["passed"] is True


def test_contradicted_facts_still_removed():
    clean, suspect = _split_verified_facts([
        {"fact": "정상", "contradiction_detected": False},
        {"fact": "모순", "contradiction_detected": True},
    ])

    assert [fact["fact"] for fact in clean] == ["정상"]
    assert [fact["fact"] for fact in suspect] == ["모순"]

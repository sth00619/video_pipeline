from app.workers.script_worker import (
    _anchor_topic_boundaries,
    _apply_flow_qa_contract,
    _narration_from_sections,
    _split_verified_facts,
    _synthesize_revision_instruction,
    _validate_topic_boundaries,
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
    deterministic["repetitions"] = [
        {"sentence_indexes": [1, 2], "similarity": 1.0},
        {"sentence_indexes": [1, 3], "similarity": 1.0},
        {"sentence_indexes": [2, 3], "similarity": 1.0},
    ]

    instruction = _synthesize_revision_instruction(deterministic, "삼성전자")

    assert "반복" in instruction
    assert "문장 1·2·3" in instruction
    assert "동일 표현 3회" in instruction
    assert "마지막 1회만 남기고 나머지 2회는 삭제하세요" in instruction
    assert "금융 사실 삭제가 아니라" in instruction
    assert "숫자·날짜·회사명·검증 사실" in instruction


def test_synthesize_instruction_has_no_delete_order_without_repetition():
    instruction = _synthesize_revision_instruction(_passing_deterministic(), "삼성전자")

    assert "삭제하세요" not in instruction


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
        ["삼성전자 주가가 하락했습니다."] * 3
        + ["시장 전반이 약세입니다."] * 6
        + ["삼성전자 실적을 계속 확인합니다."]
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
        script = "\n".join([related_sentence] * 4 + ["시장 분석입니다."] * 5 + [related_sentence])
        result = _validate_topic_scope(script, keyword)
        assert result["keyword_mention_ratio"] == 0.5, keyword
        assert result["required_ratio"] == 0.15, keyword
        assert result["passed"] is True, keyword

    unregistered = _validate_topic_scope(
        "\n".join(["테슬라 실적을 확인합니다."] + ["시장 분석입니다."] * 8 + ["테슬라를 확인합니다."]),
        "테슬라 실적 전망",
    )
    assert unregistered["keyword_mention_ratio"] == 0.2
    assert unregistered["required_ratio"] == 0.15
    assert unregistered["passed"] is True


def test_topic_scope_rejects_generic_ending_even_when_ratio_passes():
    script = "\n".join(
        ["시장 상황입니다."] * 2
        + ["삼성전자와 SK하이닉스 실적을 확인합니다."] * 4
        + ["환율과 수급을 살펴봅니다."] * 14
    )

    scope = _validate_topic_scope(script, "삼성전자 SK하이닉스 반도체 실적 전망")
    result = _validate_topic_boundaries(script, "삼성전자 SK하이닉스 반도체 실적 전망")

    assert scope["keyword_mention_ratio"] == 0.2
    assert scope["passed"] is True
    assert result["opening_topic_connected"] is False
    assert result["ending_topic_connected"] is False
    assert result["passed"] is False


def test_topic_boundary_anchor_preserves_existing_facts_and_connects_both_ends():
    sections = [
        {"content": "삼성전자와 코스피는 6860포인트입니다.", "text": "삼성전자와 코스피는 6860포인트입니다."},
        {"content": "삼성전자 실적을 확인합니다.", "text": "삼성전자 실적을 확인합니다."},
        {"content": "환율과 수급도 살펴봅니다.", "text": "환율과 수급도 살펴봅니다."},
    ]

    anchored, applied = _anchor_topic_boundaries(
        sections, "삼성전자 SK하이닉스 반도체 실적 전망",
    )
    script = _narration_from_sections(anchored)
    scope = _validate_topic_scope(script, "삼성전자 SK하이닉스 반도체 실적 전망")
    boundaries = _validate_topic_boundaries(script, "삼성전자 SK하이닉스 반도체 실적 전망")

    assert applied == ["ending"]
    assert "6860포인트" in script
    assert "환율과 수급도 살펴봅니다." in script
    assert script.endswith("삼성전자·SK하이닉스, 계속 확인하죠.")
    assert scope["passed"] is True
    assert boundaries["opening_topic_connected"] is True
    assert boundaries["ending_topic_connected"] is True
    assert boundaries["passed"] is True


def test_contradicted_facts_still_removed():
    clean, suspect = _split_verified_facts([
        {"fact": "정상", "contradiction_detected": False},
        {"fact": "모순", "contradiction_detected": True},
    ])

    assert [fact["fact"] for fact in clean] == ["정상"]
    assert [fact["fact"] for fact in suspect] == ["모순"]

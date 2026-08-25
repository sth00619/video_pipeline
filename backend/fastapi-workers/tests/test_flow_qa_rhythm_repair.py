"""job 147(2026-08-04) 재현: flow_qa가 리듬 문제를 잡아내도 아무도 고치지
않아 AUTO 모드가 사람 승인 대기에서 영구히 멈췄다. review_flow가 만들어
두고 아무도 쓰지 않던 revision_instruction을 실제로 소비해 사실은 그대로
두고 문장 리듬만 재편집하는 경로를 검증한다."""
from __future__ import annotations

import json

from app.utils.flow_qa import review_flow
from app.workers.script_worker import (
    ScriptWorker,
    _apply_flow_qa_contract,
    _narration_from_sections,
    _stabilize_formal_rhythm,
)


def _worker() -> ScriptWorker:
    worker = ScriptWorker()
    worker._llm_provider_log = []
    return worker


def _sections(*texts: str) -> list[dict]:
    return [{"content": text, "text": text} for text in texts]


def test_rhythm_rewrite_replaces_content_by_index_and_logs_provenance(monkeypatch):
    worker = _worker()
    calls: list[str] = []

    def fake_llm(system, messages, max_tokens):
        calls.append(messages[0]["content"])
        return json.dumps([
            {"index": 0, "text": "코스피는 오늘도 상승했습니다."},
            {"index": 1, "text": "그렇다면 이 흐름은 계속될까요?"},
        ], ensure_ascii=False)

    monkeypatch.setattr(worker, "_call_llm_with_fallback", fake_llm)
    sections = _sections("코스피는 오늘도 상승했습니다.", "거래대금도 늘었습니다.")

    result = worker._rewrite_sections_for_rhythm(
        sections, verified_facts=[{"fact": "코스피 상승"}],
        revision_instruction="같은 평서문이 반복되니 질문형을 하나 섞으세요.",
        format_name="longform",
    )

    assert result[0]["content"] == "코스피는 오늘도 상승했습니다."
    assert result[1]["content"] == "그렇다면 이 흐름은 계속될까요?"
    assert result[1]["char_count"] == len("그렇다면 이 흐름은 계속될까요?")
    assert worker._llm_provider_log[-1]["purpose"] == "flow_qa_rhythm_repair"
    assert "revision_instruction" not in calls[0]  # 프롬프트 본문 자체를 검사하진 않되 호출은 됐는지만 확인
    assert "질문형" in calls[0]


def test_rhythm_rewrite_falls_back_to_original_on_malformed_response(monkeypatch):
    worker = _worker()
    monkeypatch.setattr(worker, "_call_llm_with_fallback", lambda *a, **k: "이건 JSON이 아닙니다")
    sections = _sections("원본 문장입니다.")

    result = worker._rewrite_sections_for_rhythm(
        sections, verified_facts=[], revision_instruction="", format_name="longform",
    )

    assert result[0]["content"] == "원본 문장입니다."


def test_rhythm_rewrite_keeps_original_when_replacement_breaks_the_hard_char_limit(monkeypatch, caplog):
    # job 148(2026-08-05) 재현: 리듬을 고치려고 절을 덧붙이다 상한을 넘긴
    # 문장이 나왔다. 이 치환을 그대로 받아들이면 spoken_pacing 검사를
    # 새로 실패시켜 남은 리듬 복구 시도를 모두 소진하게 된다. 상한을 넘긴
    # 치환은 버리고 원문 문장을 유지해야 한다.
    worker = _worker()
    overlong = (
        "이 문장은 리듬을 살리려고 절을 자꾸 덧붙이다 보니 원래 사실과 설명의 경계를 지나 "
        "청자가 한 호흡에 따라가기 어려운 수준으로 상한을 훌쩍 넘겨버린 아주 긴 문장입니다"
    )
    assert len(overlong.replace(" ", "")) > 52

    def fake_llm(system, messages, max_tokens):
        return json.dumps([
            {"index": 0, "text": overlong},
            {"index": 1, "text": "이 문장은 괜찮습니다."},
        ], ensure_ascii=False)

    monkeypatch.setattr(worker, "_call_llm_with_fallback", fake_llm)
    sections = _sections("원본 문장 0입니다.", "원본 문장 1입니다.")

    with caplog.at_level("WARNING"):
        result = worker._rewrite_sections_for_rhythm(
            sections, verified_facts=[], revision_instruction="", format_name="longform",
        )

    assert result[0]["content"] == "원본 문장 0입니다."  # overlong replacement rejected, original kept
    assert result[1]["content"] == "이 문장은 괜찮습니다."  # in-range replacement still applied
    assert any("자 상한" in record.message for record in caplog.records)


def test_rhythm_rewrite_accepts_multi_sentence_scene_when_each_sentence_is_within_cap(monkeypatch):
    """씬 전체가 길어도 각 문장이 상한 이내면 정상 리듬 수정을 보존한다."""
    worker = _worker()
    replacement = "삼성전자는 주주환원 계획을 발표했습니다. 그런데 주가는 왜 내렸을까요?"
    assert len(replacement.replace(" ", "")) > 28

    monkeypatch.setattr(
        worker,
        "_call_llm_with_fallback",
        lambda *args, **kwargs: json.dumps([{"index": 0, "text": replacement}], ensure_ascii=False),
    )
    sections = _sections("삼성전자는 계획을 발표했습니다. 주가는 같은 날 내렸습니다.")

    result = worker._rewrite_sections_for_rhythm(
        sections,
        verified_facts=[],
        revision_instruction="질문 역할을 섞으세요.",
        format_name="longform",
    )

    assert result[0]["content"] == replacement


def test_rhythm_rewrite_rejects_result_outside_explicit_total_length_contract(monkeypatch, caplog):
    worker = _worker()
    monkeypatch.setattr(
        worker,
        "_call_llm_with_fallback",
        lambda *args, **kwargs: json.dumps([
            {"index": 0, "text": "짧습니다."},
            {"index": 1, "text": "너무 짧습니다."},
        ], ensure_ascii=False),
    )
    sections = _sections(
        "삼성전자는 주주환원 계획을 발표했습니다.",
        "시장은 발표 내용과 집행 조건을 함께 살폈습니다.",
    )

    with caplog.at_level("WARNING"):
        result = worker._rewrite_sections_for_rhythm(
            sections,
            verified_facts=[],
            revision_instruction="종결을 다듬으세요.",
            format_name="longform",
            min_total_chars=40,
            max_total_chars=80,
        )

    assert "삼성전자" in result[0]["content"]
    assert any("총분량 계약" in record.message for record in caplog.records)


def test_rhythm_rewrite_ignores_out_of_range_or_empty_replacements(monkeypatch):
    worker = _worker()

    def fake_llm(system, messages, max_tokens):
        return json.dumps([
            {"index": 0, "text": ""},
            {"index": 5, "text": "존재하지 않는 인덱스"},
            {"index": 1, "text": "실제로 반영될 문장입니다."},
        ], ensure_ascii=False)

    monkeypatch.setattr(worker, "_call_llm_with_fallback", fake_llm)
    sections = _sections("첫 문장 원본입니다.", "둘째 문장 원본입니다.")

    result = worker._rewrite_sections_for_rhythm(
        sections, verified_facts=[], revision_instruction="", format_name="longform",
    )

    assert result[0]["content"] == "첫 문장 원본입니다."  # 빈 문자열 치환은 무시
    assert result[1]["content"] == "실제로 반영될 문장입니다."
    assert len(result) == 2  # 범위 밖 인덱스가 새 씬을 만들지 않음


def test_deterministic_ending_stabilizer_preserves_facts_and_breaks_long_formal_run():
    sections = _sections(
        "삼성전자 영업이익은 10조원입니다.",
        "SK하이닉스 영업이익은 11조원입니다.",
        "두 회사 전망치는 8월에 하향됐습니다.",
        "AI 서버 수요는 계속 늘고 있습니다.",
        "스마트폰 교체 수요도 확대됐습니다.",
        "기관 자금은 다른 종목으로 이동합니다.",
    )

    repaired, converted = _stabilize_formal_rhythm(sections)
    script = _narration_from_sections(repaired)
    result = review_flow(
        lambda *args: json.dumps({"passed": True}, ensure_ascii=False),
        script=script,
        narrative_plan={"story_beats": []},
    )

    assert converted == [3, 6]
    assert "삼성전자 영업이익은 10조원" in script
    assert "SK하이닉스 영업이익은 11조원" in script
    assert "8월" in script
    assert result["deterministic"]["rhetorical_rhythm"]["passed"] is True
    assert result["deterministic"]["spoken_pacing"]["passed"] is True


def test_deterministic_stabilizer_breaks_description_run_with_mixed_endings():
    sections = _sections(
        "보도된 수치가 그렇습니다.",
        "코스피 전체 순이익도 크게 늘었는데요.",
        "전년 동기 대비 약 4배 수준으로 증가했습니다.",
    )

    repaired, converted = _stabilize_formal_rhythm(sections)
    script = _narration_from_sections(repaired)
    result = review_flow(
        lambda *args: json.dumps({"passed": True}, ensure_ascii=False),
        script=script,
        narrative_plan={"story_beats": []},
    )

    assert converted == [3]
    assert "전년 동기 대비 약 4배 수준으로 증가했죠." in script
    assert result["deterministic"]["rhetorical_rhythm"]["passed"] is True


def test_rhythm_rewrite_keeps_last_of_three_identical_sentences(monkeypatch):
    worker = _worker()
    calls: list[tuple[str, str]] = []

    def fake_llm(system, messages, max_tokens):
        calls.append((system, messages[0]["content"]))
        rows = json.loads(messages[0]["content"].split("씬: ", 1)[1])
        return json.dumps(rows, ensure_ascii=False)

    monkeypatch.setattr(worker, "_call_llm_with_fallback", fake_llm)
    repeated = "투자 판단은 반드시 스스로 해야 합니다."
    sections = _sections(repeated, "삼성전자를 먼저 확인합니다.", repeated, repeated)

    result = worker._rewrite_sections_for_rhythm(
        sections,
        verified_facts=[{"fact": "삼성전자 실적"}],
        revision_instruction=(
            "문장 1·3·4의 동일 표현 3회 중 마지막 1회만 남기고 "
            "나머지 2회는 삭제하세요."
        ),
        format_name="longform",
        repetition_groups=[{"sentence_indexes": [1, 3, 4], "count": 3}],
    )

    assert [section["content"] for section in result].count(repeated) == 1
    assert [section["content"] for section in result] == [
        "삼성전자를 먼저 확인합니다.",
        repeated,
    ]
    assert "지정된 동일 반복 문장만 마지막 1회를 남기고" in calls[0][0]
    assert "숫자·날짜·회사명·검증" in calls[0][0]


def test_rhythm_rewrite_does_not_delete_merely_similar_financial_facts(monkeypatch):
    worker = _worker()
    monkeypatch.setattr(
        worker,
        "_call_llm_with_fallback",
        lambda system, messages, max_tokens: messages[0]["content"].split("씬: ", 1)[1],
    )
    sections = _sections(
        "삼성전자 매출은 10조원입니다.",
        "삼성전자 매출은 11조원입니다.",
    )

    result = worker._rewrite_sections_for_rhythm(
        sections,
        verified_facts=[{"fact": "삼성전자 매출은 10조원과 11조원"}],
        revision_instruction="문장 1·2 중 마지막 1회만 남기고 나머지는 삭제하세요.",
        format_name="longform",
        repetition_groups=[{"sentence_indexes": [1, 2], "count": 2}],
    )

    assert [section["content"] for section in result] == [
        "삼성전자 매출은 10조원입니다.",
        "삼성전자 매출은 11조원입니다.",
    ]


def test_rhythm_rewrite_deletes_adjacent_repeat_with_ending_only_difference(monkeypatch):
    worker = _worker()
    monkeypatch.setattr(
        worker,
        "_call_llm_with_fallback",
        lambda system, messages, max_tokens: messages[0]["content"].split("씬: ", 1)[1],
    )
    sections = _sections(
        "지금은 방향을 확인해 가는 구간인 겁니다.",
        "지금은 방향을 확인해 가는 구간인 거죠.",
    )

    result = worker._rewrite_sections_for_rhythm(
        sections,
        verified_facts=[],
        revision_instruction="문장 1·2 중 마지막 1회만 남기고 나머지는 삭제하세요.",
        format_name="longform",
        repetition_groups=[{"sentence_indexes": [1, 2], "count": 2}],
    )

    assert [section["content"] for section in result] == [
        "지금은 방향을 확인해 가는 구간인 거죠.",
    ]


def test_rhythm_rewrite_keeps_non_adjacent_ending_variants(monkeypatch):
    worker = _worker()
    monkeypatch.setattr(
        worker,
        "_call_llm_with_fallback",
        lambda system, messages, max_tokens: messages[0]["content"].split("씬: ", 1)[1],
    )
    sections = _sections(
        "지금은 방향을 확인해 가는 구간인 겁니다.",
        "중간에 다른 금융 사실을 설명합니다.",
        "지금은 방향을 확인해 가는 구간인 거죠.",
    )

    result = worker._rewrite_sections_for_rhythm(
        sections,
        verified_facts=[],
        revision_instruction="문장 1·3 중 마지막 1회만 남기고 나머지는 삭제하세요.",
        format_name="longform",
        repetition_groups=[{"sentence_indexes": [1, 3], "count": 2}],
    )

    assert len(result) == 3


def test_job_189_style_repeat_passes_flow_qa_after_one_repair(monkeypatch):
    worker = _worker()
    monkeypatch.setattr(
        worker,
        "_call_llm_with_fallback",
        lambda system, messages, max_tokens: messages[0]["content"].split("씬: ", 1)[1],
    )
    repeated = "삼성전자 실적은 확인이 필요합니다."
    sections = _sections(
        repeated,
        "삼성전자 실적을 확인할까요?",
        repeated,
        repeated,
    )
    repaired = worker._rewrite_sections_for_rhythm(
        sections,
        verified_facts=[{"fact": "삼성전자 실적은 확인이 필요합니다."}],
        revision_instruction=(
            "문장 1·3·4의 동일 표현 3회 중 마지막 1회만 남기고 "
            "나머지 2회는 삭제하세요."
        ),
        format_name="longform",
        repetition_groups=[{"sentence_indexes": [1, 3, 4], "count": 3}],
    )
    script = _narration_from_sections(repaired)
    flow_qa = review_flow(
        lambda *args: json.dumps({"passed": True}, ensure_ascii=False),
        script=script,
        narrative_plan={"story_beats": []},
    )
    result = _apply_flow_qa_contract(flow_qa, script, "삼성전자")

    assert result["passed"] is True
    assert result["deterministic"]["repetitions"] == []
    assert result["deterministic"]["spoken_pacing"]["passed"] is True
    assert result["deterministic"]["topic_scope"]["passed"] is True

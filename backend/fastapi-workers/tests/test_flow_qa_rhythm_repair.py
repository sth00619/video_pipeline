"""job 147(2026-08-04) 재현: flow_qa가 리듬 문제를 잡아내도 아무도 고치지
않아 AUTO 모드가 사람 승인 대기에서 영구히 멈췄다. review_flow가 만들어
두고 아무도 쓰지 않던 revision_instruction을 실제로 소비해 사실은 그대로
두고 문장 리듬만 재편집하는 경로를 검증한다."""
from __future__ import annotations

import json

from app.workers.script_worker import ScriptWorker


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
    overlong = "이 문장은 리듬을 살리려고 절을 자꾸자꾸 덧붙이다 보니 상한을 훌쩍훌쩍 넘겨버린 아주 긴 문장입니다"
    assert len(overlong.replace(" ", "")) > 26

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

"""job 149(2026-08-05) 재현 + 사용자 명시 지시: 총 대사 분량이 target_chars
허용폭(±8~15%)을 못 맞춘다고 스크립트 생성 전체를 실패시키지 말 것. 실제
자막·TTS 싱크에 영향을 주는 건 씬(문장) 단위 계약(문장 수, 권장 24~42자·최대 52자/20단어)
이지 총 글자 수 총합이 아니다. job 149는 재작성 3회가 모두 524자(목표
360자)로 실패해 HTTP 500으로 통째로 죽었고, Anthropic API 비용만 태웠다.
_generate_with_verified_facts가 총 분량 미스매치를 경고 로그만 남기고
계속 진행하는지, 그리고 씬 단위 계약(_validate_scene_delivery)은 여전히
강제되는지 검증한다.

2026-08-25에는 사용자가 말한 38단어를 28글자로 잘못 해석한 회귀를 바로잡아,
자연스러운 한국어 호흡을 보존하는 52자·20단어 이중 상한으로 변경했다."""
from __future__ import annotations

import pytest

from app.workers.script_worker import ScriptWorker


def _overshoot_full_text(scene_count: int) -> str:
    blocks = []
    for index in range(1, scene_count + 1):
        blocks.append(
            f"## 장면 {index:03d}\n"
            f"[대사]\n코스피와 반도체 수급 변화 흐름을 아주 자세히 설명 {index:02d}\n"
            "[비주얼 설명 (한국어)]\n코스피 시세판 앞에 선 캐릭터\n"
            "[비주얼 프롬프트 (영어)]\nanalyst in front of a stock ticker board\n"
            "[감정]\nneutral"
        )
    body = "\n\n".join(blocks)
    meta = (
        "\n\n## 메타데이터\n"
        "[추천 제목]\n코스피 주간 전망\n"
        "[추천 썸네일]\nStock market background\n"
        "[더보기 설명]\n상세 설명\n"
        "[쇼츠 대본]\n요약 대본"
    )
    return body + meta


def test_generate_does_not_raise_when_only_total_length_misses_target(monkeypatch, caplog):
    worker = ScriptWorker()
    worker._llm_provider_log = []

    # 20 scenes (>= the new 17-scene minimum) x 23 visible chars each = 460
    # chars, well above the tolerance ceiling for target_chars=360 (max
    # 414), each sentence still within the new 28-char hard cap, and
    # unrescuable by the deterministic cap since each scene has exactly one
    # sentence.
    full_text = _overshoot_full_text(20)
    monkeypatch.setattr(worker, "_call_llm_with_fallback", lambda *a, **k: full_text)

    with caplog.at_level("WARNING"):
        narration, sections, *_ = worker._generate_with_verified_facts(
            keyword="코스피 주간 전망",
            category_label="KOSPI",
            target_minutes=1,
            target_chars=360,
            verified_facts=[{"fact": "코스피 반등", "figure": "1%", "source_field": "테스트", "confidence": 0.9}],
            market_data={},
            selected_terms=["코스피"],
            keyword_news=[],
            length_contract={"target_seconds": 60},
            narrative_plan={"plan_id": "test", "story_beats": []},
        )

    assert narration  # generation completed instead of raising
    assert len(sections) == 20  # no scene silently dropped
    assert any("총 대사 분량이 목표 범위를 벗어났지만" in record.message for record in caplog.records)


def _one_overlong_sentence_full_text() -> str:
    # 정상 문장 19개에 52자를 넘는 문장 하나를 섞어 문장 상한만 격리한다.
    lines = [f"코스피와 반도체 수급 흐름을 자세히 설명 {index:02d}" for index in range(1, 20)]
    lines.append(
        "코스피와 코스닥의 동반 상승 배경과 반도체 수급 변화가 두 지수와 개별 종목의 투자 심리에 어떤 경로로 이어지는지를 한 문장에 모두 담아 지나치게 길게 설명합니다"
    )
    blocks = []
    for index, line in enumerate(lines, start=1):
        blocks.append(
            f"## 장면 {index:03d}\n[대사]\n{line}\n"
            "[비주얼 설명 (한국어)]\n코스피 시세판 앞에 선 캐릭터\n"
            "[비주얼 프롬프트 (영어)]\nanalyst in front of a stock ticker board\n"
            "[감정]\nneutral"
        )
    body = "\n\n".join(blocks)
    meta = (
        "\n\n## 메타데이터\n[추천 제목]\n코스피 주간 전망\n[추천 썸네일]\nStock market background\n"
        "[더보기 설명]\n상세 설명\n[쇼츠 대본]\n요약 대본"
    )
    return body + meta


def test_generate_rejects_even_one_sentence_over_the_hard_cap(monkeypatch):
    # 2026-08-20 사용자 기준: 한 문장의 호흡 상한은 TTS·자막 의미 단위
    # 계약이므로 AUTO에서도 경고만 남기고 통과시키지 않는다.
    worker = ScriptWorker()
    worker._llm_provider_log = []
    full_text = _one_overlong_sentence_full_text()
    monkeypatch.setattr(worker, "_call_llm_with_fallback", lambda *a, **k: full_text)

    with pytest.raises(ValueError, match="52자"):
        worker._generate_with_verified_facts(
            keyword="코스피 주간 전망",
            category_label="KOSPI",
            target_minutes=1,
            target_chars=360,
            verified_facts=[{"fact": "코스피 반등", "figure": "1%", "source_field": "테스트", "confidence": 0.9}],
            market_data={},
            selected_terms=["코스피"],
            keyword_news=[],
            length_contract={"target_seconds": 60},
            narrative_plan={"plan_id": "test", "story_beats": []},
        )

def test_generate_still_raises_when_scene_count_is_genuinely_short(monkeypatch):
    # 장면 수 부족(실제로 보여줄 장면이 모자람)은 여전히 하드 실패로 남는다 —
    # 이건 자막 한 장 길이가 아니라 영상에 채울 장면 자체가 없다는 뜻이다.
    worker = ScriptWorker()
    worker._llm_provider_log = []
    full_text = _overshoot_full_text(2)  # far below the 18-scene minimum for a 1-minute target
    monkeypatch.setattr(worker, "_call_llm_with_fallback", lambda *a, **k: full_text)

    with pytest.raises(ValueError, match="장면 수가"):
        worker._generate_with_verified_facts(
            keyword="코스피 주간 전망",
            category_label="KOSPI",
            target_minutes=1,
            target_chars=360,
            verified_facts=[{"fact": "코스피 반등", "figure": "1%", "source_field": "테스트", "confidence": 0.9}],
            market_data={},
            selected_terms=["코스피"],
            keyword_news=[],
            length_contract={"target_seconds": 60},
            narrative_plan={"plan_id": "test", "story_beats": []},
        )

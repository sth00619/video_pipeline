"""job 149(2026-08-05) 재현 + 사용자 명시 지시: 총 대사 분량이 target_chars
허용폭(±8~15%)을 못 맞춘다고 스크립트 생성 전체를 실패시키지 말 것. 실제
자막·TTS 싱크에 영향을 주는 건 씬(문장) 단위 계약(문장 수, 문장당 15~26자)
이지 총 글자 수 총합이 아니다. job 149는 재작성 3회가 모두 524자(목표
360자)로 실패해 HTTP 500으로 통째로 죽었고, Anthropic API 비용만 태웠다.
_generate_with_verified_facts가 총 분량 미스매치를 경고 로그만 남기고
계속 진행하는지, 그리고 씬 단위 계약(_validate_scene_delivery)은 여전히
강제되는지 검증한다.

2026-08-05, 사용자 명시 지시로 문장 길이 목표를 26~38자에서 15~20자로
낮췄다(하드 상한 26자). target_chars=360이면 target_scene_count는
round(360/18)=20, minimum_scene_count는 round(20*0.9)=18이다. 아래
테스트들은 이 새 계약을 기준으로 씬 개수를 구성한다."""
from __future__ import annotations

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

    # 20 scenes (>= the new 18-scene minimum) x 23 visible chars each = 460
    # chars, well above the tolerance ceiling for target_chars=360 (max
    # 414), each sentence still within the new 26-char hard cap, and
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
    # 19 short sentences (19 visible chars each, within the new 26-char hard
    # cap) plus 1 long sentence (36 chars, over the cap): 20 scenes total
    # (>= the 18-scene minimum for target_chars=360), total chars = 397
    # (within the 331~414 tolerance band), isolating the per-sentence
    # overlong failure from both the scene-count and total-length checks.
    lines = [f"코스피와 반도체 수급 흐름을 자세히 설명 {index:02d}" for index in range(1, 20)]
    lines.append("코스피와 코스닥 동반 상승과 반도체 수급 변화를 아주 자세하게 설명하는 긴 문장입니다")
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


def test_generate_does_not_raise_when_only_one_sentence_is_slightly_over_the_hard_cap(monkeypatch, caplog):
    # job 152(2026-08-05) 재현: 재작성까지 시도해도 문장 하나가 상한을
    # 살짝 넘겨 HTTP 500으로 job 전체가 죽었다. 총 분량과 장면 수는
    # 모두 계약을 만족하므로, 이 문장 하나 때문에 job을 실패시키지 않는다.
    worker = ScriptWorker()
    worker._llm_provider_log = []
    full_text = _one_overlong_sentence_full_text()
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
    assert any("씬 길이 계약을 완전히 못 맞췄지만 그대로 진행" in record.message for record in caplog.records)


def test_generate_still_raises_when_scene_count_is_genuinely_short(monkeypatch):
    # 장면 수 부족(실제로 보여줄 장면이 모자람)은 여전히 하드 실패로 남는다 —
    # 이건 자막 한 장 길이가 아니라 영상에 채울 장면 자체가 없다는 뜻이다.
    worker = ScriptWorker()
    worker._llm_provider_log = []
    full_text = _overshoot_full_text(2)  # far below the 18-scene minimum for a 1-minute target
    monkeypatch.setattr(worker, "_call_llm_with_fallback", lambda *a, **k: full_text)

    import pytest
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

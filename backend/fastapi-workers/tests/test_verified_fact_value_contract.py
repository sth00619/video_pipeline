"""WO-IMG-01-B 완전한 사실값 토큰 계약의 경계 회귀."""
import pytest

from app.v5.overlay.fact_value_contract import (
    fact_value_evidence_tokens,
    text_contains_complete_value,
    verified_fact_contains_value,
)
from app.v5.overlay.diegetic_fact_overlay import facts_from_verified_scene
from app.v5.scene.runtime_contract import _build_v5_verified_overlays


@pytest.mark.parametrize("requested,figure", [
    ("4배", "PER 14배"),
    ("143조", "영업이익 143조 5000억 원"),
    ("4", "PER 4배"),
    ("4%", "하락률 -4%"),
    ("4.1%", "상승률 14.1%"),
    ("15", "관세율 15%"),
    ("2026-08-2", "기준일 2026-08-20"),
])
def test_rejects_partial_numeric_or_date_token(requested, figure):
    fact = {"figure": figure, "fact": figure}
    assert not verified_fact_contains_value(
        fact, requested, require_structured_value_match=True,
    )


@pytest.mark.parametrize("requested,figure", [
    ("4배", "PER 4배"),
    ("143조 5000억 원", "영업이익 143조 5000억 원"),
    ("-4%", "하락률 -4%"),
    ("4.1%", "상승률 4.1%"),
    ("15%", "관세율 15%"),
    ("2026-08-20", "기준일 2026-08-20"),
    ("+0.25%p", "2.50% → 2.75% (+0.25%p)"),
])
def test_accepts_complete_numeric_or_date_token(requested, figure):
    fact = {"figure": figure, "fact": f"검증값은 {figure}이다."}
    assert verified_fact_contains_value(
        fact, requested, require_structured_value_match=True,
    )


def test_structured_value_and_declared_pt_alias_remain_compatible():
    fact = {
        "value": "2,650", "unit": "pt",
        "figure": "2,650pt", "fact": "코스피 2,650 포인트 기록",
    }
    assert verified_fact_contains_value(
        fact, "2,650", require_structured_value_match=True,
    )
    assert not verified_fact_contains_value(
        fact, "2,65", require_structured_value_match=True,
    )


def test_token_audit_preserves_full_compound_amount():
    tokens = fact_value_evidence_tokens({
        "figure": "영업이익 143조 5000억 원",
        "fact": "영업이익은 143조 5000억 원이었다.",
    })
    assert tokens == ("143조5000억원",)


def test_upward_trend_endpoint_cannot_be_truncated():
    scene = {
        "verified_facts": [{
            "figure": "12.50% → 12.75% (+0.25%p)",
            "fact": "기준금리는 12.50%에서 12.75%로 0.25%p 올랐다.",
        }],
        "v5_verified_overlays": [{
            "label": "인상폭", "value": "0.25%p",
            "start_value": "2.50%", "end_value": "12.75%",
            "visualization": "upward_trend", "source_ref": "facts[0]",
            "anchor": {"x": .2, "y": .2, "width": .3, "height": .25,
                       "kind": "embedded_monitor"},
        }],
    }
    with pytest.raises(ValueError, match="시작·종료값"):
        facts_from_verified_scene(scene)


def test_runtime_overlay_builder_uses_same_complete_value_contract():
    fact = {"value": "4배", "figure": "PER 14배", "fact": "PER 14배"}
    overlay = _build_v5_verified_overlays(
        [fact], "classroom", (.1, .1, .5, .5),
        scene={"narration": "PER 14배인데 4배로 잘라 쓰면 안 된다."},
    )
    assert overlay is None


def test_runtime_overlay_builder_does_not_bind_valid_four_to_scene_fourteen():
    fact = {"value": "4배", "figure": "PER 4배", "fact": "PER 4배"}
    overlay = _build_v5_verified_overlays(
        [fact], "classroom", (.1, .1, .5, .5),
        scene={"narration": "다른 기업의 PER은 14배다."},
    )
    assert overlay is None


def test_runtime_overlay_builder_keeps_exact_structured_value():
    fact = {
        "indicator": "KOSPI", "value": "2,650", "unit": "pt",
        "figure": "2,650pt", "fact": "코스피 2,650 포인트 기록",
    }
    overlay = _build_v5_verified_overlays(
        [fact], "classroom", (.1, .1, .5, .5),
        scene={"narration": "코스피가 2,650포인트를 기록했다."},
    )
    assert overlay and overlay[0]["value"] == "2,650"


def test_nonnumeric_overlay_value_is_not_treated_as_verified_fact_value():
    fact = {"figure": "방향성 확인", "fact": "상승 방향성이 확인됐다."}
    assert not verified_fact_contains_value(
        fact, "확인", require_structured_value_match=True,
    )


def test_scene_local_value_contract_rejects_truncation_but_keeps_declared_value_unit_split():
    assert not text_contains_complete_value("PER은 14배다", "4배")
    assert not text_contains_complete_value("영업이익 143조 5000억 원", "143조")
    assert text_contains_complete_value(
        "코스피 2,650포인트 기록", "2,650", permit_structured_unit_suffix=True,
    )

"""Stage 1 유닛 테스트: scene_entity_binder.py

파이프라인 미연결 상태에서 독립 실행.
_FIGURE_RE 버그 3개 케이스 포함.
"""
from __future__ import annotations
import sys
import hashlib
import pytest
sys.path.insert(0, "backend/fastapi-workers")

from app.utils.scene_entity_binder import (
    _FIGURE_RE,
    _fictionalize,
    _extract_figures,
    bind_scene_entities,
    compute_grounding_score,
    FICTIONALIZED_LABEL_MAP,
    _extract_entities,
    entity_is_mentioned,
)


class TestFigureRegex:
    """_FIGURE_RE 버그 수정 검증 — 이전에 한 번 고친 버그 재발 방지."""

    def test_pct_point_preserved(self):
        """0.5%p — %p(포인트) 소실 버그 수정 확인."""
        matches = [m.group(0).strip() for m in _FIGURE_RE.finditer("0.5%p 상승했습니다")]
        assert any("p" in m or "포인트" in m for m in matches), \
            f"%p 가 소실됨: matches={matches}"
        assert matches, "매칭 결과 없음"
        # 정확히 '0.5%p' 형태여야 함
        assert any("0.5%p" in m or "0.5" in m for m in matches), f"got: {matches}"

    def test_negative_sign_preserved(self):
        """-3.2% 급락 — 부호(방향) 소실 버그 수정 확인."""
        matches = [m.group(0).strip() for m in _FIGURE_RE.finditer("-3.2% 급락했습니다")]
        assert matches, "매칭 결과 없음"
        first = matches[0]
        assert first.startswith("-"), f"부호 소실: '{first}'"

    def test_index_level_line_matched(self):
        """코스피 3,200선 — '선' 단위 미매칭 버그 수정 확인."""
        matches = [m.group(0).strip() for m in _FIGURE_RE.finditer("코스피 3,200선을 돌파했습니다")]
        assert matches, "코스피 '선' 표현이 매칭되지 않음"
        assert any("선" in m for m in matches), f"'선' 없는 결과: {matches}"

    def test_positive_sign_optional(self):
        """+5% 도 매칭되어야 함."""
        matches = [m.group(0).strip() for m in _FIGURE_RE.finditer("+5% 상승")]
        assert matches, "+5% 매칭 실패"

    def test_no_sign_still_matches(self):
        """부호 없는 10조 원도 정상 매칭."""
        matches = [m.group(0).strip() for m in _FIGURE_RE.finditer("10조 원 규모")]
        assert any("10조" in m or "조" in m for m in matches), f"got: {matches}"


class TestFictionalize:
    def test_seed_lookup(self):
        assert _fictionalize("SK하이닉스") == "SEMI CORP K"

    def test_sector_fallback_ev(self):
        label = _fictionalize("현대자동차")
        assert "EV" in label or "AUTOMAKER" in label or "CORP" in label, \
            f"업종 폴백 실패: {label}"

    def test_sector_fallback_battery(self):
        label = _fictionalize("LG에너지솔루션")
        assert label == "BATTERY CORP K", f"got: {label}"

    def test_unknown_fallback_has_corp(self):
        label = _fictionalize("알 수 없는 가상 기업명")
        assert "CORP" in label, f"최종 폴백에 CORP 없음: {label}"

    def test_new_seed_llg_energy(self):
        assert "BATTERY" in _fictionalize("LG에너지솔루션") or "CORP" in _fictionalize("LG에너지솔루션")


class TestExtractFigures:
    def test_extracts_pct_point(self):
        figs = _extract_figures("금리가 0.5%p 인상됐습니다")
        assert figs, "수치 추출 실패"
        assert any("p" in f["raw"] or "포인트" in f["raw"] for f in figs), \
            f"%p 미포함: {figs}"

    def test_direction_down(self):
        figs = _extract_figures("-3.2% 급락했습니다")
        assert figs
        assert figs[0]["direction"] == "down", f"방향 오류: {figs[0]}"

    def test_direction_up_from_context(self):
        figs = _extract_figures("지수가 5% 상승했습니다")
        assert figs
        assert figs[0]["direction"] == "up", f"방향 오류: {figs[0]}"

    def test_index_line(self):
        figs = _extract_figures("코스피가 3,200선을 넘었습니다")
        assert figs, "코스피 선 미추출"
        assert any(f["kind"] == "index_level" for f in figs), f"종류 오류: {figs}"


class TestBindSceneEntities:
    def test_pipeline_disconnected_no_import_error(self):
        """파이프라인 미연결 상태에서 독립 실행 가능해야 함."""
        sections = [
            {"scene_id": "s0", "content": "SK하이닉스 ADR이 10% 급락했습니다."},
            {"scene_id": "s1", "content": "코스피 3,200선을 하회했습니다."},
        ]
        verified_facts = [{"keyword": "SK하이닉스", "keywords": ["ADR", "반도체"]}]
        keyword_news = [{"title": "SK하이닉스 실적 쇼크", "summary": "ADR 급락"}]
        bindings = bind_scene_entities(sections, verified_facts, keyword_news)
        assert len(bindings) == 2
        b0 = bindings[0]
        assert "SK하이닉스" in b0.core_entities, f"엔티티 추출 실패: {b0.core_entities}"
        assert b0.narration_hash  # SHA-256 기록 확인
        assert b0.has_news_evidence, "뉴스 근거 미탐지"

    def test_narration_unchanged(self):
        """바인딩 후 narration 원문이 변경되지 않아야 함."""
        original = "SK하이닉스 ADR이 10% 급락했습니다."
        sections = [{"scene_id": "s0", "content": original}]
        bindings = bind_scene_entities(sections, [], [])
        assert bindings[0].narration == original, "narration 원문 변경됨!"


class TestComputeGroundingScore:
    def test_entity_in_prompt(self):
        score = compute_grounding_score("SEMI CORP K stock chart crashed", ["SK하이닉스"])
        assert score == 1.0, f"fictionalized label 미탐지: {score}"

    def test_no_entities_returns_one(self):
        assert compute_grounding_score("some prompt", []) == 1.0

    def test_partial_match(self):
        score = compute_grounding_score("SEMI CORP K mentioned", ["SK하이닉스", "테슬라"])
        assert 0.0 < score < 1.0, f"부분 매칭 오류: {score}"


@pytest.mark.parametrize("narration", [
    "기업은 성장합니다.", "수익은 늘었습니다.", "질문은 이것입니다.",
    "전문가들은 경고합니다.", "코스닥은 반등했습니다.", "실적은 좋습니다.",
    "현금 흐름을 봅시다.", "지금 투자할까요?", "금리는 높습니다.",
    "은행 대출금과 연금", "백금 가격 상승", "조금 낮은 수익",
])
def test_particles_and_compound_syllables_are_not_commodities(narration):
    entities = _extract_entities(narration, [])
    assert "금" not in entities
    assert "은" not in entities


@pytest.mark.parametrize("narration,expected", [
    ("금 가격과 은 가격을 비교합니다.", {"금", "은"}),
    ("금은 상승하고 은은 하락했습니다.", {"금", "은"}),
    ("금과 은을 매수했습니다.", {"금", "은"}),
    ("은으로 만든 반지와 금의 가치", {"금", "은"}),
    ("금값과 은값 상승", {"금", "은"}),
    ("금선물은 상승, 은현물은 하락", {"금", "은"}),
    ("금/은", {"금", "은"}),
    ("백금은 상승했습니다.", set()),
])
def test_independent_commodity_nouns_and_explicit_compounds_survive(narration, expected):
    assert set(_extract_entities(narration, [])) & {"금", "은"} == expected


@pytest.mark.parametrize("text,entity,expected", [
    ("SK 하이닉스의 실적", "SK하이닉스", True),
    ("삼성전자는 성장했습니다.", "삼성전자", True),
    ("코스피에서는 반등", "코스피", True),
    ("코스닥에서도 상승", "코스닥", True),
    ("ETF인 겁니다.", "ETF", True),
    ("ＰＥＲ은 낮습니다.", "PER", True),
    ("SUPER COMPUTER", "PER", False),
    ("ETF가 성장", "ETF", True),
    ("BANKS", "BANK", False),
    ("삼성전자우는 상승", "삼성전자", False),
    ("삼성전자 우선주", "삼성전자", True),
])
def test_entity_boundary_and_spacing(text, entity, expected):
    assert entity_is_mentioned(text, entity) is expected


def test_verified_candidate_also_requires_boundaries():
    assert "PER" not in _extract_entities("SUPER COMPUTER", [{"entity": "PER"}])


def test_news_evidence_cannot_match_particle_or_compound():
    binding = bind_scene_entities([{"content": "은 가격 상승"}], [], [
        {"title": "기업은 성장하고 은행은 대출을 늘립니다."}
    ])[0]
    assert binding.core_entities == ["은"]
    assert not binding.has_news_evidence


def test_grounding_score_uses_same_boundaries():
    assert compute_grounding_score("지금 기업은 성장", ["금", "은"]) == 0


def test_fixed_binding_preserves_narration_and_hash():
    narration = "지금 기업은 현금 10조 원을 보유했습니다. SK 하이닉스의 실적은?"
    binding = bind_scene_entities([{"content": narration}], [], [])[0]
    assert binding.narration == narration
    assert binding.narration_hash == hashlib.sha256(narration.encode()).hexdigest()
    assert "금" not in binding.fictionalized_labels
    assert "은" not in binding.fictionalized_labels
    assert "SK하이닉스" in binding.core_entities

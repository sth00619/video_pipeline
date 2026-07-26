import pytest

from app.services.overlay.editorial_overlay import OverlaySlot
from app.services.overlay.plans import CopyClaim
from app.services.thumbnail.v2.narrative_plan import ThumbnailNarrativePlan
from app.services.thumbnail.v2.narrative_plan import build_from_video_manifest


def test_question_candidate_requires_gradient_burst_and_fact_candidate_requires_fact():
    with pytest.raises(ValueError, match="gradient burst"):
        ThumbnailNarrativePlan(
            pattern_id="P3", candidate_kind="question", source_scene_ids=["s1"],
            decision_hook=CopyClaim(text="왜 지금일까", claim_type="derived_hook", source_refs=["facts[0]"]),
            rationale="장면의 질문과 시청자 판단을 연결합니다.",
        )
    with pytest.raises(ValueError, match="fact_anchor"):
        ThumbnailNarrativePlan(
            pattern_id="P2", candidate_kind="fact", source_scene_ids=["s1"],
            decision_hook=CopyClaim(text="무엇이 바뀌나", claim_type="derived_hook", source_refs=["facts[0]"]),
            rationale="검증된 수치가 장면의 핵심 대상에 연결됩니다.",
        )


def test_question_candidate_has_traceable_overlay_grammar():
    plan = ThumbnailNarrativePlan(
        pattern_id="P3", candidate_kind="question", source_scene_ids=["s1"],
        decision_hook=CopyClaim(text="왜 지금일까", claim_type="derived_hook", source_refs=["facts[0]"]),
        overlays=[OverlaySlot(kind="burst", text="왜 지금일까?", claim_type="derived_hook", source_refs=["facts[0]"], text_style="gradient")],
        rationale="갈림길 장면의 질문과 시청자 판단을 연결합니다.",
    )
    assert plan.overlays[0].text_style == "gradient"


def test_manifest_builder_keeps_numeric_copy_traceable_and_uses_video_scene_ids():
    plan = build_from_video_manifest(
        keyword="semiconductor outlook",
        sections=[{"scene_id": "intro-1", "phase": "intro"}, {"scene_id": "data-2", "phase": "data"}],
        verified_facts=[{"figure": "12.5%", "source": "official"}],
    )
    assert plan.pattern_id == "P2"
    assert plan.source_scene_ids == ["intro-1", "data-2"]
    assert plan.fact_anchor and plan.fact_anchor.source_refs == ["facts[0]"]
    assert plan.overlays[0].kind == "metaphor_label"

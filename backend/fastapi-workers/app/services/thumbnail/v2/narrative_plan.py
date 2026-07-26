"""Video-grounded thumbnail narrative contract.

The plan deliberately contains copy/overlay intent, not model prompts. A
renderer can therefore explain why a recommendation exists and retain the
scene/fact provenance after selection.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.overlay.editorial_overlay import OverlaySlot
from app.services.overlay.plans import CopyClaim


def build_from_video_manifest(
    *,
    keyword: str,
    sections: list[dict],
    verified_facts: list[dict],
) -> "ThumbnailNarrativePlan":
    """Make one traceable recommendation from the completed video manifest.

    This deliberately selects only scene IDs already present in the video and
    reserves readable copy for the deterministic overlay renderer.  The image
    model therefore never has to spell Korean or reproduce a numeric fact.
    """
    source_scene_ids: list[str] = []
    for index, section in enumerate(sections):
        phase = str(section.get("phase") or section.get("section") or "")
        if index == 0 or phase in {"data", "scenario", "action", "conclusion"}:
            source_scene_ids.append(str(section.get("scene_id") or section.get("id") or index))
        if len(source_scene_ids) == 3:
            break
    source_scene_ids = source_scene_ids or ["0"]
    hook = (keyword or "핵심 변수를 확인하세요").strip()[:24]
    fact_index = next(
        (index for index, fact in enumerate(verified_facts or [])
         if any(char.isdigit() for char in str(fact.get("figure") or fact.get("value") or ""))),
        None,
    )
    if fact_index is not None:
        fact = verified_facts[fact_index]
        value = str(fact.get("figure") or fact.get("value") or "").strip()[:24]
        reference = f"facts[{fact_index}]"
        fact_claim = CopyClaim(text=value, claim_type="verbatim_fact", source_refs=[reference])
        return ThumbnailNarrativePlan(
            pattern_id="P2",
            candidate_kind="fact",
            source_scene_ids=source_scene_ids,
            decision_hook=CopyClaim(text=hook, claim_type="derived_hook", source_refs=[reference]),
            fact_anchor=fact_claim,
            overlays=[OverlaySlot(
                kind="metaphor_label", text=value, claim_type="verbatim_fact",
                source_refs=[reference], anchor="target", target_bbox=(.48, .18, .28, .16),
                text_style="outline", tone="warning",
            )],
            rationale="검증된 수치를 장면의 데이터 표면에만 배치해 영상 근거와 추천 썸네일을 연결합니다.",
        )
    return ThumbnailNarrativePlan(
        pattern_id="P3",
        candidate_kind="question",
        source_scene_ids=source_scene_ids,
        decision_hook=CopyClaim(text=hook, claim_type="derived_hook", source_refs=[f"scene:{source_scene_ids[0]}"]),
        overlays=[OverlaySlot(
            kind="burst", text="지금 확인할 변수?", claim_type="derived_hook",
            source_refs=[f"scene:{source_scene_ids[0]}"], anchor="upper_left", text_style="gradient", tone="warning",
        )],
        rationale="수치 근거가 없는 경우에는 사실처럼 보이는 숫자 대신 질문형 훅으로 안전하게 호기심을 만듭니다.",
    )


class ThumbnailNarrativePlan(BaseModel):
    schema_version: Literal[1] = 1
    pattern_id: Literal["P1", "P2", "P3", "P4", "P5", "P6", "P8"]
    candidate_kind: Literal["question", "fact", "result"]
    source_scene_ids: list[str] = Field(min_length=1, max_length=3)
    decision_hook: CopyClaim
    fact_anchor: CopyClaim | None = None
    overlays: list[OverlaySlot] = Field(default_factory=list, max_length=2)
    rationale: str = Field(min_length=12, max_length=240)

    @model_validator(mode="after")
    def candidate_grammar(self):
        if self.candidate_kind == "question":
            if not any(item.kind == "burst" and item.text_style == "gradient" for item in self.overlays):
                raise ValueError("question candidate requires gradient burst")
        if self.candidate_kind == "fact" and not self.fact_anchor:
            raise ValueError("fact candidate requires fact_anchor")
        if self.candidate_kind == "result" and sum(bool(any(char.isdigit() for char in item.text)) for item in self.overlays) > 1:
            raise ValueError("result candidate permits at most one numeric overlay")
        return self

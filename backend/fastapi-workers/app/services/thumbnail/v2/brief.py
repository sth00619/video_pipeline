"""Validated v2 thumbnail contract; coordinates are renderer-owned."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .semantic_emphasis import SemanticEmphasis
from .typography import HeadlineLineV3, Span
from app.services.overlay.editorial_overlay import OverlaySlot

Tone = Literal["white", "yellow", "red"]
TemplateId = Literal[
    "person_headline",
    "mascot_headline",
    "chart_warning",
    "article_evidence",
    "product_earnings",
]


class HeadlineLine(BaseModel):
    """Headline input expressed as independently styled text spans.

    ``text`` remains as an API/display convenience, but new planners must
    provide ``spans``.  Rendering always uses the span representation, so a
    single whole-line tone can no longer bypass the typography contract.
    """
    text: str | None = Field(default=None, min_length=2, max_length=32)
    tone: Tone = "white"
    spans: list[Span] | None = None

    @model_validator(mode="after")
    def requires_copy(self) -> "HeadlineLine":
        if not self.text and not self.spans:
            raise ValueError("headline line requires text or spans")
        if self.spans:
            span_text = "".join(span.text for span in self.spans)
            if self.text and self.text != span_text:
                raise ValueError("headline text must match concatenated spans")
            self.text = span_text
        return self

    def to_v3(self) -> HeadlineLineV3:
        return HeadlineLineV3(spans=self.spans or [Span(text=self.text or "", tone=self.tone)])


class Subject(BaseModel):
    kind: Literal["person", "article", "chart", "product"]
    asset_id: str = Field(min_length=1)
    source_ref: str | None = None


class MascotPolicy(BaseModel):
    allowed: bool = False
    emotion: Literal["neutral", "highlight", "surprised", "worried", "happy"] = "neutral"
    prop: str | None = None


class Evidence(BaseModel):
    source_url: str = Field(min_length=8)
    quote: str = Field(min_length=2, max_length=240)
    source_ref: str = Field(min_length=1)
    publisher: str = Field(min_length=1)


class Badge(BaseModel):
    label: str = Field(min_length=1, max_length=24)
    value: str = Field(min_length=1, max_length=40)
    source_ref: str = Field(min_length=1)


class ThumbnailBriefV2(BaseModel):
    template: TemplateId
    language: Literal["ko-KR"] = "ko-KR"
    headline: list[HeadlineLine] = Field(min_length=2, max_length=4)
    primary_subject: Subject
    secondary_subject: MascotPolicy = Field(default_factory=MascotPolicy)
    evidence: Evidence | None = None
    badge: Badge | None = None
    semantic_emphasis: SemanticEmphasis | None = None
    speech_bubble: str | None = Field(default=None, max_length=24)
    editorial_overlays: list[OverlaySlot] = Field(default_factory=list, max_length=2)
    pattern_id: str | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def template_requirements(self) -> "ThumbnailBriefV2":
        if self.template == "article_evidence" and not self.evidence:
            raise ValueError("article_evidence 템플릿은 evidence가 필수입니다")
        if self.template == "person_headline" and self.primary_subject.kind != "person":
            raise ValueError("person_headline 템플릿의 주 피사체는 person이어야 합니다")
        if self.template == "product_earnings" and not self.badge:
            raise ValueError("product_earnings 템플릿은 badge가 필수입니다")
        if self.template not in {"chart_warning", "mascot_headline"} and self.secondary_subject.allowed:
            raise ValueError("마스코트는 mascot_headline 또는 chart_warning 템플릿에서만 허용됩니다")
        if self.template == "mascot_headline" and not self.secondary_subject.allowed:
            raise ValueError("mascot_headline 템플릿은 선택된 채널 캐릭터가 필수입니다")
        return self


BANNED_PHRASES = ("경제 사냥꾼", "우리 진짜 다 같이 부자되자")


def validate_brief(brief: ThumbnailBriefV2, verified_facts: list[dict] | None = None, narration: str = "") -> list[str]:
    """Return gate errors; renderers must not silently repair editorial copy."""
    errors: list[str] = []
    joined = " ".join(item.text for item in brief.headline)
    for phrase in BANNED_PHRASES:
        if phrase in joined:
            errors.append(f"banned phrase: {phrase}")
    span_chars = 0
    highlighted_chars = 0
    for line in brief.headline:
        # Legacy records did not contain spans. They stay renderable during
        # migration, while every newly planned line is held to the cap.
        if not line.spans:
            continue
        for span in line.to_v3().spans:
            count = sum(not character.isspace() for character in span.text)
            span_chars += count
            if span.tone in {"yellow", "red"}:
                highlighted_chars += count
    if span_chars and highlighted_chars / span_chars > .60:
        errors.append("headline highlight spans exceed 60 percent of copy")
    refs = {
        reference
        for index, _ in enumerate(verified_facts or [])
        for reference in (f"facts[{index}]", f"verified_facts[{index}]")
    }
    for reference in [brief.badge.source_ref if brief.badge else None, brief.evidence.source_ref if brief.evidence else None]:
        if reference and refs and reference not in refs:
            errors.append(f"unverified source_ref: {reference}")
    if brief.semantic_emphasis:
        reference = brief.semantic_emphasis.reason_ref
        if refs and reference not in refs:
            errors.append(f"unverified semantic emphasis reason_ref: {reference}")
    # `asset_id` is a registry key, not necessarily the public person's name.
    # The registry approval gate is authoritative for image use; narration-name
    # matching belongs to the planner before it picks a person record.
    return errors

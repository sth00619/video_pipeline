"""Pydantic contracts for captured, attributable article evidence.

Coordinates are always normalised to the rendered image (0..1).  Keeping this
contract separate from the scene prompt prevents an LLM from inventing pixel
positions or financial labels.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class NormalizedBBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def stays_inside_canvas(self) -> "NormalizedBBox":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("normalized bbox must remain inside the canvas")
        return self

    def as_list(self) -> list[float]:
        return [self.x, self.y, self.width, self.height]

    @classmethod
    def from_list(cls, value: list[float] | tuple[float, float, float, float]) -> "NormalizedBBox":
        if len(value) != 4:
            raise ValueError("bbox must contain x, y, width, height")
        return cls(x=value[0], y=value[1], width=value[2], height=value[3])


class ArticleCapture(BaseModel):
    schema_version: int = 2
    source_url: str
    source_title: str = ""
    publisher: str = ""
    published_at: str | None = None
    captured_at: datetime
    capture_mode: Literal["dom", "pdf", "user_image"]
    quote: str = Field(min_length=1)
    image_sha256: str = Field(min_length=64, max_length=64)
    target_bbox: NormalizedBBox
    quote_bboxes: list[NormalizedBBox] = Field(default_factory=list)
    # V2 separates source geometry by meaning.  A key phrase is measured with
    # its own DOM Range and is never approximated from the first quote line.
    key_phrase: str | None = None
    key_phrase_bboxes: list[NormalizedBBox] = Field(default_factory=list)
    title_text_bbox: NormalizedBBox | None = None
    source_bbox: NormalizedBBox | None = None
    article_container_bbox: NormalizedBBox | None = None
    bbox_source: Literal["dom_range", "pdf_text", "ocr_estimate"] = "dom_range"
    approval_required: bool = False
    local_path: str | None = None
    object_key: str | None = None


class EvidenceAnnotation(BaseModel):
    type: Literal["underline", "ellipse", "rect", "dashed_ellipse", "arrow", "highlighter"]
    bbox: NormalizedBBox | None = None
    bboxes: list[NormalizedBBox] = Field(default_factory=list)
    from_xy: tuple[float, float] | None = None
    to_xy: tuple[float, float] | None = None
    color: str = "#E60023"
    stroke_width: int = Field(default=8, ge=1, le=48)

    @model_validator(mode="after")
    def validate_geometry(self) -> "EvidenceAnnotation":
        if self.type == "underline" and not (self.bboxes or self.bbox):
            raise ValueError("underline requires bbox or bboxes")
        if self.type == "arrow" and (self.from_xy is None or self.to_xy is None):
            raise ValueError("arrow requires from_xy and to_xy")
        if self.type not in {"underline", "arrow"} and self.bbox is None:
            raise ValueError(f"{self.type} requires bbox")
        return self


class CalloutSpec(BaseModel):
    text: str = Field(min_length=1, max_length=120)
    style: Literal["red_block"] = "red_block"
    placement: Literal["auto", "top_left", "top_right", "bottom_left", "bottom_right"] = "auto"
    anchor: tuple[float, float] | None = None


class EvidenceCaptureRequest(BaseModel):
    job_id: int = Field(ge=0)
    source_url: str = Field(min_length=8, max_length=2048)
    quote: str = Field(min_length=2, max_length=1000)
    source_title: str = ""
    publisher: str = ""
    published_at: str | None = None
    key_phrase: str | None = Field(default=None, max_length=240)
    # v2 keeps the legacy URL fields readable while requiring an attributable
    # Korean publisher whenever the allow-list policy is enabled.
    source: "ArticleSource | None" = None

    @field_validator("source_url")
    @classmethod
    def http_url_only(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("source_url must use http or https")
        return value


class ArticleSource(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    publisher: str = Field(min_length=1, max_length=120)
    language: Literal["ko"] = "ko"


class QuoteCardRequest(BaseModel):
    job_id: int = Field(ge=0)
    quote: str = Field(min_length=2, max_length=1000)
    publisher: str = Field(min_length=1, max_length=200)
    published_at: str = Field(min_length=4, max_length=40)
    source_url: str = ""
    canvas_size: tuple[int, int] = (1920, 1080)


class ArticleCandidate(BaseModel):
    title: str
    url: str
    publisher: str = ""
    published_at: str | None = None
    summary: str = ""
    score: float = 0.0
    matched_terms: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

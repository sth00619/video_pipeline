from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TimelineEntry(BaseModel):
    date_label: str = Field(min_length=1, max_length=20)
    lines: list[str] = Field(min_length=1, max_length=5)
    source_refs: list[str] = Field(min_length=1)
    emphasis_line_range: tuple[int, int] | None = None

    @field_validator("lines")
    @classmethod
    def concise_lines(cls, value: list[str]) -> list[str]:
        if any(len(line) > 18 for line in value):
            raise ValueError("timeline line must be 18 characters or less")
        return value


class TimelineCardSpec(BaseModel):
    kind: Literal["timeline"] = "timeline"
    entries: list[TimelineEntry] = Field(min_length=2, max_length=4)


class BulletListCardSpec(BaseModel):
    kind: Literal["bullet_list"] = "bullet_list"
    title: str = Field(min_length=2, max_length=28)
    bullets: list[str] = Field(min_length=3, max_length=5)
    source_refs: list[str] = Field(min_length=1)
    emphasis_index: int | None = None

    @field_validator("bullets")
    @classmethod
    def concise_bullets(cls, value: list[str]) -> list[str]:
        if any(len(line) > 24 for line in value):
            raise ValueError("bullet list line must be 24 characters or less")
        return value

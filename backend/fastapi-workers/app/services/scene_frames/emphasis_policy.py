"""Typed editorial-emphasis policy for article evidence scenes.

One body target receives exactly one policy.  In particular, a red underline
and a red rectangle cannot be requested together; the only combined treatment
is a fluorescent highlight followed by an opaque red underline.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class TitleEmphasis(str, Enum):
    RECT_TEXT_EXTENT = "rect_text_extent"
    NONE = "none"


class BodyEmphasis(str, Enum):
    UNDERLINE = "underline"
    RECT = "rect"
    HIGHLIGHT = "highlight"
    HIGHLIGHT_UNDERLINE = "highlight_underline"


class EmphasisPlan(BaseModel):
    title: TitleEmphasis = TitleEmphasis.RECT_TEXT_EXTENT
    # Deliberately required.  The renderer must not invent an editorial style.
    body: BodyEmphasis


def plan_from_scene(raw: object) -> EmphasisPlan:
    """Validate a scene-owned plan, retaining one explicit legacy migration.

    Old in-flight jobs have no policy field.  Their migration is made here,
    outside the renderer, so new callers still have to provide a body policy.
    """
    if isinstance(raw, EmphasisPlan):
        return raw
    if isinstance(raw, dict) and raw:
        return EmphasisPlan.model_validate(raw)
    return EmphasisPlan(body=BodyEmphasis.HIGHLIGHT_UNDERLINE)

"""Evidence-linked editorial markings for thumbnail imagery.

The old renderer drew decorative arrows, charts and circles even when no
source fact existed.  This contract makes a visual emphasis an auditable
editorial decision: it needs a target, a fact reference and, for arrows, an
explicit source anchor.
"""
from __future__ import annotations

import hashlib
import random
from typing import Literal

from PIL import Image, ImageDraw
from pydantic import BaseModel, Field, model_validator


class NormalizedBBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_canvas(self) -> "NormalizedBBox":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("semantic target must stay inside normalized canvas")
        return self


class SemanticEmphasis(BaseModel):
    kind: Literal["circle", "underline", "arrow"]
    target: NormalizedBBox
    # Identifies what the coordinates refer to (for example a verified chart
    # or an evidence text span).  It is provenance, not copy to render.
    target_asset_id: str = Field(default="scene_target", min_length=1)
    reason_ref: str = Field(min_length=1)
    direction_claim: Literal["up", "down"] | None = None
    # ``source`` is mandatory for arrows so they cannot be arbitrary direction
    # graphics. For other marks it is intentionally omitted.
    source: NormalizedBBox | None = None
    source_anchor: Literal["subject", "evidence", "chart", "headline"] | None = None

    @model_validator(mode="after")
    def arrow_needs_source(self) -> "SemanticEmphasis":
        if self.kind == "arrow" and not (self.source or self.source_anchor):
            raise ValueError("arrow emphasis requires source or source_anchor")
        if self.kind != "arrow" and (self.source or self.source_anchor):
            raise ValueError("only arrow emphasis may define a source")
        return self


def _box(value: NormalizedBBox, size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    return (
        round(value.x * width), round(value.y * height),
        round((value.x + value.width) * width), round((value.y + value.height) * height),
    )


def _jitter(seed: str, amount: int = 3) -> random.Random:
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16) + amount)


def _anchor_box(name: str, anchors: dict[str, dict[str, int]], size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    region = anchors.get(name)
    if not region:
        return None
    x, y = int(region["x"]), int(region["y"])
    return x, y, x + int(region["width"]), y + int(region["height"])


def draw_semantic_emphasis(
    canvas: Image.Image,
    emphasis: SemanticEmphasis | None,
    anchors: dict[str, dict[str, int]] | None = None,
) -> list[dict[str, object]]:
    """Draw zero or one fact-referenced mark and return its QA provenance."""
    if emphasis is None:
        return []
    anchors = anchors or {}
    target = _box(emphasis.target, canvas.size)
    seed = f"{emphasis.kind}:{emphasis.reason_ref}:{target}"
    rng = _jitter(seed)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    red = (233, 36, 31, 255)
    width = max(5, canvas.width // 230)

    if emphasis.kind == "underline":
        start = (target[0], target[3] + width)
        end = (target[2], target[3] + width)
        points = [start]
        steps = max(4, (end[0] - start[0]) // 60)
        for i in range(1, steps):
            x = round(start[0] + (end[0] - start[0]) * i / steps)
            points.append((x, start[1] + rng.randint(-2, 2)))
        points.append(end)
        draw.line(points, fill=red, width=width, joint="curve")
    elif emphasis.kind == "circle":
        padded = (target[0] - width * 2, target[1] - width * 2, target[2] + width * 2, target[3] + width * 2)
        # Non-perfect segmented arcs retain an editorial pen mark without
        # becoming a generic decorative ring.
        for start in range(0, 360, 30):
            draw.arc(padded, start + rng.randint(-3, 3), start + 20 + rng.randint(-2, 3), fill=red, width=width)
    else:
        source = _box(emphasis.source, canvas.size) if emphasis.source else _anchor_box(emphasis.source_anchor or "", anchors, canvas.size)
        if source is None:  # model validation should prevent this; keep hard fail.
            raise ValueError("SEMANTIC_ARROW_SOURCE_MISSING")
        start = ((source[0] + source[2]) // 2, (source[1] + source[3]) // 2)
        end = ((target[0] + target[2]) // 2, (target[1] + target[3]) // 2)
        bend = ((start[0] + end[0]) // 2 + rng.randint(-30, 30), (start[1] + end[1]) // 2 + rng.randint(-30, 30))
        draw.line([start, bend, end], fill=red, width=width, joint="curve")
        # Deterministic, short arrow head; it describes the relation only.
        dx, dy = end[0] - bend[0], end[1] - bend[1]
        norm = max(1, (dx * dx + dy * dy) ** .5)
        ux, uy = dx / norm, dy / norm
        px, py = -uy, ux
        head = max(16, width * 3)
        draw.polygon(
            [end, (round(end[0] - ux * head + px * head * .55), round(end[1] - uy * head + py * head * .55)),
             (round(end[0] - ux * head - px * head * .55), round(end[1] - uy * head - py * head * .55))],
            fill=red,
        )
    canvas.alpha_composite(layer)
    return [{
        "kind": emphasis.kind,
        "target": target,
        "target_asset_id": emphasis.target_asset_id,
        "reason_ref": emphasis.reason_ref,
        "direction_claim": emphasis.direction_claim,
    }]

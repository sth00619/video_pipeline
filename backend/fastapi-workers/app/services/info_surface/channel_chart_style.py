"""Channel-owned cartoon ink renderer for physical information surfaces.

This renderer intentionally avoids dashboard grammar.  A surface carries one
large verified statistic, a directional cue, one meaning line, and at most two
support marks.  It is transparent so the compositor can preserve the real
paper, chalkboard, or monitor material beneath it.
"""
from __future__ import annotations

from hashlib import sha256
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw

from .channel_typography import draw_display_text
from .hero_stat import HeroStatPlan, hero_stat_from_chart
from .ink_primitives import ink_arrow, ink_bar, ink_line, ink_underline, seeded_rng
from .cartoon_ink_qc import require_panel_palette, require_type_minima


INK = "#071A3A"
CREAM = "#FFF4D6"
YELLOW = "#F6BE28"
RED = "#C94B3C"
PAPER_GRAY = "#A99F8A"


@dataclass(frozen=True)
class ChartRenderOutput:
    image: Image.Image
    # x/y/width/height are in the renderer canvas. The compositor promotes
    # them to the Phase B crop contract after perspective placement.
    bars: list[dict[str, object]]


def _seed(chart: dict[str, Any]) -> int:
    explicit = chart.get("scene_seed")
    if explicit is not None:
        return int(explicit)
    stable = "|".join(str(chart.get(key) or "") for key in ("source_ref", "source", "label", "source_date"))
    return int.from_bytes(sha256(stable.encode("utf-8")).digest()[:4], "big")


def _fit_role(width: int, role: str) -> str:
    # A small surface cannot support poster-scale data.  The worker normally
    # moves it to a cutaway; this keeps direct helper callers deterministic.
    if role == "hero" and width < 330:
        return "support"
    return role


def _hero(chart: dict[str, Any]) -> HeroStatPlan:
    raw = chart.get("hero_stat")
    return HeroStatPlan.model_validate(raw) if isinstance(raw, dict) else hero_stat_from_chart(chart)


def _accent(plan: HeroStatPlan) -> str:
    return RED if plan.direction == "down" else YELLOW


def _draw_support_marks(image: Image.Image, hero: HeroStatPlan, width: int, height: int, rng) -> None:
    marks = hero.support_marks[:2]
    if not marks:
        return
    y = int(height * .71)
    slot = max(1, width // len(marks))
    scale = max(1.0, width / 720)
    for index, mark in enumerate(marks):
        center = slot * index + slot // 2
        # Supports are intentionally annotation-sized, never a second visual
        # hierarchy competing with the hero number.
        draw_display_text(image, (center, y), mark.value, role=_fit_role(width, "support"), fill=INK, align="center", scale=scale)
        draw_display_text(image, (center, y + int(35 * scale)), mark.label, role=_fit_role(width, "support"), fill=PAPER_GRAY, align="center", scale=scale)


def _draw_indexed_bars(image: Image.Image, chart: dict[str, Any], hero: HeroStatPlan, rng) -> list[dict[str, object]]:
    """Use two hand-inked bars as supporting evidence, not a widget chart."""
    values: list[tuple[str, float]] = []
    for item in list(chart.get("comparison_values") or [])[:2]:
        try:
            values.append((str(item["label"]), float(item["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    if len(values) < 2:
        return []
    draw = ImageDraw.Draw(image)
    width, height = image.size
    scale = max(1.0, width / 720)
    baseline = float(chart.get("comparison_baseline") if chart.get("comparison_baseline") is not None else values[0][1])
    high = max(value for _, value in values)
    low = min(value for _, value in values + [("basis", baseline)])
    span = max(1.0, high - low)
    bottom = int(height * .76)
    usable = int(height * .22)
    x_positions = (int(width * .12), int(width * .25))
    metadata: list[dict[str, object]] = []
    for index, ((label, value), x) in enumerate(zip(values, x_positions)):
        bar_height = max(int(height * .055), int(usable * ((value - low) / span)))
        fill = PAPER_GRAY if index == 0 else _accent(hero)
        rect = (x, bottom - bar_height, x + int(width * .09), bottom)
        ink_bar(draw, rect, fill=fill, outline=INK, outline_px=max(2, width // 105), rng=rng)
        draw_display_text(image, (x + int(width * .045), bottom + 5), label, role=_fit_role(width, "support"), fill=INK, align="center", scale=scale)
        metadata.append({"bbox": (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]), "value": value, "fill_rgb": tuple(int(fill[index:index + 2], 16) for index in (1, 3, 5))})
    return metadata


def render_chart_content(chart: dict[str, Any], size: tuple[int, int], *, return_metadata: bool = False) -> Image.Image | ChartRenderOutput:
    """Render verified data into a concise, comic-poster information grammar.

    A malformed indexed comparison raises ``ValueError``.  The caller must
    keep the original Phase-A result rather than silently present an index as
    an absolute market value.
    """
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    hero = _hero(chart)
    rng = seeded_rng(_seed(chart))
    accent = _accent(hero)
    require_panel_palette([INK, CREAM, PAPER_GRAY, accent])
    title = str(chart.get("label") or hero.headline_unit_label)
    scale = max(1.0, width / 720)
    # Callers that render at a supersampled size declare their final downscale
    # factor. A content panel then fails instead of silently shipping type
    # below the 1080p readability floor.
    final_scale = float(chart.get("final_output_scale", 1.0))
    require_type_minima({"hero": 66 * scale * final_scale, "title": 44 * scale * final_scale, "meaning": 30 * scale * final_scale})

    draw_display_text(image, (width // 2, int(height * .055)), title, role=_fit_role(width, "title"), fill=INK, align="center", scale=scale)
    # A long underline is a deliberate comic mark, rather than a card edge.
    ink_underline(draw, (int(width * .18), int(height * .20)), (int(width * .82), int(height * .20)), fill=accent, width=max(3, width // 115), rng=rng)

    headline_y = int(height * .27)
    draw_display_text(image, (width // 2, headline_y), hero.headline_value, role=_fit_role(width, "hero"), fill=accent, align="center", scale=scale)
    # 제목과 단위 라벨이 같으면 물리 소품 안에서 같은 문구를 반복하지 않는다.
    if hero.headline_unit_label.strip().casefold() != title.strip().casefold():
        draw_display_text(image, (width // 2, headline_y + int(height * .18)), hero.headline_unit_label, role=_fit_role(width, "support"), fill=INK, align="center", scale=scale)

    arrow_up = hero.direction != "down"
    start = (int(width * .76), int(height * (.62 if arrow_up else .47)))
    end = (int(width * .90), int(height * (.40 if arrow_up else .70)))
    if hero.direction and hero.direction != "flat":
        ink_arrow(draw, start, end, fill=accent, outline=INK, width=max(5, width // 72), rng=rng)

    bars: list[dict[str, object]] = []
    if str(chart.get("visual_kind") or "") == "indexed_comparison":
        bars = _draw_indexed_bars(image, chart, hero, rng)
    else:
        # One short trend stroke is enough to preserve time direction without
        # reverting to the dense date/tick dashboard grammar.
        points = [float(item.get("close")) for item in chart.get("points") or [] if item.get("close") is not None]
        if len(points) >= 2:
            sample = points[::max(1, len(points) // 4)]
            low, high = min(sample), max(sample)
            span = max(1e-6, high - low)
            path = [
                (int(width * (.12 + index * .12)), int(height * (.76 - ((value - low) / span) * .12)))
                for index, value in enumerate(sample[:5])
            ]
            ink_line(draw, path, fill=accent, width=max(3, width // 105), rng=rng)

    if str(chart.get("visual_kind") or "") != "indexed_comparison":
        _draw_support_marks(image, hero, width, height, rng)
    meaning = hero.meaning_line
    draw_display_text(image, (width // 2, int(height * .89)), meaning, role=_fit_role(width, "support"), fill=INK, align="center", scale=scale)
    return ChartRenderOutput(image=image, bars=bars) if return_metadata else image


def render_metric_summary(chart: dict[str, Any], size: tuple[int, int]) -> Image.Image:
    return render_chart_content(chart, size)

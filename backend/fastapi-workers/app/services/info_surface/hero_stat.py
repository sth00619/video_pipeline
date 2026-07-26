"""Poster-style factual contracts for deterministic information surfaces.

The chart payload remains the source of truth.  ``HeroStatPlan`` only selects
the one fact that deserves poster-scale emphasis and bounds any supporting
marks.  It deliberately cannot manufacture a value from narration text.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SupportMark(BaseModel):
    label: str = Field(min_length=1, max_length=20)
    value: str = Field(min_length=1, max_length=24)


class HeroStatPlan(BaseModel):
    headline_value: str = Field(min_length=1, max_length=28)
    headline_unit_label: str = Field(min_length=1, max_length=40)
    direction: Literal["up", "down", "flat"] | None = None
    meaning_line: str = Field(min_length=1, max_length=48)
    support_marks: list[SupportMark] = Field(default_factory=list, max_length=2)
    comparison_basis: str = Field(min_length=1, max_length=64)
    source_refs: list[str] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def require_a_real_basis(self):
        if not self.comparison_basis.strip():
            raise ValueError("comparison_basis is required for every hero statistic")
        if not all(item.strip() for item in self.source_refs):
            raise ValueError("source_refs cannot contain blank values")
        return self


def _direction(value: float) -> Literal["up", "down", "flat"]:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _number(value: object, precision: int = 1) -> str:
    numeric = float(value)
    return f"{numeric:,.{precision}f}"


def hero_stat_from_chart(chart: dict[str, Any]) -> HeroStatPlan:
    """Create a compact factual hierarchy from one verified chart payload.

    Indexed/comparison data is the dangerous case: a value such as ``107.0``
    is not an absolute market quote.  The producer must therefore supply a
    human-readable basis (for example ``2026-07-21 = 100``).  We fail closed
    when it is absent rather than render a materially misleading graphic.
    """
    source_ref = str(chart.get("source_ref") or chart.get("source") or "").strip()
    if chart.get("verified") is not True or not source_ref:
        raise ValueError("hero statistic requires a verified source reference")
    kind = str(chart.get("visual_kind") or "trend_dashboard")
    label = str(chart.get("label") or "verified metric").strip()

    if kind == "indexed_comparison":
        basis = str(chart.get("comparison_basis") or "").strip()
        if not basis:
            raise ValueError("indexed_comparison requires comparison_basis")
        parsed: list[tuple[str, float]] = []
        for item in list(chart.get("comparison_values") or [])[:4]:
            try:
                parsed.append((str(item["label"]), float(item["value"])))
            except (KeyError, TypeError, ValueError):
                continue
        if len(parsed) < 2:
            raise ValueError("indexed_comparison requires two verified values")
        baseline = float(chart.get("comparison_baseline") if chart.get("comparison_baseline") is not None else parsed[0][1])
        headline_label, headline = parsed[-1]
        change = headline - baseline
        supports = [SupportMark(label=name, value=_number(value)) for name, value in parsed[:-1][:2]]
        return HeroStatPlan(
            headline_value=_number(headline),
            headline_unit_label=f"index ({basis})",
            direction=_direction(change),
            meaning_line=f"{headline_label}: {change:+.1f} vs baseline",
            support_marks=supports,
            comparison_basis=basis,
            source_refs=[source_ref],
        )

    if kind == "supply_flow":
        entries = [(str(name), str(value)) for name, value in dict(chart.get("supply_demand") or {}).items() if str(value).strip()]
        if not entries:
            raise ValueError("supply_flow requires verified values")
        name, value = entries[0]
        return HeroStatPlan(
            headline_value=value,
            headline_unit_label=name,
            direction="down" if value.lstrip().startswith("-") else "up",
            meaning_line="verified investor flow",
            support_marks=[SupportMark(label=other_name, value=other_value) for other_name, other_value in entries[1:3]],
            comparison_basis=str(chart.get("source_date") or "verified collection date"),
            source_refs=[source_ref],
        )

    if kind == "stock_movers":
        movers = list(chart.get("movers") or [])
        if not movers:
            raise ValueError("stock_movers requires verified values")
        first = movers[0]
        pct = float(first["change_pct"])
        supports: list[SupportMark] = []
        for item in movers[1:3]:
            supports.append(SupportMark(label=str(item["name"]), value=f"{float(item['change_pct']):+.2f}%"))
        return HeroStatPlan(
            headline_value=f"{pct:+.2f}%",
            headline_unit_label=str(first["name"]),
            direction=_direction(pct),
            meaning_line="verified related-stock move",
            support_marks=supports,
            comparison_basis=str(chart.get("source_date") or "verified collection date"),
            source_refs=[source_ref],
        )

    latest = chart.get("latest")
    change = chart.get("change_pct")
    if latest is None or change is None:
        raise ValueError("hero statistic requires latest and change_pct")
    change_value = float(change)
    date = str(chart.get("source_date") or "").strip()
    return HeroStatPlan(
        headline_value=_number(latest, 2),
        headline_unit_label=label,
        direction=_direction(change_value),
        meaning_line=f"{change_value:+.2f}% over selected period",
        comparison_basis=date or "verified collection period",
        source_refs=[source_ref],
    )

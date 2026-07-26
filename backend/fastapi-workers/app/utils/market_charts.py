"""Exact market graphics, sized from the final in-scene surface.

The image model supplies a blank *landscape* prop.  This module owns every
visible number and renders at twice the final pixel size, so typography and
composition do not drift when FFmpeg places the final opaque graphic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import math


SERIES_LABELS = {
    "kospi": "KOSPI", "kosdaq": "KOSDAQ", "sp500": "S&P 500",
    "nasdaq": "NASDAQ", "dow": "DOW JONES", "vix": "VIX", "dxy": "DOLLAR INDEX",
}


def _valid_points(raw: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    points: list[dict[str, float | str]] = []
    for item in raw:
        try:
            points.append({"date": str(item["date"]), "close": float(item["close"])})
        except (KeyError, TypeError, ValueError):
            continue
    return points


def _selected_series(snapshot: dict[str, Any], text: str) -> tuple[str, list[dict[str, Any]]] | None:
    candidates: dict[str, list[dict[str, Any]]] = {}
    for market_key in ("kr", "us"):
        candidates.update((snapshot.get(market_key) or {}).get("chart_series") or {})
    lower = text.lower()
    # A time series is valid only when the narration explicitly names that
    # series.  Falling back to an arbitrary index made policy comparisons
    # (for example, two tariff rates) look like a fabricated time trend.
    preferred = [key for token, key in (
        ("kosdaq", "kosdaq"), ("kospi", "kospi"), ("nasdaq", "nasdaq"),
        ("s&p", "sp500"), ("sp500", "sp500"), ("dow", "dow"),
        ("vix", "vix"), ("dxy", "dxy"), ("dollar index", "dxy"),
    ) if token in lower]
    for key in preferred:
        series = candidates.get(key) or []
        if len(_valid_points(series)) >= 5:
            return key, series
    return None


def _market_cap_pie(snapshot: dict[str, Any]) -> list[dict[str, float | str]]:
    values: list[dict[str, float | str]] = []
    for stock in ((snapshot.get("kr") or {}).get("top_stocks") or [])[:5]:
        try:
            value = float(stock.get("market_cap_value"))
            if value > 0:
                values.append({"label": str(stock.get("name") or stock.get("symbol") or "종목"), "value": value})
        except (TypeError, ValueError):
            continue
    return values if len(values) >= 2 else []


def _verified_supply_demand(snapshot: dict[str, Any]) -> dict[str, str] | None:
    raw = ((snapshot.get("kr") or {}).get("supply_demand") or {}).get("kospi") or {}
    labels = {
        "외국인": raw.get("foreign_net_buy"),
        "기관": raw.get("institution_net_buy"),
        "개인": raw.get("retail_net_buy"),
    }
    values = {label: str(value) for label, value in labels.items() if value not in (None, "", "0", "+0원")}
    return values if len(values) >= 2 else None


def _verified_associated_movers(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw = ((snapshot.get("associated_data") or {}).get("associated_stocks") or [])
    movers: list[dict[str, Any]] = []
    for item in raw:
        try:
            close, change_pct = float(item.get("close")), float(item.get("change_pct"))
        except (TypeError, ValueError):
            continue
        if close <= 0:
            continue
        movers.append({"name": str(item.get("name") or item.get("symbol") or "종목"), "close": close, "change_pct": change_pct})
    return movers[:4]


def extract_market_chart(scene: dict[str, Any]) -> dict[str, Any] | None:
    """Build a chart only when every plotted value has a collector source."""
    if str(scene.get("section") or "") != "data":
        return None
    snapshot = scene.get("market_snapshot") or {}
    text = str(scene.get("content") or scene.get("text") or "")
    lower = text.lower()
    supply = _verified_supply_demand(snapshot)
    if supply and any(token in lower for token in ("수급", "외국인", "기관", "순매수", "개인")):
        return {
            "series_key": "supply_demand", "label": "KOSPI 수급", "visual_kind": "supply_flow",
            "supply_demand": supply, "source_date": str(((snapshot.get("kr") or {}).get("data_date") or "")),
            "source_ref": "market_snapshot.kr.supply_demand.kospi", "verified": True,
        }
    movers = _verified_associated_movers(snapshot)
    if movers and any(token in lower for token in ("관련주", "동반", "종목", "반도체", "주가", "상승률", "등락률")):
        return {
            "series_key": "associated_movers", "label": "관련 종목 등락", "visual_kind": "stock_movers",
            "movers": movers, "source_date": str(snapshot.get("collected_at") or "")[:10],
            "source_ref": "market_snapshot.associated_data.associated_stocks", "verified": True,
        }
    selected = _selected_series(snapshot, text)
    if not selected:
        return None
    key, raw = selected
    points = _valid_points(raw)[-30:]
    if len(points) < 5:
        return None
    start, end = float(points[0]["close"]), float(points[-1]["close"])
    bars = []
    for previous, current in zip(points[-6:-1], points[-5:]):
        before, now = float(previous["close"]), float(current["close"])
        bars.append({"label": str(current["date"])[5:], "value": round((now - before) / before * 100, 2) if before else 0.0})
    return {
        "series_key": key, "label": SERIES_LABELS.get(key, key.upper()), "points": points,
        "daily_change_bars": bars, "market_cap_pie": _market_cap_pie(snapshot),
        "change_pct": round((end - start) / start * 100, 2) if start else 0.0,
        "latest": end, "source_date": str(points[-1]["date"]),
        "source_ref": f"market_snapshot.chart_series.{key}",
    }


def _theme(chart: dict[str, Any]) -> dict[str, str]:
    return {
        # Keep data surfaces as a readable cartoon prop, not a neon dashboard:
        # white carries labels, yellow marks the one key value, red is reserved
        # for a downside/warning. This mirrors the reference hierarchy while
        # retaining our original mascot and scene artwork.
        "chalkboard": {"background": "#18232b", "text": "#ffffff", "note": "#e9e9e9", "edge": "#080b0e", "up": "#ffd230", "down": "#e5484d", "grid": "#d7d7d7"},
        "paper_poster": {"background": "#f4ead3", "text": "#171717", "note": "#4c4c4c", "edge": "#111111", "up": "#ffd230", "down": "#e5484d", "grid": "#767676"},
        "factory_panel": {"background": "#17212a", "text": "#ffffff", "note": "#dddddd", "edge": "#080b0e", "up": "#ffd230", "down": "#e5484d", "grid": "#cfcfcf"},
    }.get(str(chart.get("visual_theme") or "chalkboard"), {})


def _surface_size(chart: dict[str, Any]) -> tuple[int, int]:
    surface = chart.get("render_surface") or {}
    return max(360, int(surface.get("width", 720))), max(260, int(surface.get("height", 405)))


def _make_canvas(chart: dict[str, Any]):
    """Create a stable 2x canvas from final overlay pixels; never tight-crop."""
    import matplotlib.pyplot as plt
    width, height = _surface_size(chart)
    scale, dpi = 2, 200
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=dpi)
    # Kling may invent decorative lines inside the requested blank panel.  An
    # opaque renderer background fully replaces those generated marks so only
    # collected, verified data remains visible in the delivered frame.
    fig.patch.set_facecolor(_theme(chart)["background"])
    fig.patch.set_alpha(1)

    def font(height_fraction: float, minimum_px: float = 14, maximum_px: float = 42) -> float:
        # The surface proportion chooses the size, while screen-pixel caps
        # stop a tall panel from turning values into overlapping headlines.
        final_px = min(maximum_px, max(minimum_px, height * height_fraction))
        target_px = final_px * scale
        return max(9, target_px * 72 / dpi)

    return fig, width, height, font


def _save(fig, output_path: str) -> bool:
    # No bbox_inches='tight': every renderer preserves the exact canvas that
    # the FFmpeg surface calculation supplied.
    fig.savefig(output_path, transparent=False, pad_inches=0)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return Path(output_path).exists() and Path(output_path).stat().st_size > 4_000


def _render_cartoon_poster(chart: dict[str, Any], output_path: str) -> bool:
    """Opaque compatibility output using the same v3 cartoon ink grammar.

    Image-stage compositing is the normal path.  This function keeps older
    FFmpeg-only jobs visually consistent instead of sending them through the
    former dense matplotlib dashboard renderer.
    """
    from PIL import Image

    from app.services.info_surface.channel_chart_style import render_chart_content
    from app.services.info_surface.material_fx import apply_material_fx

    width, height = _surface_size(chart)
    scale = 2
    canvas_size = (width * scale, height * scale)
    theme = _theme(chart)
    background = Image.new("RGBA", canvas_size, theme["background"])
    content = render_chart_content({**chart, "final_output_scale": 1 / scale}, canvas_size)
    content = apply_material_fx(content, str(chart.get("surface_kind") or chart.get("visual_theme") or "paper"), chart.get("scene_seed"))
    background.alpha_composite(content)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    background.convert("RGB").save(output_path, "PNG")
    return Path(output_path).is_file() and Path(output_path).stat().st_size > 4_000


def _footer(fig, chart: dict[str, Any], theme: dict[str, str], font, height: int) -> None:
    text = f"검증 데이터 - {str(chart['source_date'])[5:]}" if height < 360 else f"수집 기준일 {chart['source_date']} - 검증 데이터만 표시"
    fig.text(.06, .035, text, color=theme["note"], fontsize=font(.035, 12, 16), fontproperties=_fonts()[0])


def _fonts():
    from matplotlib.font_manager import FontProperties
    # Use the bundled OFL font, not an incidental host font. Test runners and
    # containers therefore render the same Korean glyph set.
    bundled = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "BlackHanSans-Regular.ttf"
    profile = FontProperties(fname=str(bundled)) if bundled.is_file() else None
    return profile, profile


def render_market_chart(chart: dict[str, Any], output_path: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        kind = str(chart.get("visual_kind") or "trend_dashboard")
        if kind == "indexed_comparison":
            from app.services.info_surface.hero_stat import hero_stat_from_chart
            # Direct/offline rendering is also a strict boundary. A normalized
            # number without its basis may never be written to an image.
            hero_stat_from_chart(chart)
        # This is also used by the bounded legacy FFmpeg path. Keep every
        # supported factual visual in the same one-hero-stat cartoon language
        # as the in-world surface compositor.
        if kind in {
            "trend_dashboard", "chalkboard_explainer", "change_arrow",
            "composition_pie", "comparison", "indexed_comparison",
            "supply_flow", "stock_movers",
        }:
            return _render_cartoon_poster(chart, output_path)
        if kind == "chalkboard_explainer":
            return _render_chalkboard_explainer(chart, output_path)
        if kind == "change_arrow":
            return _render_change_arrow(chart, output_path)
        if kind == "composition_pie":
            return _render_composition_pie(chart, output_path)
        if kind == "comparison":
            return _render_market_cap_comparison(chart, output_path)
        if kind == "indexed_comparison":
            return _render_indexed_comparison(chart, output_path)
        if kind == "supply_flow":
            return _render_supply_flow(chart, output_path)
        if kind == "stock_movers":
            return _render_stock_movers(chart, output_path)
        return _render_trend_dashboard(chart, output_path)
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _render_chalkboard_explainer(chart: dict[str, Any], output_path: str) -> bool:
    """Render F6 as one opaque, hand-drawn cartoon chalkboard.

    This replaces every potentially hallucinated board mark from the image
    model.  The only visible values are sourced from ``chart`` and the layout
    deliberately keeps the mascot outside the board surface.
    """
    import matplotlib.pyplot as plt

    regular, bold = _fonts()
    chart = {**chart, "visual_theme": "chalkboard"}
    theme = _theme(chart)
    fig, _width, height, font = _make_canvas(chart)
    points = chart["points"]
    values = [float(point["close"]) for point in points]
    change = float(chart["change_pct"])
    accent = theme["up"] if change >= 0 else theme["down"]

    fig.text(.07, .90, f"{chart['label']} 핵심 흐름", color=theme["text"], fontsize=font(.07, 24, 38), fontproperties=bold)
    fig.text(.07, .835, "검증된 종가 데이터 - 최근 추이", color=theme["note"], fontsize=font(.035, 13, 18), fontproperties=regular)

    graph = fig.add_axes([.075, .23, .55, .52])
    graph.set_facecolor(theme["background"])
    x = list(range(len(values)))
    graph.plot(x, values, color=accent, linewidth=4.2, solid_capstyle="round")
    graph.fill_between(x, values, min(values), color=accent, alpha=.14)
    graph.scatter([x[-1]], [values[-1]], s=90, color="#f8ca4e", edgecolor=theme["edge"], linewidth=2.2, zorder=4)
    graph.grid(axis="y", color=theme["grid"], alpha=.30, linewidth=1.1, linestyle="--")
    graph.set_xticks([0, len(x) - 1])
    graph.set_xticklabels([str(points[0]["date"])[5:], str(points[-1]["date"])[5:]], color=theme["text"], fontsize=font(.036, 12, 16), fontproperties=regular)
    graph.tick_params(axis="y", colors=theme["text"], labelsize=font(.032, 11, 15), length=0)
    for spine in graph.spines.values():
        spine.set_color(theme["note"]); spine.set_linewidth(1.2)

    panel = fig.add_axes([.68, .26, .25, .47]); panel.axis("off")
    panel.text(.5, .82, "최신 종가", ha="center", color=theme["note"], fontsize=font(.046, 15, 21), fontproperties=regular)
    panel.text(.5, .61, f"{chart['latest']:,.2f}", ha="center", color=theme["text"], fontsize=font(.082, 27, 43), fontproperties=bold)
    panel.text(.5, .34, f"{'+' if change >= 0 else '-'} {abs(change):.2f}%", ha="center", color=accent, fontsize=font(.075, 24, 39), fontproperties=bold)
    panel.text(.5, .13, "기간 변화", ha="center", color=theme["note"], fontsize=font(.034, 12, 16), fontproperties=regular)
    panel.plot([.08, .92, .92, .08, .08], [.08, .08, .92, .92, .08], color=theme["note"], alpha=.75, linewidth=1.8)

    fig.text(.075, .11, "핵심: 숫자는 장면 생성 후 검증 데이터로 다시 그립니다.", color=theme["text"], fontsize=font(.037, 13, 18), fontproperties=bold)
    _footer(fig, chart, theme, font, height)
    return _save(fig, output_path)


def _render_trend_dashboard(chart: dict[str, Any], output_path: str) -> bool:
    import matplotlib.pyplot as plt
    regular, bold = _fonts(); theme = _theme(chart)
    fig, _, height, font = _make_canvas(chart)
    points = chart["points"]; values = [float(point["close"]) for point in points]
    bars = chart.get("daily_change_bars") or []
    line_ax = fig.add_axes([.08, .32 if bars else .16, .84, .53 if bars else .63])
    line_ax.set_facecolor((0, 0, 0, 0)); x = list(range(len(values)))
    accent = theme["up"] if float(chart["change_pct"]) >= 0 else theme["down"]
    # One decisive hand-drawn line is easier to read in a moving long-form
    # frame than a dense terminal chart.  Labels and values stay unoutlined.
    line_ax.plot(x, values, color=accent, linewidth=3.2, solid_capstyle="round")
    line_ax.fill_between(x, values, min(values), color=accent, alpha=.12)
    line_ax.scatter([x[-1]], [values[-1]], color="#f8ca4e", edgecolor=theme["edge"], linewidth=1.8, zorder=4)
    line_ax.grid(axis="y", color=theme["grid"], alpha=.28, linewidth=1.1, linestyle="--")
    line_ax.set_xticks([0, len(x) - 1]); line_ax.set_xticklabels([str(points[0]["date"])[5:], str(points[-1]["date"])[5:]], color=theme["text"], fontsize=font(.045, 14, 20), fontproperties=regular)
    line_ax.tick_params(axis="y", colors=theme["text"], labelsize=font(.042, 13, 18), length=0)
    for spine in line_ax.spines.values(): spine.set_visible(False)
    sign = "+" if float(chart["change_pct"]) >= 0 else ""
    fig.text(.08, .91, f"{chart['label']}  {chart['latest']:,.2f}", color=theme["text"], fontsize=font(.075, 22, 36), fontproperties=bold)
    fig.text(.92, .91, f"{sign}{chart['change_pct']:.2f}%", color=accent, fontsize=font(.075, 22, 36), ha="right", fontproperties=bold)
    if bars:
        bar_ax = fig.add_axes([.08, .12, .84, .14])
        bar_ax.set_facecolor(theme["background"])
        vals = [float(item["value"]) for item in bars]
        bars_artist = bar_ax.bar(range(len(vals)), vals, width=.64, color=[theme["up"] if value >= 0 else theme["down"] for value in vals], edgecolor="none", linewidth=0)
        for bar in bars_artist: bar.set_hatch("//"); bar.set_sketch_params(1.0, 70, 1.2)
        bar_ax.axhline(0, color=theme["grid"], alpha=.6, linewidth=1)
        bar_ax.set_xticks(range(len(vals))); bar_ax.set_xticklabels([item["label"] for item in bars], color=theme["text"], fontsize=font(.04, 12, 17), fontproperties=regular)
        bar_ax.tick_params(axis="y", colors=theme["text"], labelsize=font(.035, 11, 16), length=0)
        for spine in bar_ax.spines.values(): spine.set_visible(False)
    _footer(fig, chart, theme, font, height)
    return _save(fig, output_path)


def _render_change_arrow(chart: dict[str, Any], output_path: str) -> bool:
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch
    _, bold = _fonts(); theme = _theme(chart)
    fig, _, height, font = _make_canvas(chart); ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 10)
    pct = float(chart["change_pct"]); positive = pct >= 0; accent = theme["up"] if positive else theme["down"]
    start, end = ((3.2, 2.5), (8.9, 7.7)) if positive else ((3.2, 7.7), (8.9, 2.5))
    arrow = FancyArrowPatch(start, end, arrowstyle="Simple,tail_width=1.15,head_width=2.5,head_length=2.2", facecolor=accent, edgecolor=theme["edge"], linewidth=3.2, mutation_scale=24)
    ax.add_patch(arrow); arrow.set_sketch_params(1.0, 90, 1.5)
    fig.text(.07, .76, chart["label"], color=theme["text"], fontsize=font(.075, 24, 38), fontproperties=bold)
    fig.text(.07, .58, f"{chart['latest']:,.2f}", color=theme["text"], fontsize=font(.115, 34, 56), fontproperties=bold)
    fig.text(.07, .42, f"{'▲' if positive else '▼'} {pct:+.2f}%", color=accent, fontsize=font(.09, 28, 44), fontproperties=bold)
    _footer(fig, chart, theme, font, height)
    return _save(fig, output_path)


def _render_composition_pie(chart: dict[str, Any], output_path: str) -> bool:
    import matplotlib.pyplot as plt
    regular, bold = _fonts(); theme = _theme(chart)
    items = list(chart.get("market_cap_pie") or [])[:5]
    if len(items) < 2: return False
    fig, width, height, font = _make_canvas(chart); ax = fig.add_axes([.12, .25, .76, .58]); ax.set_facecolor((0, 0, 0, 0))
    values = [float(item["value"]) for item in items]; labels = [str(item["label"]) for item in items]; total = sum(values)
    colors = ["#ffffff", "#ffd230", "#e5484d", "#8d8d8d", "#343434"][:len(items)]
    wedges, _ = ax.pie(values, colors=colors, startangle=95, wedgeprops={"width":.43, "edgecolor":theme["edge"], "linewidth":3.3})
    for index, wedge in enumerate(wedges):
        wedge.set_sketch_params(1.0, 80, 1.4)
        if index % 2: wedge.set_hatch("///")
    ax.text(0, .10, "상위 5종목", ha="center", va="center", color=theme["text"], fontsize=font(.06, 24, 34), fontproperties=bold)
    ax.text(0, -.14, "시가총액 비중", ha="center", va="center", color=theme["note"], fontsize=font(.045, 18, 26), fontproperties=bold)
    # A bottom two-column legend keeps the donut itself geometrically centered.
    ax.legend(wedges, [f"{label} {value / total * 100:.1f}%" for label, value in zip(labels, values)], loc="upper center", bbox_to_anchor=(.5, -.04), ncol=2, frameon=False, labelcolor=theme["text"], prop=bold, fontsize=font(.032, 12, 18), handlelength=1.15, columnspacing=.55)
    ax.set_title("시가총액 상위 종목 구성", color=theme["text"], fontsize=font(.055, 21, 32), fontproperties=bold, pad=8)
    _footer(fig, chart, theme, font, height)
    return _save(fig, output_path)


def _format_trillion_won(value: float) -> str:
    return f"{value / 1_000_000_000_000:,.0f}조원"


def _render_market_cap_comparison(chart: dict[str, Any], output_path: str) -> bool:
    import matplotlib.pyplot as plt
    _, bold = _fonts(); theme = _theme(chart)
    items = list(chart.get("market_cap_pie") or [])[:2]
    if len(items) < 2: return False
    fig, _, height, font = _make_canvas(chart); ax = fig.add_axes([.12, .22, .76, .55]); ax.set_facecolor((0, 0, 0, 0))
    labels = [str(item["label"]) for item in items]; values = [float(item["value"]) for item in items]; maximum = max(values)
    bars = ax.bar([0, 1], values, width=.48, color=[theme["up"], theme["down"]], edgecolor=theme["edge"], linewidth=3.4)
    for index, bar in enumerate(bars): bar.set_hatch("///" if index == 0 else "\\\\"); bar.set_sketch_params(1.0, 85, 1.5)
    for bar, label, value in zip(bars, labels, values):
        center = bar.get_x() + bar.get_width() / 2
        ax.text(center, value + maximum * .045, _format_trillion_won(value), ha="center", color=theme["text"], fontsize=font(.052, 23, 34), fontproperties=bold)
        ax.text(center, -maximum * .11, label, ha="center", color=theme["text"], fontsize=font(.046, 20, 29), fontproperties=bold)
    ax.set_xlim(-.55, 1.55); ax.set_ylim(-maximum * .18, maximum * 1.2); ax.axis("off")
    fig.text(.5, .86, "시가총액 규모 비교", ha="center", color=theme["text"], fontsize=font(.06, 24, 36), fontproperties=bold)
    _footer(fig, chart, theme, font, height)
    return _save(fig, output_path)


def _render_indexed_comparison(chart: dict[str, Any], output_path: str) -> bool:
    """Render a bounded-base comparison with explicit chart geometry.

    Policy and cost comparisons are not trends.  Their bar axis, value labels,
    and safe margins are computed from one shared baseline so a small
    difference is neither visually fabricated nor hidden by a zero-based axis.
    """
    import matplotlib.pyplot as plt

    _, bold = _fonts(); theme = _theme(chart)
    items = list(chart.get("comparison_values") or [])[:4]
    parsed: list[tuple[str, float]] = []
    for item in items:
        try:
            parsed.append((str(item["label"]), float(item["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    if len(parsed) < 2:
        return False
    fig, _, height, font = _make_canvas(chart)
    values = [value for _, value in parsed]
    baseline = float(chart.get("comparison_baseline") or values[0])
    low = math.floor((min(values + [baseline]) - max(1, abs(baseline) * .05)) / 5) * 5
    high = math.ceil((max(values + [baseline]) + max(1, abs(baseline) * .05)) / 5) * 5
    if high <= low:
        high = low + max(10, abs(baseline) * .1)
    ax = fig.add_axes([.15, .22, .77, .54])
    ax.set_facecolor(theme["background"])
    colors = ["#969696"] + [theme["down"], theme["up"], theme["note"]][:max(0, len(parsed) - 1)]
    bars = ax.bar(range(len(parsed)), [value - low for value in values], width=.52, color=colors, edgecolor=theme["edge"], linewidth=1.2, bottom=low)
    ax.set_ylim(low, high)
    ticks = [low + (high - low) * part / 4 for part in range(5)]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{tick:g}" for tick in ticks], color=theme["note"], fontsize=font(.033, 11, 15), fontproperties=bold)
    ax.set_xticks(range(len(parsed)))
    ax.set_xticklabels([label for label, _ in parsed], color=theme["text"], fontsize=font(.04, 13, 18), fontproperties=bold)
    ax.grid(axis="y", color=theme["grid"], alpha=.45, linewidth=.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(theme["note"]); ax.spines["bottom"].set_color(theme["note"])
    for bar, (_, value) in zip(bars, parsed):
        ax.text(bar.get_x() + bar.get_width() / 2, value + (high - low) * .025, f"{value:,.1f}", ha="center", color=theme["text"], fontsize=font(.038, 12, 17), fontproperties=bold)
    title = str(chart.get("label") or "비교 지수")
    fig.text(.5, .88, title, ha="center", color=theme["text"], fontsize=font(.065, 23, 36), fontproperties=bold)
    from app.utils.number_format import indexed_basis
    fig.text(.5, .82, f"지수 기준: {indexed_basis(chart.get('comparison_basis'), baseline)}", ha="center", color=theme["note"], fontsize=font(.035, 12, 16), fontproperties=bold)
    _footer(fig, chart, theme, font, height)
    return _save(fig, output_path)


def _render_supply_flow(chart: dict[str, Any], output_path: str) -> bool:
    """Render collector-backed investor flows as a story-like notice board."""
    import matplotlib.pyplot as plt
    _, bold = _fonts(); theme = _theme({**chart, "visual_theme": "paper_poster"})
    fig, _, height, font = _make_canvas({**chart, "visual_theme": "paper_poster"})
    values = chart.get("supply_demand") or {}
    labels = list(values)[:3]
    ax = fig.add_axes([.07, .19, .86, .65]); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.text(.07, .89, "누가 사고 있나", color=theme["text"], fontsize=font(.07, 24, 38), fontproperties=bold)
    fig.text(.07, .83, "KOSPI 투자자별 순매수", color=theme["note"], fontsize=font(.035, 13, 18), fontproperties=bold)
    for index, label in enumerate(labels):
        y = .73 - index * .27
        value = str(values[label])
        positive = not value.lstrip().startswith("-")
        accent = theme["up"] if positive else theme["down"]
        ax.add_patch(plt.Rectangle((.02, y - .10), .96, .19, facecolor="#fff9e9", edgecolor=theme["edge"], linewidth=2.2))
        ax.text(.08, y, label, va="center", color=theme["text"], fontsize=font(.055, 20, 31), fontproperties=bold)
        ax.text(.92, y, value, ha="right", va="center", color=accent, fontsize=font(.062, 23, 35), fontproperties=bold)
        ax.text(.49, y, "매수 우위" if positive else "매도 우위", ha="center", va="center", color=theme["note"], fontsize=font(.032, 12, 16), fontproperties=bold)
    _footer(fig, {**chart, "visual_theme": "paper_poster"}, theme, font, height)
    return _save(fig, output_path)


def _render_stock_movers(chart: dict[str, Any], output_path: str) -> bool:
    """Render actual related-stock percentage moves as a compact score board."""
    import matplotlib.pyplot as plt
    _, bold = _fonts(); theme = _theme({**chart, "visual_theme": "factory_panel"})
    fig, _, height, font = _make_canvas({**chart, "visual_theme": "factory_panel"})
    movers = list(chart.get("movers") or [])[:4]
    ax = fig.add_axes([.07, .17, .86, .68]); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.text(.07, .89, "관련 종목 온도", color=theme["text"], fontsize=font(.07, 24, 38), fontproperties=bold)
    fig.text(.07, .83, "수집된 종가 기준 등락률", color=theme["note"], fontsize=font(.035, 13, 18), fontproperties=bold)
    for index, item in enumerate(movers):
        y = .78 - index * .20
        pct = float(item["change_pct"])
        accent = theme["up"] if pct >= 0 else theme["down"]
        ax.add_patch(plt.Rectangle((.02, y - .075), .96, .145, facecolor=theme["background"], edgecolor=theme["note"], linewidth=1.5))
        ax.text(.07, y, str(item["name"]), va="center", color=theme["text"], fontsize=font(.045, 16, 25), fontproperties=bold)
        ax.text(.92, y, f"{'▲' if pct >= 0 else '▼'} {pct:+.2f}%", ha="right", va="center", color=accent, fontsize=font(.053, 19, 30), fontproperties=bold)
    _footer(fig, {**chart, "visual_theme": "factory_panel"}, theme, font, height)
    return _save(fig, output_path)

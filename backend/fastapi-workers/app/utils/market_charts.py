"""Exact market graphics, sized from the final in-scene surface.

The image model supplies a blank *landscape* prop.  This module owns every
visible number and renders at twice the final pixel size, so typography and
composition do not drift when FFmpeg places the final opaque graphic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


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
    preferred = [key for token, key in (("kosdaq", "kosdaq"), ("kospi", "kospi"), ("nasdaq", "nasdaq"), ("s&p", "sp500"), ("sp500", "sp500"), ("vix", "vix")) if token in lower]
    preferred.extend(["kospi", "kosdaq", "sp500", "nasdaq", "dow", "vix", "dxy"])
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


def extract_market_chart(scene: dict[str, Any]) -> dict[str, Any] | None:
    """Build a chart only when every plotted value has a collector source."""
    if str(scene.get("section") or "") != "data":
        return None
    selected = _selected_series(scene.get("market_snapshot") or {}, str(scene.get("content") or scene.get("text") or ""))
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
        "daily_change_bars": bars, "market_cap_pie": _market_cap_pie(scene.get("market_snapshot") or {}),
        "change_pct": round((end - start) / start * 100, 2) if start else 0.0,
        "latest": end, "source_date": str(points[-1]["date"]),
    }


def _theme(chart: dict[str, Any]) -> dict[str, str]:
    return {
        "chalkboard": {"background": "#142b35", "text": "#f9f4e8", "note": "#d8e6ef", "edge": "#1c2a38", "up": "#ff5b6e", "down": "#49a9f8", "grid": "#d8e6ef"},
        "paper_poster": {"background": "#f3e5c7", "text": "#3c3026", "note": "#785f4c", "edge": "#34291f", "up": "#d84b42", "down": "#277fba", "grid": "#785f4c"},
        "factory_panel": {"background": "#1d3937", "text": "#f7f5df", "note": "#91a08d", "edge": "#1b2f2c", "up": "#ffce4b", "down": "#58bdf2", "grid": "#91a08d"},
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


def _footer(fig, chart: dict[str, Any], theme: dict[str, str], font, height: int) -> None:
    text = f"검증 데이터 · {str(chart['source_date'])[5:]}" if height < 360 else f"수집 기준일 {chart['source_date']} · 검증 데이터만 표시"
    fig.text(.06, .035, text, color=theme["note"], fontsize=font(.035, 12, 16), fontproperties=_fonts()[0])


def _fonts():
    from matplotlib.font_manager import FontProperties
    regular_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    bold_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    regular = FontProperties(fname=regular_path) if Path(regular_path).exists() else None
    bold = FontProperties(fname=bold_path) if Path(bold_path).exists() else regular
    return regular, bold


def render_market_chart(chart: dict[str, Any], output_path: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        kind = str(chart.get("visual_kind") or "trend_dashboard")
        if kind == "change_arrow":
            return _render_change_arrow(chart, output_path)
        if kind == "composition_pie":
            return _render_composition_pie(chart, output_path)
        if kind == "comparison":
            return _render_market_cap_comparison(chart, output_path)
        return _render_trend_dashboard(chart, output_path)
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _render_trend_dashboard(chart: dict[str, Any], output_path: str) -> bool:
    import matplotlib.pyplot as plt
    regular, bold = _fonts(); theme = _theme(chart)
    fig, _, height, font = _make_canvas(chart)
    points = chart["points"]; values = [float(point["close"]) for point in points]
    bars = chart.get("daily_change_bars") or []
    line_ax = fig.add_axes([.08, .32 if bars else .16, .84, .53 if bars else .63])
    line_ax.set_facecolor((0, 0, 0, 0)); x = list(range(len(values)))
    accent = theme["up"] if float(chart["change_pct"]) >= 0 else theme["down"]
    line_ax.plot(x, values, color=accent, linewidth=3.8, solid_capstyle="round")
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
        bars_artist = bar_ax.bar(range(len(vals)), vals, width=.64, color=[theme["up"] if value >= 0 else theme["down"] for value in vals], edgecolor=theme["edge"], linewidth=1.4)
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
    colors = ["#4ca4d8", "#d95047", "#e5b64b", "#62a56f", "#9b7ac9"][:len(items)]
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

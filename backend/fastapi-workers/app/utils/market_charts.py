"""Render charts only from collected market closing-price series."""
from __future__ import annotations

from pathlib import Path
from typing import Any


SERIES_LABELS = {
    "kospi": "KOSPI",
    "kosdaq": "KOSDAQ",
    "sp500": "S&P 500",
    "nasdaq": "NASDAQ",
    "dow": "DOW JONES",
    "vix": "VIX",
    "dxy": "DOLLAR INDEX",
}


def extract_market_chart(scene: dict[str, Any]) -> dict[str, Any] | None:
    """Choose a real collected series appropriate for a data scene."""
    if str(scene.get("section") or "") != "data":
        return None
    snapshot = scene.get("market_snapshot") or {}
    candidates: dict[str, list] = {}
    for market_key in ("kr", "us"):
        candidates.update((snapshot.get(market_key) or {}).get("chart_series") or {})
    if not candidates:
        return None
    text = str(scene.get("content") or scene.get("text") or "").lower()
    preferred = []
    if "코스닥" in text or "kosdaq" in text:
        preferred.append("kosdaq")
    if "코스피" in text or "kospi" in text:
        preferred.append("kospi")
    if "나스닥" in text or "nasdaq" in text:
        preferred.append("nasdaq")
    if "s&p" in text or "sp500" in text or "미국" in text:
        preferred.append("sp500")
    if "vix" in text or "변동성" in text:
        preferred.append("vix")
    preferred.extend(["kospi", "kosdaq", "sp500", "nasdaq", "dow", "vix", "dxy"])
    for key in preferred:
        raw = candidates.get(key) or []
        points = []
        for item in raw:
            try:
                points.append({"date": str(item["date"]), "close": float(item["close"])})
            except (KeyError, TypeError, ValueError):
                continue
        if len(points) >= 5:
            start, end = points[0]["close"], points[-1]["close"]
            change_pct = ((end - start) / start * 100) if start else 0.0
            return {
                "series_key": key,
                "label": SERIES_LABELS.get(key, key.upper()),
                "points": points[-30:],
                "change_pct": round(change_pct, 2),
                "latest": end,
                "source_date": points[-1]["date"],
            }
    return None


def render_market_chart(chart: dict[str, Any], output_path: str) -> bool:
    """Render a transparent 720x360 editorial line chart from supplied points."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.font_manager import FontProperties
        from matplotlib.patches import FancyBboxPatch

        points = chart["points"]
        values = [point["close"] for point in points]
        x = list(range(len(values)))
        positive = chart["change_pct"] >= 0
        line = "#38D39F" if positive else "#FF5A6E"
        font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        bold_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
        regular = FontProperties(fname=font_path) if Path(font_path).exists() else None
        bold = FontProperties(fname=bold_path) if Path(bold_path).exists() else regular

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig = plt.figure(figsize=(7.2, 3.6), dpi=100)
        fig.patch.set_alpha(0)
        ax = fig.add_axes([0.11, 0.16, 0.82, 0.64])
        ax.set_facecolor("#081A30")
        fig.patches.append(FancyBboxPatch(
            (0.01, 0.02), 0.98, 0.96, transform=fig.transFigure,
            boxstyle="round,pad=0.01,rounding_size=0.03",
            facecolor="#081A30", edgecolor="#4BD6FF", linewidth=1.4, alpha=0.94,
            zorder=-1,
        ))
        ax.plot(x, values, color=line, linewidth=3)
        ax.fill_between(x, values, min(values), color=line, alpha=0.14)
        ax.scatter([x[-1]], [values[-1]], color="#F7C948", edgecolor="#FFFFFF", linewidth=0.8, zorder=3)
        ax.grid(axis="y", color="#315170", alpha=0.35, linewidth=0.7)
        ax.tick_params(colors="#AFC4DA", labelsize=8, length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xticks([0, len(x) - 1])
        ax.set_xticklabels([points[0]["date"][5:], points[-1]["date"][5:]], fontproperties=regular)
        ax.set_yticklabels([])
        title = f"{chart['label']}  |  최근 수집 시계열"
        fig.text(0.10, 0.87, title, color="#FFFFFF", fontsize=14, fontproperties=bold, weight="bold")
        sign = "+" if chart["change_pct"] >= 0 else ""
        fig.text(0.89, 0.87, f"{sign}{chart['change_pct']:.2f}%", color=line, fontsize=14,
                 fontproperties=bold, weight="bold", ha="right")
        fig.text(0.10, 0.06, f"Source date: {chart['source_date']}", color="#8DA9C4", fontsize=8,
                 fontproperties=regular)
        fig.savefig(output_path, transparent=True, dpi=100)
        plt.close(fig)
        return Path(output_path).exists() and Path(output_path).stat().st_size > 4_000
    except Exception:
        return False

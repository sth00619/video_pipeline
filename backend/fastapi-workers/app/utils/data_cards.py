"""Editorial data-card overlays rendered independently from AI images.

AI image models are deliberately told not to produce text.  This module draws
the factual Korean text as a deterministic transparent PNG which FFmpeg can
place over an eligible scene.
"""
from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any

from app.utils.quality_gate import sanitize_narration

logger = logging.getLogger(__name__)


NUMBER_RE = re.compile(
    r"(?<![\w.])(?:[$₩]\s*)?\d{1,3}(?:,\d{3})*(?:\.\d+)?"
    r"\s*(?:%|퍼센트|조|억|만|배|포인트|원|달러|주|년|개월)?"
)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", sanitize_narration(text)).strip()
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"


def extract_data_card(scene: dict[str, Any]) -> dict[str, Any] | None:
    """Select only evidence-bearing scenes; never invent a metric."""
    text = sanitize_narration(scene.get("content") or scene.get("text") or "")
    if not text:
        return None
    visual_type = str(scene.get("visual_type") or "")
    section = str(scene.get("section") or "")
    metrics = []
    for match in NUMBER_RE.finditer(text):
        value = re.sub(r"\s+", "", match.group(0))
        if value and value not in metrics:
            metrics.append(value)
        if len(metrics) == 3:
            break

    # Do not turn narration numbers into screenshot-like cards. A card is
    # reserved for an intentionally selected news-headline scene; data scenes
    # should use a verified market chart when one is available.
    overlay_strategy = str((scene.get("art_direction") or {}).get("overlay_strategy") or "")
    if overlay_strategy != "headline_card":
        return None

    sentences = [s.strip() for s in SENTENCE_RE.split(text) if s.strip()]
    headline = _compact(scene.get("title") or (sentences[0] if sentences else text), 28)
    detail_source = sentences[0] if sentences else text
    detail = _compact(detail_source, 62)
    label = "핵심 데이터" if metrics else "핵심 포인트"
    return {"label": label, "headline": headline, "detail": detail, "metrics": metrics}


def render_data_card(card: dict[str, Any], output_path: str) -> bool:
    """Render one 850x325 transparent PNG using the Docker-installed Nanum font."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.font_manager import FontProperties
        from matplotlib.patches import FancyBboxPatch, Rectangle

        font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        bold_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
        regular = FontProperties(fname=font_path) if Path(font_path).exists() else None
        bold = FontProperties(fname=bold_path) if Path(bold_path).exists() else regular

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig = plt.figure(figsize=(8.5, 3.25), dpi=100)
        fig.patch.set_alpha(0)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        ax.add_patch(FancyBboxPatch(
            (0.01, 0.03), 0.98, 0.94,
            boxstyle="round,pad=0.015,rounding_size=0.035",
            facecolor="#07182D", edgecolor="#60D8FF", linewidth=1.6, alpha=0.94,
        ))
        ax.add_patch(Rectangle((0.04, 0.16), 0.012, 0.68, facecolor="#F7C948", linewidth=0))
        ax.text(0.075, 0.80, card["label"].upper(), color="#60D8FF", fontsize=12,
                fontproperties=bold, va="center", weight="bold")
        ax.text(0.075, 0.63, card["headline"], color="#FFFFFF", fontsize=22,
                fontproperties=bold, va="center", weight="bold")
        ax.text(0.075, 0.43, card["detail"], color="#C7D5E5", fontsize=13,
                fontproperties=regular, va="center")

        metrics = card.get("metrics") or []
        if metrics:
            width = min(0.25, 0.76 / len(metrics))
            for i, metric in enumerate(metrics):
                x = 0.075 + i * (width + 0.025)
                ax.add_patch(FancyBboxPatch(
                    (x, 0.20), width, 0.13,
                    boxstyle="round,pad=0.01,rounding_size=0.018",
                    facecolor="#123353", edgecolor="#285C87", linewidth=0.8,
                ))
                ax.text(x + width / 2, 0.265, metric, color="#F7C948", fontsize=15,
                        fontproperties=bold, ha="center", va="center", weight="bold")

        fig.savefig(output_path, transparent=True, dpi=100)
        plt.close(fig)
        return Path(output_path).exists() and Path(output_path).stat().st_size > 4_000
    except Exception:
        logger.exception("data card render failed")
        return False

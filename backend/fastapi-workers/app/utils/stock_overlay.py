"""Deterministic market-data cards and safe placement helpers.

AI images never receive factual numbers.  Verified values are rendered here
as a transparent PNG and composited afterwards.  Anchor placement is the
default because it survives image resizing/cropping; pixel coordinates remain
available for fixed templates and QA.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


class Market(str, Enum):
    KR = "kr"
    US = "us"


class Anchor(str, Enum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CENTER = "center"


@dataclass(frozen=True)
class IndexData:
    name: str
    value: float
    change: float
    change_pct: float
    market: Market = Market.KR


def _font(size: int, font_path: Optional[str] = None):
    candidates = [font_path] if font_path else []
    candidates += [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _color(data: IndexData):
    if data.change == 0:
        return (150, 150, 150, 255)
    if data.market == Market.KR:
        return (229, 57, 53, 255) if data.change > 0 else (30, 136, 229, 255)
    return (38, 166, 91, 255) if data.change > 0 else (229, 57, 53, 255)


def render_index_card(data: IndexData, out_path: str, *, scale: int = 2, font_path: Optional[str] = None) -> str:
    """Render one transparent RGBA card using only supplied verified values."""
    s = max(1, int(scale))
    pad_x, pad_y, gap = 40 * s, 30 * s, 10 * s
    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    name_font, value_font, change_font = _font(30 * s, font_path), _font(76 * s, font_path), _font(38 * s, font_path)
    name = str(data.name)
    value = f"{float(data.value):,.2f}"
    arrow = "▲" if data.change > 0 else ("▼" if data.change < 0 else "─")
    change = f"{arrow} {float(data.change):+,.2f}  ({float(data.change_pct):+.2f}%)"

    def size(text, font):
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0], box[3] - box[1]

    widths = [size(name, name_font), size(value, value_font), size(change, change_font)]
    content_left = pad_x + 8 * s + 18 * s
    card_w = content_left + max(w for w, _ in widths) + pad_x
    card_h = pad_y + sum(h for _, h in widths) + gap * 2 + pad_y
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, card_w - 1, card_h - 1), radius=24 * s, fill=(18, 22, 30, 235))
    accent = _color(data)
    draw.rounded_rectangle((pad_x, pad_y, pad_x + 8 * s, card_h - pad_y), radius=4 * s, fill=accent)
    y = pad_y
    draw.text((content_left, y), name, font=name_font, fill=(210, 216, 226, 255))
    y += widths[0][1] + gap
    draw.text((content_left, y), value, font=value_font, fill=(245, 247, 250, 255))
    y += widths[1][1] + gap
    draw.text((content_left, y), change, font=change_font, fill=accent)
    if s > 1:
        card = card.resize((card_w // s, card_h // s), Image.Resampling.LANCZOS)
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    card.save(output, format="PNG")
    return str(output)


def resolve_position(anchor: Anchor, base_w: int, base_h: int, card_w: int, card_h: int, margin: int = 40) -> tuple[int, int]:
    if anchor == Anchor.TOP_LEFT:
        return margin, margin
    if anchor == Anchor.TOP_RIGHT:
        return base_w - card_w - margin, margin
    if anchor == Anchor.BOTTOM_LEFT:
        return margin, base_h - card_h - margin
    if anchor == Anchor.BOTTOM_RIGHT:
        return base_w - card_w - margin, base_h - card_h - margin
    return (base_w - card_w) // 2, (base_h - card_h) // 2


def compose_on_image(base_path: str, card_path: str, output_path: str, *, anchor: Anchor = Anchor.TOP_RIGHT, margin: int = 40, xy: tuple[int, int] | None = None) -> str:
    base = Image.open(base_path).convert("RGBA")
    card = Image.open(card_path).convert("RGBA")
    position = xy or resolve_position(anchor, base.width, base.height, card.width, card.height, margin)
    base.alpha_composite(card, (int(position[0]), int(position[1])))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    base.save(output, format="PNG")
    return str(output)


def overlay_filter(base_w: int, base_h: int, card_w: int, card_h: int, *, anchor: Anchor = Anchor.TOP_RIGHT, margin: int = 40, xy: tuple[int, int] | None = None) -> str:
    if xy is not None:
        x, y = xy
        return f"overlay={int(x)}:{int(y)}"
    if anchor == Anchor.TOP_LEFT:
        return f"overlay={margin}:{margin}"
    if anchor == Anchor.TOP_RIGHT:
        return f"overlay=main_w-overlay_w-{margin}:{margin}"
    if anchor == Anchor.BOTTOM_LEFT:
        return f"overlay={margin}:main_h-overlay_h-{margin}"
    if anchor == Anchor.BOTTOM_RIGHT:
        return f"overlay=main_w-overlay_w-{margin}:main_h-overlay_h-{margin}"
    return "overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2"

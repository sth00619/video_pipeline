"""우상단 채널 워터마크를 결정론적으로 렌더한다.

레퍼런스 채널(경제사냥꾼)은 모든 프레임 우상단에 채널 배지가 항상 존재한다.
채널명 문구는 아직 확정되지 않았으므로, 이 모듈은 마스코트와 같은 재질의
둥근 금화 배지 아이콘만 그린다. 채널명이 정해지면 이 레이어에 텍스트를
추가하면 된다 — 좌표·마진 계약은 이미 ``editorial_overlay.py``의
``_WATERMARK`` 보호 영역과 일치시켜 뒀다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .editorial_overlay import _WATERMARK

# 지름·마진 비율을 별도로 유지하지 않고 기존 ``_WATERMARK`` 보호 영역(px)에서
# 직접 계산한다. 16:9 캔버스에서는 그 영역의 높이(세로)가 폭보다 좁은 제약이라,
# 폭 기준 비율만으로 지름을 정하면 높이를 넘칠 수 있다 — 항상
# ``min(영역 폭, 영역 높이)`` 기준으로 계산해 영역을 절대 벗어나지 않게 한다.
_DIAMETER_RATIO_OF_MIN_SIDE = 0.72
_MARGIN_RATIO_OF_MIN_SIDE = 0.10

_GOLD_FILL = (255, 196, 43, 255)
_GOLD_RIM = (196, 140, 20, 255)
_INK_OUTLINE = (46, 30, 8, 255)
_HIGHLIGHT = (255, 240, 190, 165)


def _coin_badge(diameter: int) -> Image.Image:
    """마스코트와 같은 재질(둥근 금화, 점각 림, 잉크 외곽선)의 배지를 그린다."""
    badge = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    outline_width = max(2, round(diameter * 0.045))
    draw.ellipse((0, 0, diameter - 1, diameter - 1), fill=_INK_OUTLINE)
    inset = outline_width
    draw.ellipse((inset, inset, diameter - 1 - inset, diameter - 1 - inset), fill=_GOLD_FILL)
    rim_inset = inset + max(2, round(diameter * 0.05))
    draw.ellipse(
        (rim_inset, rim_inset, diameter - 1 - rim_inset, diameter - 1 - rim_inset),
        outline=_GOLD_RIM,
        width=max(1, round(diameter * 0.02)),
    )
    highlight_radius = max(2, round(diameter * 0.10))
    highlight_cx, highlight_cy = round(diameter * 0.34), round(diameter * 0.32)
    draw.ellipse(
        (
            highlight_cx - highlight_radius, highlight_cy - highlight_radius,
            highlight_cx + highlight_radius, highlight_cy + highlight_radius,
        ),
        fill=_HIGHLIGHT,
    )
    return badge


def watermark_region(canvas_size: tuple[int, int] = (1920, 1080)) -> dict[str, int]:
    """다른 오버레이가 피해야 할 워터마크 보호 영역(px)을 반환한다.

    ``editorial_overlay._WATERMARK``가 정의한 기존 보호 사각형 안쪽
    우상단 모서리에 배지를 앉힌다. 계산이 항상 그 사각형 안쪽에서만
    이뤄지므로 다른 오버레이가 이미 피하는 영역과 절대 겹치지 않는다.
    """
    width, height = canvas_size
    region_x = _WATERMARK["x"] * width
    region_y = _WATERMARK["y"] * height
    region_w = _WATERMARK["width"] * width
    region_h = _WATERMARK["height"] * height
    min_side = min(region_w, region_h)
    diameter = round(min_side * _DIAMETER_RATIO_OF_MIN_SIDE)
    margin = round(min_side * _MARGIN_RATIO_OF_MIN_SIDE)
    x = round(region_x + region_w - diameter - margin)
    y = round(region_y + margin)
    return {"x": x, "y": y, "width": diameter, "height": diameter}


def render_channel_watermark_layer(canvas_size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    """전체 캔버스 크기의 투명 레이어에 우상단 배지만 그려서 반환한다."""
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    region = watermark_region(canvas_size)
    badge = _coin_badge(region["width"])
    layer.alpha_composite(badge, (region["x"], region["y"]))
    return layer

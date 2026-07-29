"""Pillow 기반 결정론적 한글 오버레이."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


class FontMissing(Exception):
    """한글 오버레이에 사용할 글꼴이 없음."""


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        os.environ.get("KOREAN_FONT_PATH"),
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "C:/Windows/Fonts/malgunbd.ttf",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    raise FontMissing("한글 글꼴을 찾지 못했습니다. KOREAN_FONT_PATH를 설정하세요.")


@dataclass
class OverlaySpec:
    subtitle: Optional[str] = None
    logo_text: str = "경제브리핑"
    timestamp: Optional[str] = None
    speech_bubble: Optional[str] = None


@dataclass(frozen=True)
class VerifiedMetric:
    """외부 검증 또는 실행 원장에서 온 값만 담는 정보 패널 항목."""
    label: str
    value: str
    source: str


@dataclass(frozen=True)
class InfoPanelSpec:
    title: str
    timestamp: str
    metrics: tuple[VerifiedMetric, ...]
    chart_value: float
    chart_max: float
    source_note: str


def _outlined_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, *, fill="white", outline="black", width=3) -> None:
    draw.text(xy, text, font=font, fill=fill, stroke_width=width, stroke_fill=outline)


def apply_overlay(base_png: bytes, spec: OverlaySpec) -> bytes:
    """생성 이미지 위에 검증된 한글 자막·로고를 합성한다."""
    image = Image.open(io.BytesIO(base_png)).convert("RGBA")
    width, height = image.size
    draw = ImageDraw.Draw(image)
    if spec.subtitle:
        font = _load_font(int(height * 0.055))
        box = draw.textbbox((0, 0), spec.subtitle, font=font, stroke_width=3)
        text_width = box[2] - box[0]
        _outlined_text(draw, ((width - text_width) // 2, int(height * 0.86)), spec.subtitle, font, width=max(2, int(height * 0.004)))
    if spec.logo_text:
        logo_font = _load_font(int(height * 0.045))
        box = draw.textbbox((0, 0), spec.logo_text, font=logo_font)
        _outlined_text(draw, (width - (box[2] - box[0]) - int(width * 0.02), int(height * 0.03)), spec.logo_text, logo_font, fill="#FFD700", width=2)
    if spec.timestamp:
        time_font = _load_font(int(height * 0.035))
        box = draw.textbbox((0, 0), spec.timestamp, font=time_font)
        _outlined_text(draw, (width - (box[2] - box[0]) - int(width * 0.02), int(height * 0.09)), spec.timestamp, time_font, fill="#00E5FF", width=2)
    if spec.speech_bubble:
        bubble_font = _load_font(int(height * 0.07))
        box = draw.textbbox((0, 0), spec.speech_bubble, font=bubble_font)
        pad, x, y = int(width * 0.015), int(width * 0.04), int(height * 0.08)
        draw.rounded_rectangle([x - pad, y - pad, x + box[2] - box[0] + pad, y + box[3] - box[1] + pad], radius=int(height * 0.03), fill="white", outline="black", width=max(3, int(height * 0.005)))
        draw.text((x, y), spec.speech_bubble, font=bubble_font, fill="black")
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def apply_info_panel(base_png: bytes, spec: InfoPanelSpec) -> bytes:
    """검증된 값만으로 차트·수치 패널을 결정론적으로 합성한다.

    모델이 그린 문자나 숫자를 읽거나 수정하지 않는다. 호출자가 제공한
    ``VerifiedMetric`` 값만 Pillow 텍스트로 렌더링한다.
    """
    image = Image.open(io.BytesIO(base_png)).convert("RGBA")
    width, height = image.size
    draw = ImageDraw.Draw(image)
    panel_x, panel_y = int(width * 0.035), int(height * 0.135)
    panel_w, panel_h = int(width * 0.405), int(height * 0.625)
    radius = max(12, int(height * 0.025))
    draw.rounded_rectangle(
        (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), radius=radius,
        fill=(10, 31, 52, 238), outline=(109, 224, 255, 255), width=max(3, int(height * 0.005)),
    )
    title_font = _load_font(int(height * 0.038))
    metric_font = _load_font(int(height * 0.027))
    value_font = _load_font(int(height * 0.030))
    small_font = _load_font(int(height * 0.018))
    padding = int(panel_w * 0.065)
    _outlined_text(draw, (panel_x + padding, panel_y + int(panel_h * 0.06)), spec.title, title_font, fill="#FFFFFF", outline="#07131E", width=2)
    draw.text((panel_x + padding, panel_y + int(panel_h * 0.13)), spec.timestamp, font=small_font, fill="#84E9FF")

    row_y = panel_y + int(panel_h * 0.205)
    row_step = int(panel_h * 0.105)
    for metric in spec.metrics:
        draw.rounded_rectangle(
            (panel_x + padding, row_y - int(row_step * 0.025), panel_x + panel_w - padding, row_y + int(row_step * 0.77)),
            radius=max(6, int(height * 0.012)), fill=(24, 61, 86, 235), outline=(66, 125, 151, 255), width=1,
        )
        draw.text((panel_x + padding + int(panel_w * 0.03), row_y + int(row_step * 0.09)), metric.label, font=metric_font, fill="#BFEFFF")
        value_box = draw.textbbox((0, 0), metric.value, font=value_font)
        draw.text((panel_x + panel_w - padding - (value_box[2] - value_box[0]) - int(panel_w * 0.03), row_y + int(row_step * 0.07)), metric.value, font=value_font, fill="#FFD64D")
        row_y += row_step

    chart_top = panel_y + int(panel_h * 0.68)
    chart_left = panel_x + padding + int(panel_w * 0.03)
    chart_w = panel_w - 2 * padding - int(panel_w * 0.06)
    chart_h = int(panel_h * 0.18)
    draw.text((chart_left, chart_top - int(height * 0.032)), "실비 검증 차트 (USD)", font=small_font, fill="#BFEFFF")
    for grid in range(4):
        y = chart_top + round(chart_h * grid / 3)
        draw.line((chart_left, y, chart_left + chart_w, y), fill=(66, 125, 151, 180), width=1)
    ratio = min(1.0, max(0.0, spec.chart_value / spec.chart_max)) if spec.chart_max else 0.0
    bar_w = max(4, round(chart_w * ratio))
    draw.rounded_rectangle((chart_left, chart_top + int(chart_h * 0.42), chart_left + bar_w, chart_top + int(chart_h * 0.72)), radius=max(3, int(height * 0.006)), fill="#36D399")
    draw.text((chart_left, chart_top + int(chart_h * 0.75)), f"{spec.chart_value:.3f} / {spec.chart_max:.3f}", font=small_font, fill="#FFFFFF")
    draw.text((panel_x + padding, panel_y + panel_h - int(panel_h * 0.06)), spec.source_note, font=small_font, fill="#9FC0D1")

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()

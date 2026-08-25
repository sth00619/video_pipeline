"""그림 속 소품의 내부 화면에 검증 수치를 다시 그리는 V5 템플릿.

이 모듈은 프레임 위에 범용 정보 카드를 추가하지 않는다. 생성 이미지에 이미
존재하는 계산대ㆍ경보판ㆍ날씨 지도 같은 소품의 **내부 표시 영역**만 다시
그린다. 값은 호출자가 검증한 ``VerifiedFact``에서만 받아야 한다.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from .diegetic_fact_overlay import VerifiedFact


TemplateKind = Literal["checkout_total", "risk_warning", "weather_callouts"]


@dataclass(frozen=True)
class InSceneTemplate:
    """기존 소품 안쪽 화면의 정규화 좌표와 표현 방식이다."""

    kind: TemplateKind
    x: float
    y: float
    width: float
    height: float

    def validate(self) -> None:
        if self.kind not in {"checkout_total", "risk_warning", "weather_callouts"}:
            raise ValueError("지원하지 않는 그림 내부 정보 템플릿입니다.")
        if not (0 <= self.x < 1 and 0 <= self.y < 1 and self.width > 0 and self.height > 0):
            raise ValueError("그림 내부 정보 영역 좌표가 올바르지 않습니다.")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("그림 내부 정보 영역이 캔버스 밖으로 나갑니다.")


def _font(size: int) -> ImageFont.FreeTypeFont:
    # 운영체제별 굵은 산세리프 후보를 명시적으로 순회한다. Pillow 기본 글꼴로
    # 조용히 낮추지 않으며, 승인된 후보가 하나도 없을 때만 실패한다.
    candidates = (
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/app/assets/fonts/BlackHanSans-Regular.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise OSError("그림 내부 정보 표면에 사용할 굵은 글꼴이 없습니다.")


def _fit(text: str, max_width: int, start_size: int) -> ImageFont.FreeTypeFont:
    for size in range(start_size, 8, -1):
        candidate = _font(size)
        box = candidate.getbbox(text)
        if box[2] - box[0] <= max_width:
            return candidate
    raise ValueError("표시 영역에 비해 검증 값이 너무 깁니다.")


def _rect(template: InSceneTemplate, size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    return (
        round(template.x * width), round(template.y * height),
        round((template.x + template.width) * width), round((template.y + template.height) * height),
    )


def apply_checkout_total(
    base_png: bytes,
    fact: VerifiedFact,
    template: InSceneTemplate,
    *,
    heading: str = "KOSPI CLOSE",
) -> bytes:
    """빨간 POS/계산대 화면의 안쪽만 실제 지표로 교체한다.

    베젤, 주변 로봇 팔, 계산기, 그림자 등은 전혀 손대지 않는다. ``heading``은
    수치가 아닌 장면 설명이며, 정확한 수치는 ``fact.value``만 표시한다.
    """
    if template.kind != "checkout_total":
        raise ValueError("계산대 화면에는 checkout_total 템플릿이 필요합니다.")
    fact.validate()
    template.validate()

    image = Image.open(io.BytesIO(base_png)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = _rect(template, image.size)
    panel_width, panel_height = right - left, bottom - top
    radius = max(7, round(min(panel_width, panel_height) * .055))
    border = max(2, round(min(panel_width, panel_height) * .016))

    # 원본의 붉은 전광판과 같은 계열의 그라데이션/금색 장식을 화면 "안"에만
    # 다시 만든다. 바깥 베젤은 기존 AI 일러스트 픽셀을 보존한다.
    for y in range(top, bottom):
        ratio = (y - top) / max(1, panel_height - 1)
        color = (
            round(92 + 35 * (1 - ratio)),
            round(13 + 10 * (1 - ratio)),
            round(19 + 14 * (1 - ratio)),
            255,
        )
        draw.line((left, y, right, y), fill=color)
    draw.rounded_rectangle((left, top, right, bottom), radius=radius, outline=(255, 178, 91, 255), width=border)
    inset = max(8, round(panel_width * .07))
    gold = (255, 209, 121, 255)
    accent = (255, 154, 77, 255)
    line_y1 = top + round(panel_height * .18)
    line_y2 = top + round(panel_height * .82)
    draw.line((left + inset, line_y1, right - inset, line_y1), fill=gold, width=max(1, border // 2))
    draw.line((left + inset, line_y2, right - inset, line_y2), fill=gold, width=max(1, border // 2))
    # 작은 장식은 실수치와 경쟁하지 않으면서 원본 간판의 구도를 유지한다.
    for cx in (left + round(panel_width * .28), right - round(panel_width * .28)):
        draw.arc((cx - 10, line_y1 - 7, cx + 10, line_y1 + 7), 190, 350, fill=accent, width=max(1, border // 2))
        draw.arc((cx - 10, line_y2 - 7, cx + 10, line_y2 + 7), 10, 170, fill=accent, width=max(1, border // 2))

    label_font = _fit(heading, panel_width - inset * 2, max(12, round(panel_height * .16)))
    value_font = _fit(fact.value, panel_width - inset * 2, max(18, round(panel_height * .29)))
    def centered(text: str, y: int, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int, int]) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((left + right - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)

    centered(heading, top + round(panel_height * .30), label_font, gold)
    centered(fact.value, top + round(panel_height * .49), value_font, (255, 226, 157, 255))

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()

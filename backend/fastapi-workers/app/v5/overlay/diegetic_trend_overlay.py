"""NAVER 검색어 트렌드를 그림 속 지도 라벨로 합성하는 결정론적 렌더러."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class MapTrendAnnotation:
    """지도 위 직접 표기할 NAVER 상대 검색 관심도 한 점이다."""

    label: str
    ratio_text: str
    x: float
    y: float
    source_series_id: str

    def validate(self) -> None:
        if not self.label.strip() or not self.ratio_text.strip() or not self.source_series_id.strip():
            raise ValueError("지도 라벨에는 이름ㆍ값ㆍNAVER 시계열 참조가 필요합니다.")
        if not (0 <= self.x <= 1 and 0 <= self.y <= 1):
            raise ValueError("지도 라벨 좌표는 0~1 범위여야 합니다.")


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/app/assets/fonts/BlackHanSans-Regular.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise OSError("지도 수치 표면에 사용할 굵은 글꼴이 없습니다.")


def annotations_from_visual_data_pack(pack: dict[str, Any]) -> tuple[MapTrendAnnotation, ...]:
    """데이터 팩의 마지막 NAVER 원본 점만 지도 표기로 변환한다.

    ratio를 반올림하거나 주가 지표로 해석하지 않는다. 표시 문자열은 API가 준
    숫자의 문자열 표현을 그대로 사용한다.
    """
    rows = pack.get("trend_series")
    if not isinstance(rows, list) or len(rows) < 1:
        raise ValueError("visual_data_pack에 NAVER 검색어 트렌드 시계열이 없습니다.")
    # 날씨 스튜디오의 지도면(좌ㆍ중앙)에만 쓴다. 우측 마스코트, 카메라,
    # 하단 자막 영역은 어떤 실제 값도 침범하지 않는 고정 안전영역이다.
    positions = ((.19, .34), (.35, .49), (.50, .34), (.36, .62), (.49, .27))
    labels = {"코스피": "KOSPI", "삼성전자": "SAMSUNG", "SK하이닉스": "SK HYNIX", "엔비디아": "NVIDIA"}
    result: list[MapTrendAnnotation] = []
    for index, row in enumerate(rows[:len(positions)]):
        if not isinstance(row, dict):
            raise ValueError("NAVER 검색어 트렌드 시계열 형식이 올바르지 않습니다.")
        points = row.get("points")
        if not isinstance(points, list) or not points or not isinstance(points[-1], dict):
            raise ValueError("NAVER 검색어 트렌드의 마지막 시계열 점이 없습니다.")
        ratio = points[-1].get("ratio")
        if not isinstance(ratio, (int, float)):
            raise ValueError("NAVER 검색어 트렌드 ratio는 숫자여야 합니다.")
        title = str(row.get("title") or "").strip()
        annotation = MapTrendAnnotation(
            label=labels.get(title, title.upper()), ratio_text=str(ratio),
            x=positions[index][0], y=positions[index][1], source_series_id=str(row.get("id") or ""),
        )
        annotation.validate()
        result.append(annotation)
    return tuple(result)


def apply_weather_map_search_interest(base_png: bytes, annotations: tuple[MapTrendAnnotation, ...]) -> bytes:
    """기존 지도 그래픽 위에 실제 NAVER 검색 관심도 라벨을 직접 그린다.

    별도 상자나 UI 패널을 만들지 않는다. 라벨은 지도 위의 날씨 아이콘ㆍ흐름
    화살표처럼 보이도록 외곽선, 작은 점, 짧은 리더선만 사용한다.
    """
    for annotation in annotations:
        annotation.validate()
    image = Image.open(io.BytesIO(base_png)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    title_font = _font(max(16, round(width * .010)))
    value_font = _font(max(18, round(width * .012)))
    line_width = max(2, round(width * .0017))
    for annotation in annotations:
        x, y = round(annotation.x * width), round(annotation.y * height)
        # 지도 위에서 나온 리더선과 기상 관측 점. 배경의 광원에 맞춰 청록/백색을 쓴다.
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(67, 224, 242, 255), outline=(10, 55, 86, 255), width=line_width)
        draw.line((x + 8, y - 3, x + 28, y - 22), fill=(226, 252, 255, 230), width=line_width)
        tx, ty = x + 30, y - 48
        draw.text((tx, ty), annotation.label, font=title_font, fill=(236, 253, 255, 255), stroke_width=line_width, stroke_fill=(14, 51, 81, 255))
        draw.text((tx, ty + title_font.size), annotation.ratio_text, font=value_font, fill=(255, 215, 96, 255), stroke_width=line_width, stroke_fill=(14, 51, 81, 255))
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()

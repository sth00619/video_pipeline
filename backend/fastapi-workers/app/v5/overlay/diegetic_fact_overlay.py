"""장면 속 소품 표면에만 검증된 사실을 합성하는 결정론 렌더러.

AI가 그린 장식 문자와 실제 대본의 사실을 분리한다. 이 모듈은 화면 한쪽에
일괄 정보 패널을 만들지 않고, 장면 기획자가 지정한 계산기·모니터·표지판 같은
소품의 표면에 한 사실씩만 배치한다.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Literal

from PIL import Image, ImageDraw

from .korean_overlay import _load_font
from .fact_value_contract import verified_fact_contains_value
from app.services.surface_text_manifest import draw_text_cell, set_manifest


# ``embedded_monitor``는 배경에 AI가 이미 그린 물리 모니터의 *내부 화면*만
# 갱신한다. 프레임 전체 위에 새 정보 카드를 얹는 용도가 아니다.
SurfaceKind = Literal["monitor", "placard", "gauge_caption", "embedded_monitor"]
VisualizationKind = Literal["text", "upward_trend"]


@dataclass(frozen=True)
class SurfaceAnchor:
    """사실 문구를 넣을, 장면 안 소품 표면의 정규화 좌표."""

    x: float
    y: float
    width: float
    height: float
    kind: SurfaceKind

    def validate(self) -> None:
        if self.kind not in {"monitor", "placard", "gauge_caption", "embedded_monitor"}:
            raise ValueError("지원하지 않는 소품 표면 종류입니다.")
        if not (0.0 <= self.x < 1.0 and 0.0 <= self.y < 1.0):
            raise ValueError("소품 표면 좌표는 0~1 범위여야 합니다.")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("소품 표면의 너비와 높이는 양수여야 합니다.")
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("소품 표면이 캔버스 밖으로 나갈 수 없습니다.")


@dataclass(frozen=True)
class VerifiedFact:
    """대본 검증을 통과한 한 개의 사실과 그 근거."""

    label: str
    value: str
    source_ref: str
    anchor: SurfaceAnchor
    visualization: VisualizationKind = "text"
    start_value: str = ""
    end_value: str = ""

    def validate(self) -> None:
        if not self.label.strip() or not self.value.strip():
            raise ValueError("검증 사실의 항목명과 값은 비어 있을 수 없습니다.")
        if not self.source_ref.strip():
            raise ValueError("검증 사실에는 출처 참조가 필요합니다.")
        if self.visualization not in {"text", "upward_trend"}:
            raise ValueError("지원하지 않는 검증 사실 시각화입니다.")
        if self.visualization == "upward_trend":
            if self.anchor.kind not in {"monitor", "embedded_monitor"}:
                raise ValueError("상승 추세선은 모니터 계열 소품 표면에만 배치할 수 있습니다.")
            if not self.start_value.strip() or not self.end_value.strip():
                raise ValueError("상승 추세선에는 검증된 시작값과 종료값이 필요합니다.")
        self.anchor.validate()


def _fit_font(text: str, max_width: int, start_size: int):
    for size in range(start_size, 11, -1):
        font = _load_font(size)
        if font.getbbox(text)[2] - font.getbbox(text)[0] <= max_width:
            return font
    raise ValueError("소품 표면에 비해 사실 문구가 너무 깁니다.")


def _surface_text_style(kind: SurfaceKind) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """소품을 덮는 새 카드 없이 기존 배경 위에 읽을 수 있는 글자만 그린다."""
    if kind in {"monitor", "embedded_monitor"}:
        return (245, 251, 255, 255), (4, 18, 30, 220)
    if kind == "placard":
        return (42, 30, 18, 255), (255, 242, 187, 220)
    return (255, 247, 211, 255), (30, 41, 52, 220)


def _draw_upward_trend(
    draw: ImageDraw.ImageDraw,
    fact: VerifiedFact,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    text_cells: list[dict] | None = None,
    cell_prefix: str = "",
) -> None:
    """새 UI 상자 없이 기존 벽면 위에 상승 의미를 직접 그린다.

    이 도형의 값·방향은 Gemini에 맡기지 않는다. 시작/종료 수치와 변화량은 모두
    verified_facts 원문 검증을 통과한 문자열만 사용한다.
    """
    width = right - left
    height = bottom - top
    padding_x = max(10, round(width * 0.07))
    padding_y = max(8, round(height * 0.08))
    inner_left = left + padding_x
    inner_right = right - padding_x
    inner_top = top + padding_y
    inner_bottom = bottom - padding_y
    line_width = max(3, round(min(width, height) * 0.035))
    label_font = _fit_font(fact.label, width - 2 * padding_x, max(14, round(height * 0.16)))
    value_font = _fit_font(fact.value, max(36, round(width * 0.30)), max(16, round(height * 0.16)))
    point_font = _fit_font(fact.start_value, max(30, round(width * 0.22)), max(14, round(height * 0.14)))

    # 얇은 가이드선만 남겨 벽면과 분리된 카드처럼 보이지 않게 한다.
    for fraction in (0.30, 0.55, 0.80):
        y = round(inner_top + (inner_bottom - inner_top) * fraction)
        draw.line((inner_left, y, inner_right, y), fill=(72, 236, 240, 72), width=max(1, line_width // 3))

    title_y = inner_top
    def write(xy, text, *, role, font, **style):
        draw_text_cell(draw, xy, text, font=font, cells=text_cells, cell_id=f"{cell_prefix}:{role}",
                       role=role, anchor_bbox=(left, top, right, bottom), **style)

    write((inner_left, title_y), fact.label, role="label", font=label_font, fill=(225, 251, 255, 255))
    chart_top = title_y + label_font.getbbox(fact.label)[3] + max(4, round(height * 0.04))
    chart_bottom = inner_bottom - max(16, round(height * 0.18))
    start = (inner_left + round((inner_right - inner_left) * 0.10), chart_bottom)
    elbow = (inner_left + round((inner_right - inner_left) * 0.48), chart_bottom - round((chart_bottom - chart_top) * 0.28))
    end = (inner_left + round((inner_right - inner_left) * 0.83), chart_top + round((chart_bottom - chart_top) * 0.08))
    glow_width = line_width + max(3, line_width)
    draw.line((start, elbow, end), fill=(20, 176, 197, 120), width=glow_width, joint="curve")
    draw.line((start, elbow, end), fill=(255, 204, 66, 255), width=line_width, joint="curve")
    arrow = max(8, round(width * 0.035))
    draw.polygon(
        [(end[0], end[1] - arrow), (end[0] + arrow, end[1] + arrow), (end[0] - arrow, end[1] + arrow)],
        fill=(255, 204, 66, 255),
    )
    dot_radius = max(4, round(line_width * 0.80))
    for point in (start, end):
        draw.ellipse(
            (point[0] - dot_radius, point[1] - dot_radius, point[0] + dot_radius, point[1] + dot_radius),
            fill=(255, 244, 183, 255), outline=(7, 51, 68, 255), width=max(1, line_width // 3),
        )
    write((start[0] - dot_radius, min(inner_bottom - 14, start[1] + dot_radius + 2)), fact.start_value, role="start_value", font=point_font, fill=(222, 249, 255, 255))
    end_box = point_font.getbbox(fact.end_value)
    write((end[0] - (end_box[2] - end_box[0]) / 2, end[1] + arrow + 8 - end_box[1]),
          fact.end_value, role="end_value", font=point_font, fill=(255, 239, 168, 255))
    # 종료값은 화살표 아래, 변화량은 제목 우측으로 분리한다. 긴 문구가
    # 공간을 침범하면 문자별 위치 검증에서 거절하며 값을 잘라 맞추지 않는다.
    value_x = inner_right - value_font.getbbox(fact.value)[2]
    write((value_x, title_y), fact.value, role="value", font=value_font, fill=(255, 215, 86, 255), stroke_width=1, stroke_fill=(4, 27, 42, 220))


def apply_facts_to_surfaces(base_png: bytes, facts: tuple[VerifiedFact, ...], *, text_cells: list[dict] | None = None) -> bytes:
    """검증 사실을 지정 소품 표면에만 합성한다.

    ``facts``의 각 항목은 명시적인 출처와 좌표를 가져야 한다. 따라서 빈 화면이나
    임의 위치에 정보를 덧씌우는 일반 패널 경로로 사용할 수 없다.
    """
    for fact in facts:
        fact.validate()

    image = Image.open(io.BytesIO(base_png)).convert("RGBA")
    width, height = image.size
    draw = ImageDraw.Draw(image)
    for index, fact in enumerate(facts):
        anchor = fact.anchor
        left = round(anchor.x * width)
        top = round(anchor.y * height)
        right = round((anchor.x + anchor.width) * width)
        bottom = round((anchor.y + anchor.height) * height)
        if fact.visualization == "upward_trend":
            _draw_upward_trend(draw, fact, left=left, top=top, right=right, bottom=bottom,
                               text_cells=text_cells, cell_prefix=f"overlay:{index}")
            continue
        text_fill, stroke_fill = _surface_text_style(anchor.kind)
        stroke_width = max(2, round(min(width, height) * 0.003))
        padding = max(4, round((right - left) * 0.05))
        label_font = _fit_font(fact.label, max(20, right - left - 2 * padding), max(14, round((bottom - top) * 0.32)))
        value_font = _fit_font(fact.value, max(20, right - left - 2 * padding), max(16, round((bottom - top) * 0.45)))
        
        # 2D 카툰 잉크 아웃라인 적용 (배경 그림과 자연스럽게 결합)
        dark_ink_stroke = (12, 18, 28, 240)
        draw_text_cell(draw,
            (left + padding, top + round((bottom - top) * 0.05)),
            fact.label,
            cells=text_cells, cell_id=f"overlay:{index}:label", role="label", anchor_bbox=(left, top, right, bottom),
            font=label_font,
            fill=text_fill,
            stroke_width=stroke_width,
            stroke_fill=dark_ink_stroke,
        )
        value_fill = (255, 224, 102, 255) if anchor.kind in {"monitor", "embedded_monitor"} else text_fill
        draw_text_cell(draw,
            (left + padding, top + round((bottom - top) * 0.48)),
            fact.value,
            cells=text_cells, cell_id=f"overlay:{index}:value", role="value", anchor_bbox=(left, top, right, bottom),
            font=value_font,
            fill=value_fill,
            stroke_width=stroke_width + 1,
            stroke_fill=dark_ink_stroke,
        )

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()


_FACT_REF = re.compile(r"^(?:facts|verified_facts)\[(\d+)]$")


def facts_from_verified_scene(scene: dict[str, Any]) -> tuple[VerifiedFact, ...]:
    """V5 씬 계약의 ``v5_verified_overlays``를 렌더 가능한 사실로 검증한다.

    수치·날짜·금액은 반드시 이미 검증된 ``verified_facts`` 원문 안에 그대로
    존재해야 한다. 대본이나 이미지 모델이 새 값을 만들어 이 경로로 보내는 일을
    막기 위한 fail-closed 어댑터다.
    """
    raw_overlays = scene.get("v5_verified_overlays")
    if raw_overlays is None:
        return ()
    if not isinstance(raw_overlays, list):
        raise ValueError("v5_verified_overlays는 목록이어야 합니다.")
    verified_facts = scene.get("verified_facts")
    if not isinstance(verified_facts, list):
        raise ValueError("검증 수치 오버레이에는 verified_facts가 필요합니다.")

    result: list[VerifiedFact] = []
    for raw in raw_overlays:
        if not isinstance(raw, dict):
            raise ValueError("검증 수치 오버레이 항목은 객체여야 합니다.")
        source_ref = str(raw.get("source_ref") or "")
        match = _FACT_REF.fullmatch(source_ref)
        if match is None:
            raise ValueError("검증 수치 오버레이의 source_ref는 facts[n] 형식이어야 합니다.")
        index = int(match.group(1))
        if index >= len(verified_facts) or not isinstance(verified_facts[index], dict):
            raise ValueError("검증 수치 오버레이가 존재하지 않는 사실을 참조합니다.")
        value = str(raw.get("value") or "")
        fact = verified_facts[index]
        if not verified_fact_contains_value(
            fact, value, require_structured_value_match=True,
        ):
            raise ValueError("오버레이 값은 참조한 verified_facts 원문에 그대로 있어야 합니다.")
        visualization = str(raw.get("visualization") or "text")
        start_value = str(raw.get("start_value") or "")
        end_value = str(raw.get("end_value") or "")
        if visualization == "upward_trend":
            for trend_value in (start_value, end_value):
                if not verified_fact_contains_value(
                    fact, trend_value, require_structured_value_match=False,
                ):
                    raise ValueError("상승 추세선의 시작·종료값은 참조한 verified_facts 원문에 그대로 있어야 합니다.")
        raw_anchor = raw.get("anchor")
        if not isinstance(raw_anchor, dict):
            raise ValueError("검증 수치 오버레이에는 소품 표면 좌표가 필요합니다.")
        try:
            anchor = SurfaceAnchor(
                x=float(raw_anchor["x"]), y=float(raw_anchor["y"]),
                width=float(raw_anchor["width"]), height=float(raw_anchor["height"]),
                kind=str(raw_anchor["kind"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("소품 표면 좌표 형식이 올바르지 않습니다.") from exc
        result.append(VerifiedFact(
            str(raw.get("label") or ""), value, source_ref, anchor,
            visualization=visualization, start_value=start_value, end_value=end_value,
        ))
    return tuple(result)


def _v5_archetype(scene: dict[str, Any]) -> str | None:
    """V5 런타임 계약에 기록된 archetype만 반환한다.

    과거의 독립 오버레이 도구는 V5 계약 없이도 사용할 수 있으므로, 계약이
    없는 입력에는 이 검사를 강제하지 않는다. 반대로 계약이 있는 운영 씬은
    primary 표면을 벗어난 사실값을 절대 합성할 수 없어야 한다.
    """
    contract = scene.get("v5_render_contract")
    if not isinstance(contract, dict):
        return None
    selection = contract.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("V5 렌더 계약에 archetype 선택 정보가 없습니다.")
    archetype = str(selection.get("archetype") or "").strip()
    if not archetype:
        raise ValueError("V5 렌더 계약의 archetype이 비어 있습니다.")
    return archetype


def _is_inside_primary_surface(
    anchor: SurfaceAnchor,
    region: tuple[float, float, float, float],
) -> bool:
    """사실 오버레이가 V5 primary 표면 안에 완전히 들어가는지 확인한다."""
    region_x, region_y, region_width, region_height = region
    epsilon = 1e-9
    return (
        anchor.x + epsilon >= region_x
        and anchor.y + epsilon >= region_y
        and anchor.x + anchor.width <= region_x + region_width + epsilon
        and anchor.y + anchor.height <= region_y + region_height + epsilon
    )


def _validate_v5_primary_surface(scene: dict[str, Any], facts: tuple[VerifiedFact, ...]) -> None:
    """V5 사실값이 선택된 archetype의 primary 표면 밖으로 새는 것을 차단한다."""
    archetype = _v5_archetype(scene)
    if archetype is None or not facts:
        return

    # 순환 의존성을 피하려고 실제 V5 계약이 필요한 시점에만 좌표 정의를 읽는다.
    from app.v5.scene.scene_type_archetypes import primary_surface_region

    region = primary_surface_region(archetype)
    for fact in facts:
        if not _is_inside_primary_surface(fact.anchor, region):
            raise ValueError(
                f"{archetype}: 검증 수치 오버레이는 V5 primary 표면 안에만 배치할 수 있습니다."
            )


def validated_facts_from_verified_scene(scene: dict[str, Any]) -> tuple[VerifiedFact, ...]:
    """검증 원문과 V5 primary 표면 계약을 모두 통과한 사실만 반환한다."""
    facts = facts_from_verified_scene(scene)
    _validate_v5_primary_surface(scene, facts)
    return facts


def apply_verified_scene_facts(base_png: bytes, scene: dict[str, Any]) -> bytes:
    """검증 씬의 소품-표면 오버레이를 합성한다. 오버레이가 없으면 원본을 유지한다."""
    facts = validated_facts_from_verified_scene(scene)
    cells: list[dict] = []
    rendered = apply_facts_to_surfaces(base_png, facts, text_cells=cells)
    if facts:
        with Image.open(io.BytesIO(rendered)) as frame:
            set_manifest(scene, frame.size, cells)
    return rendered

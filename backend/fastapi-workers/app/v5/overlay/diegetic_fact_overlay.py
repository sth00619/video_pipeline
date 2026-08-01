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


# ``embedded_monitor``는 배경에 AI가 이미 그린 물리 모니터의 *내부 화면*만
# 갱신한다. 프레임 전체 위에 새 정보 카드를 얹는 용도가 아니다.
SurfaceKind = Literal["monitor", "placard", "gauge_caption", "embedded_monitor"]


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

    def validate(self) -> None:
        if not self.label.strip() or not self.value.strip():
            raise ValueError("검증 사실의 항목명과 값은 비어 있을 수 없습니다.")
        if not self.source_ref.strip():
            raise ValueError("검증 사실에는 출처 참조가 필요합니다.")
        self.anchor.validate()


def _fit_font(text: str, max_width: int, start_size: int):
    for size in range(start_size, 11, -1):
        font = _load_font(size)
        if font.getbbox(text)[2] - font.getbbox(text)[0] <= max_width:
            return font
    raise ValueError("소품 표면에 비해 사실 문구가 너무 깁니다.")


def _surface_style(kind: SurfaceKind) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], tuple[int, int, int, int]]:
    if kind == "embedded_monitor":
        return (7, 25, 42, 255), (68, 202, 231, 255), (241, 250, 255, 255)
    if kind == "monitor":
        return (7, 29, 42, 225), (78, 225, 255, 255), (245, 251, 255, 255)
    if kind == "placard":
        return (255, 242, 187, 235), (79, 51, 24, 255), (42, 30, 18, 255)
    return (30, 41, 52, 220), (222, 168, 58, 255), (255, 247, 211, 255)


def apply_facts_to_surfaces(base_png: bytes, facts: tuple[VerifiedFact, ...]) -> bytes:
    """검증 사실을 지정 소품 표면에만 합성한다.

    ``facts``의 각 항목은 명시적인 출처와 좌표를 가져야 한다. 따라서 빈 화면이나
    임의 위치에 정보를 덧씌우는 일반 패널 경로로 사용할 수 없다.
    """
    for fact in facts:
        fact.validate()

    image = Image.open(io.BytesIO(base_png)).convert("RGBA")
    width, height = image.size
    draw = ImageDraw.Draw(image)
    for fact in facts:
        anchor = fact.anchor
        left = round(anchor.x * width)
        top = round(anchor.y * height)
        right = round((anchor.x + anchor.width) * width)
        bottom = round((anchor.y + anchor.height) * height)
        fill, outline, text_fill = _surface_style(anchor.kind)
        border = max(2, round(min(width, height) * 0.0025))
        radius = max(4, round(min(right - left, bottom - top) * 0.08))
        if anchor.kind == "embedded_monitor":
            # 모니터 베젤은 이미지 모델이 만든 배경을 그대로 유지한다. 여기서는
            # 안쪽 발광 화면을 정리하고 실제 정보만 넣어 장면 속 소품처럼 보이게 한다.
            inner = max(2, round(min(right - left, bottom - top) * 0.035))
            draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=fill)
            draw.rounded_rectangle((left, top, right, bottom), radius=radius, outline=outline, width=border)
            grid_color = (60, 142, 167, 255)
            for fraction in (.33, .66):
                x = round(left + (right - left) * fraction)
                draw.line((x, top + inner, x, bottom - inner), fill=grid_color, width=1)
            draw.line((left + inner, round(top + (bottom - top) * .76), right - inner, round(top + (bottom - top) * .76)), fill=grid_color, width=1)
        else:
            draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=fill, outline=outline, width=border)

        padding = max(6, round((right - left) * 0.07))
        label_font = _fit_font(fact.label, right - left - 2 * padding, max(14, round((bottom - top) * 0.23)))
        value_font = _fit_font(fact.value, right - left - 2 * padding, max(16, round((bottom - top) * 0.35)))
        draw.text((left + padding, top + round((bottom - top) * 0.14)), fact.label, font=label_font, fill=text_fill)
        value_fill = (255, 214, 77, 255) if anchor.kind in {"monitor", "embedded_monitor"} else text_fill
        draw.text(
            (left + padding, top + round((bottom - top) * 0.49)),
            fact.value,
            font=value_font,
            fill=value_fill,
            stroke_width=max(1, border // 2),
            stroke_fill=(0, 0, 0, 170),
        )

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()


_FACT_REF = re.compile(r"^(?:facts|verified_facts)\[(\d+)]$")


def _normalise(value: str) -> str:
    return "".join(value.split()).casefold()


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
        evidence = " ".join(str(fact.get(key) or "") for key in ("figure", "fact"))
        if not value.strip() or _normalise(value) not in _normalise(evidence):
            raise ValueError("오버레이 값은 참조한 verified_facts 원문에 그대로 있어야 합니다.")
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
        result.append(VerifiedFact(str(raw.get("label") or ""), value, source_ref, anchor))
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
    return apply_facts_to_surfaces(base_png, facts)

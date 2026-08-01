"""V5 장면의 안전영역을 결정론적으로 계획한다.

이 모듈의 SVG는 개발 검토용 산출물일 뿐 이미지 모델에 참조 이미지로 전달하지
않는다. 래스터 레이아웃 가이드가 장면의 테두리로 복제되는 문제를 막기 위함이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path


@dataclass(frozen=True)
class NormalizedRect:
    """16:9 프레임을 기준으로 하는 0~1 좌표 사각형."""

    x: float
    y: float
    width: float
    height: float

    def validate(self) -> None:
        if not (0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0):
            raise ValueError("안전영역 시작 좌표는 0~1 범위여야 합니다.")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("안전영역의 너비와 높이는 양수여야 합니다.")
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("안전영역은 프레임 밖으로 나갈 수 없습니다.")


@dataclass(frozen=True)
class LayoutPlan:
    """생성 전 레이아웃 계약. 수치·문구 자체는 포함하지 않는다."""

    scene_id: str
    mascot: NormalizedRect
    fact_overlay: NormalizedRect
    subtitle: NormalizedRect
    logo: NormalizedRect
    mascot_position: str = "right"

    def validate(self) -> None:
        if not self.scene_id:
            raise ValueError("scene_id가 필요합니다.")
        for region in (self.mascot, self.fact_overlay, self.subtitle, self.logo):
            region.validate()
        if _overlaps(self.mascot, self.subtitle) or _overlaps(self.mascot, self.logo):
            raise ValueError("마스코트가 자막 또는 로고 안전영역과 겹칩니다.")

    def prompt_instruction(self) -> str:
        """문자·선·프레임을 만들지 않도록 상대적 배치만 언어로 전달한다."""
        self.validate()
        position_words = {
            "left": "left-side foreground",
            "center": "center foreground",
            "right": "right-side foreground",
        }
        position = position_words.get(self.mascot_position)
        if position is None:
            raise ValueError("지원하지 않는 마스코트 위치입니다.")
        return (
            f"LAYOUT CONTRACT: keep the mascot in the {position} and keep its face and hands away "
            "from a calm lower band and a quiet upper-right corner. Keep the designated mid-frame readable for a later "
            "fact overlay while preserving ordinary scene depth and fully dressed diegetic props. "
            "Do not draw any layout guide, safe-area outline, placeholder, or empty display."
        )

    def to_svg(self, *, width: int = 1920, height: int = 1080) -> str:
        """사람 검토용 무문자 SVG를 만든다. 이 SVG는 공급자 입력에 사용하지 않는다."""
        self.validate()
        def rect(region: NormalizedRect, color: str) -> str:
            return (
                f'<rect x="{region.x * width:.1f}" y="{region.y * height:.1f}" '
                f'width="{region.width * width:.1f}" height="{region.height * height:.1f}" '
                f'fill="none" stroke="{color}" stroke-width="6"/>'
            )
        return "\n".join((
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#112438"/>',
            rect(self.fact_overlay, "#70d9ff"), rect(self.mascot, "#ffd24a"),
            rect(self.subtitle, "#ffffff"), rect(self.logo, "#9ff3d5"), "</svg>",
        ))

    def write_svg(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_svg(), encoding="utf-8")


def _overlaps(left: NormalizedRect, right: NormalizedRect) -> bool:
    return not (
        left.x + left.width <= right.x or right.x + right.width <= left.x
        or left.y + left.height <= right.y or right.y + right.height <= left.y
    )


class LayoutSketcher:
    """장면의 마스코트 위치에 맞춰 안전영역을 계산한다."""

    @staticmethod
    def for_right_mascot(scene_id: str, *, occupancy: float) -> LayoutPlan:
        return LayoutSketcher.for_mascot_position(scene_id, occupancy=occupancy, position="right")

    @staticmethod
    def for_mascot_position(scene_id: str, *, occupancy: float, position: str) -> LayoutPlan:
        if not 0.25 <= occupancy <= 0.50:
            raise ValueError("마스코트 점유율은 0.25~0.50 범위여야 합니다.")
        if position not in {"left", "center", "right"}:
            raise ValueError("마스코트 위치는 left, center, right 중 하나여야 합니다.")
        # 점유율이 커져도 자막과 상단 우측 로고에는 침범하지 않도록 높이를 제한한다.
        mascot_width = min(0.39, max(0.31, occupancy * 0.85))
        mascot_x = {
            "left": 0.04,
            "center": 0.50 - mascot_width / 2,
            "right": 0.98 - mascot_width,
        }[position]
        fact_overlay = {
            "left": NormalizedRect(0.53, 0.17, 0.38, 0.52),
            "center": NormalizedRect(0.05, 0.17, 0.30, 0.52),
            "right": NormalizedRect(0.05, 0.17, 0.43, 0.52),
        }[position]
        plan = LayoutPlan(
            scene_id=scene_id,
            mascot=NormalizedRect(mascot_x, 0.16, mascot_width, 0.65),
            fact_overlay=fact_overlay,
            subtitle=NormalizedRect(0.03, 0.86, 0.94, 0.10),
            logo=NormalizedRect(0.83, 0.03, 0.14, 0.09),
            mascot_position=position,
        )
        plan.validate()
        return plan

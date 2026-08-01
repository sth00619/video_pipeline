"""V5 이미지의 규칙 기반 1차 품질 게이트.

이 단계는 사람·마스코트·문자를 인식하는 비전 모델을 흉내 내지 않는다. 대신
빈 배경, 소품 밀도 부족, 잘못된 종횡비처럼 재현 가능하게 측정되는 실패만 자동으로
차단한다. 마스코트 얼굴·손의 안전영역 침범은 후속 비전 게이트 전까지 사람 검토
항목으로 남긴다.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

import numpy as np
from PIL import Image, ImageFilter

from .layout_sketcher import LayoutPlan, LayoutSketcher
from .prompt_builder import SceneSpec
from .scene_type_archetypes import primary_surface_region


Decision = Literal["pass", "retry_once", "manual_review_required", "downgrade_to_v4_cutaway"]


@dataclass(frozen=True)
class ScreenPanelCandidate:
    """primary 밖에서 감지한 사각 화면형 소품 후보다."""

    x: float
    y: float
    width: float
    height: float
    score: float


@dataclass(frozen=True)
class ScoreCard:
    """자동 측정값과 사람이 확인해야 하는 항목을 함께 보관한다."""

    scene_id: str
    passed: bool
    score: int
    aspect_ratio: float
    edge_density: float
    blank_tile_ratio: float
    prop_detail_regions: int
    gold_signal_ratio: float
    safe_zone_noise_ratio: float
    failures: tuple[str, ...]
    human_review: tuple[str, ...]
    primary_surface_region: tuple[float, float, float, float] | None = None
    foreign_screen_panels: tuple[ScreenPanelCandidate, ...] = ()


class QualityGate:
    """이미지 통계만으로 확실하게 판별 가능한 V5 실패를 먼저 막는다."""

    _GRID = 8
    # 평면 셀 셰이딩 장면은 큰 색면이 많아 전체 윤곽 비율이 낮다. 빈 단색
    # 프레임(거의 0)과 정상 일러스트를 구분하는 보수적 하한만 둔다.
    _MIN_EDGE_DENSITY = 0.020
    _MAX_BLANK_TILE_RATIO = 0.35
    _MIN_PROP_DETAIL_REGIONS = 3

    @classmethod
    def score(cls, image_bytes: bytes, spec: SceneSpec, layout: LayoutPlan | None = None) -> ScoreCard:
        spec.validate()
        plan = layout or LayoutSketcher.for_mascot_position(
            spec.scene_id, occupancy=spec.frame_occupancy, position=spec.character_position,
        )
        plan.validate()
        with Image.open(io.BytesIO(image_bytes)) as loaded:
            image = loaded.convert("RGB")
        width, height = image.size
        ratio = width / height if height else 0.0
        gray = np.asarray(image.convert("L"), dtype=np.float32)
        edges = np.asarray(image.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
        edge_density = float(np.mean(edges > 38))
        blank_ratio, detail_regions = cls._grid_statistics(gray, edges, plan)
        rgb = np.asarray(image, dtype=np.uint8)
        gold_signal_ratio = cls._gold_signal_ratio(rgb)
        safe_zone_noise = cls._safe_zone_noise(edges, plan)
        primary_region = primary_surface_region(spec.archetype)
        foreign_screen_panels = cls._foreign_screen_panels(rgb, primary_region)

        failures: list[str] = []
        if not 1.72 <= ratio <= 1.83:
            failures.append("16:9 종횡비 이탈")
        if edge_density < cls._MIN_EDGE_DENSITY:
            failures.append("전체 윤곽·세부 묘사가 부족함")
        if blank_ratio > cls._MAX_BLANK_TILE_RATIO:
            failures.append("빈 배경 비율이 높음")
        if detail_regions < cls._MIN_PROP_DETAIL_REGIONS:
            failures.append("마스코트 외 소품 밀도가 부족함")

        if foreign_screen_panels:
            failures.append("primary 외 화면형 보조 소품 감지")

        score = 100
        score -= min(35, round(blank_ratio * 100))
        score -= max(0, cls._MIN_PROP_DETAIL_REGIONS - detail_regions) * 10
        score -= 25 if edge_density < cls._MIN_EDGE_DENSITY else 0
        score -= 20 if not 1.72 <= ratio <= 1.83 else 0
        score = max(0, score)
        return ScoreCard(
            scene_id=spec.scene_id,
            passed=not failures,
            score=score,
            aspect_ratio=round(ratio, 4),
            edge_density=round(edge_density, 4),
            blank_tile_ratio=round(blank_ratio, 4),
            prop_detail_regions=detail_regions,
            gold_signal_ratio=round(gold_signal_ratio, 4),
            safe_zone_noise_ratio=round(safe_zone_noise, 4),
            failures=tuple(failures),
            human_review=(
                "마스코트의 실제 면적·얼굴·손 위치는 사람 또는 후속 비전 모델이 확인해야 합니다.",
                "AI가 만든 영어·숫자는 장식인지 여부를 사람이 확인해야 합니다.",
                "한 장의 연속된 무대인지, 만화 분할컷·삽입 패널·내부 프레임처럼 보이는 경계가 없는지 사람이 확인해야 합니다.",
                "마스코트의 동공·얼굴·테두리 비율이 기준 캐릭터와 같은지 사람이 확인해야 합니다.",
            ),
            primary_surface_region=primary_region,
            foreign_screen_panels=tuple(foreign_screen_panels),
        )

    @staticmethod
    def next_action(card: ScoreCard, *, generation_attempt: int, retry_budget_available: bool) -> Decision:
        """한 번만 재생성하고, 그 뒤에는 기존 V4 cutaway로 안전하게 강등한다."""
        if card.passed:
            return "pass"
        if card.foreign_screen_panels:
            return "manual_review_required"
        if generation_attempt == 0 and retry_budget_available:
            return "retry_once"
        return "downgrade_to_v4_cutaway"

    @classmethod
    def _foreign_screen_panels(
        cls,
        rgb: np.ndarray,
        primary_region: tuple[float, float, float, float],
    ) -> list[ScreenPanelCandidate]:
        """테두리·균일 내부·주변 대비를 가진 primary 밖 사각 화면 후보를 찾는다.

        외부 비전 모델 없이 Pillow/NumPy만 사용한다. 이 검사는 확정 OCR이 아니라
        화면형 보조 소품을 자동 실패로 올리고 사람의 재생성 결정을 요구하는 1차 방어선이다.
        """
        height, width = rgb.shape[:2]
        scale = min(1.0, 384 / max(width, height))
        if scale < 1.0:
            resized = Image.fromarray(rgb).resize(
                (round(width * scale), round(height * scale)), Image.Resampling.BILINEAR,
            )
            sample = np.asarray(resized, dtype=np.float32)
        else:
            sample = rgb.astype(np.float32)
        sample_height, sample_width = sample.shape[:2]
        gray = 0.299 * sample[:, :, 0] + 0.587 * sample[:, :, 1] + 0.114 * sample[:, :, 2]
        horizontal = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
        vertical = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
        gradient = horizontal + vertical
        candidates: list[ScreenPanelCandidate] = []
        shapes = (
            (0.09, 0.08), (0.12, 0.10), (0.15, 0.12), (0.16, 0.18),
            (0.12, 0.30), (0.12, 0.40), (0.14, 0.32), (0.15, 0.42),
            (0.20, 0.14), (0.23, 0.18),
            (0.28, 0.20), (0.32, 0.24),
        )
        for relative_width, relative_height in shapes:
            panel_width = max(18, round(sample_width * relative_width))
            panel_height = max(16, round(sample_height * relative_height))
            stride = max(4, min(panel_width, panel_height) // 5)
            for top in range(1, max(2, sample_height - panel_height), stride):
                for left in range(1, max(2, sample_width - panel_width), stride):
                    rect = (
                        left / sample_width,
                        top / sample_height,
                        panel_width / sample_width,
                        panel_height / sample_height,
                    )
                    if cls._overlap_ratio(rect, primary_region) >= 0.55:
                        continue
                    if rect[2] * rect[3] < 0.030:
                        continue
                    border = max(2, min(panel_width, panel_height) // 12)
                    inner = gray[top + border:top + panel_height - border, left + border:left + panel_width - border]
                    if inner.size == 0 or float(np.std(inner)) > 85.0:
                        continue
                    inner_rgb = sample[
                        top + border:top + panel_height - border,
                        left + border:left + panel_width - border,
                    ]
                    # 단순 액자·종이·벽 장식은 제외하고, 화면형 패널 특유의
                    # 균일한 고채도 발광면만 대상으로 좁힌다. 이 조건은 고정된
                    # job_market_hall의 종이 안내물 오탐을 막는다.
                    red, green, blue = inner_rgb[:, :, 0], inner_rgb[:, :, 1], inner_rgb[:, :, 2]
                    maximum = np.max(inner_rgb, axis=2)
                    minimum = np.min(inner_rgb, axis=2)
                    # 금색 테두리·조명 같은 일반 카툰 장식은 화면으로 세지 않는다.
                    # 보조 디스플레이에서 반복된 청록/청색·적색 발광면만 허용한다.
                    cool_display = (blue >= red + 12.0) & (green >= red + 4.0)
                    red_display = (red >= 185.0) & (green <= 130.0) & (blue <= 130.0)
                    luminous_color_ratio = float(np.mean(
                        (maximum >= 165.0) & ((maximum - minimum) >= 35.0) & (cool_display | red_display)
                    ))
                    if luminous_color_ratio < 0.50:
                        continue
                    top_edge = float(np.mean(gradient[top:top + border, left:left + panel_width] > 26.0))
                    bottom_edge = float(np.mean(gradient[top + panel_height - border:top + panel_height, left:left + panel_width] > 26.0))
                    left_edge = float(np.mean(gradient[top:top + panel_height, left:left + border] > 26.0))
                    right_edge = float(np.mean(gradient[top:top + panel_height, left + panel_width - border:left + panel_width] > 26.0))
                    edge_sides = sum(value >= 0.16 for value in (top_edge, bottom_edge, left_edge, right_edge))
                    # 16:9 프레임을 축소한 픽셀 좌표에서 세로 패널은 약 1.5:1부터
                    # 나타난다. 정규화 좌표 비율을 그대로 비교하면 놓치게 된다.
                    tall_narrow_panel = panel_height / panel_width >= 1.5
                    solid_luminous_panel = (
                        tall_narrow_panel
                        and luminous_color_ratio >= 0.75
                        and float(np.std(inner)) <= 65.0
                    )
                    if edge_sides < 3 and not (
                        solid_luminous_panel and edge_sides >= 1
                    ):
                        continue
                    outer_left = max(0, left - border)
                    outer_top = max(0, top - border)
                    outer_right = min(sample_width, left + panel_width + border)
                    outer_bottom = min(sample_height, top + panel_height + border)
                    outer = gray[outer_top:outer_bottom, outer_left:outer_right]
                    contrast = abs(float(np.mean(inner)) - float(np.mean(outer)))
                    if contrast < 8.0 and not solid_luminous_panel:
                        continue
                    score = round((top_edge + bottom_edge + left_edge + right_edge) * 25 + contrast / 3, 2)
                    if score < 24.0 and not solid_luminous_panel:
                        continue
                    candidates.append(ScreenPanelCandidate(*rect, score=score))
        return cls._deduplicate_panels(candidates)

    @staticmethod
    def _overlap_ratio(
        left: tuple[float, float, float, float],
        right: tuple[float, float, float, float],
    ) -> float:
        left_x, left_y, left_width, left_height = left
        right_x, right_y, right_width, right_height = right
        overlap_width = max(0.0, min(left_x + left_width, right_x + right_width) - max(left_x, right_x))
        overlap_height = max(0.0, min(left_y + left_height, right_y + right_height) - max(left_y, right_y))
        overlap = overlap_width * overlap_height
        area = left_width * left_height
        return overlap / area if area else 0.0

    @classmethod
    def _deduplicate_panels(cls, candidates: list[ScreenPanelCandidate]) -> list[ScreenPanelCandidate]:
        selected: list[ScreenPanelCandidate] = []
        for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
            rect = (candidate.x, candidate.y, candidate.width, candidate.height)
            if any(cls._overlap_ratio(rect, (item.x, item.y, item.width, item.height)) >= 0.45 for item in selected):
                continue
            selected.append(candidate)
        return selected[:6]

    @classmethod
    def _grid_statistics(cls, gray: np.ndarray, edges: np.ndarray, plan: LayoutPlan) -> tuple[float, int]:
        height, width = gray.shape
        blank_tiles = 0
        prop_regions = 0
        for row in range(cls._GRID):
            for column in range(cls._GRID):
                left = round(column * width / cls._GRID)
                right = round((column + 1) * width / cls._GRID)
                top = round(row * height / cls._GRID)
                bottom = round((row + 1) * height / cls._GRID)
                tile = gray[top:bottom, left:right]
                tile_edges = edges[top:bottom, left:right]
                deviation = float(np.std(tile))
                density = float(np.mean(tile_edges > 38))
                if deviation < 9.0 and density < 0.012:
                    blank_tiles += 1
                center_x = (column + .5) / cls._GRID
                center_y = (row + .5) / cls._GRID
                if not cls._inside(center_x, center_y, plan.mascot) and density >= 0.015:
                    prop_regions += 1
        return blank_tiles / (cls._GRID * cls._GRID), prop_regions

    @staticmethod
    def _inside(x: float, y: float, rect) -> bool:
        return rect.x <= x <= rect.x + rect.width and rect.y <= y <= rect.y + rect.height

    @staticmethod
    def _gold_signal_ratio(rgb: np.ndarray) -> float:
        red = rgb[:, :, 0].astype(np.int16)
        green = rgb[:, :, 1].astype(np.int16)
        blue = rgb[:, :, 2].astype(np.int16)
        gold = (red >= 160) & (green >= 90) & (blue <= 140) & (red > blue + 45)
        return float(np.mean(gold))

    @staticmethod
    def _safe_zone_noise(edges: np.ndarray, plan: LayoutPlan) -> float:
        height, width = edges.shape
        zones = (plan.subtitle, plan.logo)
        densities: list[float] = []
        for zone in zones:
            left, right = round(zone.x * width), round((zone.x + zone.width) * width)
            top, bottom = round(zone.y * height), round((zone.y + zone.height) * height)
            crop = edges[top:bottom, left:right]
            densities.append(float(np.mean(crop > 38)) if crop.size else 0.0)
        return sum(densities) / len(densities)

"""Deterministic four-gate verifier. All gates must pass to replace Phase A."""
from __future__ import annotations

import re
from typing import Protocol, Sequence

import cv2
import numpy as np

from .contracts import BarSpec, ExpectedText, GateReport


class TextReader(Protocol):
    def read_texts(self, image_bgr: np.ndarray) -> list[str]: ...


_WS = re.compile(r"\s+")


def _norm(value: str) -> str:
    # Whitespace only is normalized. Never treat O/0 or another glyph swap as
    # equivalent: numeric text is a factual invariant.
    return _WS.sub("", value.strip())


def text_integrity_gate(image_bgr: np.ndarray, expected: Sequence[ExpectedText], reader: TextReader) -> GateReport:
    found = "\x01".join(_norm(item) for item in reader.read_texts(image_bgr))
    missing = [item.text for item in expected if _norm(item.text) not in found]
    return GateReport(
        name="text_integrity", passed=not missing,
        detail="" if not missing else f"missing/altered: {missing}",
        metric=1 - len(missing) / max(1, len(expected)),
    )


def _ink_height(image_bgr: np.ndarray, bar: BarSpec, tolerance: int = 60) -> int:
    x, y, width, height = bar.bbox
    roi = image_bgr[y:y + height, x:x + width].astype(np.int16)
    if not roi.size:
        return 0
    bgr = np.asarray(bar.fill_rgb[::-1], dtype=np.int16)
    mask = np.abs(roi - bgr).sum(axis=2) < tolerance * 3
    rows = np.where(mask.any(axis=1))[0]
    return int(rows[-1] - rows[0] + 1) if rows.size else 0


def bar_geometry_gate(original_bgr: np.ndarray, stylized_bgr: np.ndarray, bars: Sequence[BarSpec], rel_tol: float = .03) -> GateReport:
    if len(bars) < 2:
        return GateReport(name="bar_geometry", passed=True, detail="bars<2, skip", metric=1.0)
    original = [max(1, _ink_height(original_bgr, bar)) for bar in bars]
    stylized = [max(1, _ink_height(stylized_bgr, bar)) for bar in bars]
    worst = max(
        abs((stylized[index] / stylized[0]) - (original[index] / original[0])) / max(original[index] / original[0], 1e-6)
        for index in range(1, len(bars))
    )
    return GateReport(name="bar_geometry", passed=worst <= rel_tol, detail=f"worst_ratio_drift={worst:.4f} (tol {rel_tol})", metric=worst)


def _lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb.reshape(1, -1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)


def palette_gate(image_bgr: np.ndarray, palette_rgb: Sequence[tuple[int, int, int]], delta_e_max: float = 14.0, k: int = 5, coverage_min: float = .90) -> GateReport:
    if not palette_rgb:
        return GateReport(name="palette", passed=False, detail="empty palette", metric=0.0)
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB).reshape(-1, 3)
    sample = rgb[::max(1, len(rgb) // 40000)]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(sample.astype(np.float32), min(k, len(sample)), None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    weights = np.bincount(labels.ravel(), minlength=len(centers)) / max(1, len(labels))
    token_lab = _lab(np.asarray(palette_rgb, dtype=np.uint8))
    off_weight, worst = 0.0, 0.0
    for center, weight in zip(_lab(centers.astype(np.uint8)), weights):
        distance = float(np.linalg.norm(token_lab - center, axis=1).min())
        if distance > delta_e_max:
            off_weight += float(weight); worst = max(worst, distance)
    coverage = 1 - off_weight
    return GateReport(name="palette", passed=coverage >= coverage_min, detail=f"off_palette_weight={off_weight:.3f}, worst_dE={worst:.1f}", metric=coverage)


def edge_iou_gate(original_bgr: np.ndarray, stylized_bgr: np.ndarray, iou_min: float = .80) -> GateReport:
    def edges(image: np.ndarray) -> np.ndarray:
        gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 1.2)
        return cv2.dilate(cv2.Canny(gray, 60, 160), np.ones((5, 5), np.uint8)) > 0
    first, second = edges(original_bgr), edges(stylized_bgr)
    union = float(np.logical_or(first, second).sum())
    iou = float(np.logical_and(first, second).sum()) / union if union else 1.0
    return GateReport(name="edge_iou", passed=iou >= iou_min, detail=f"iou={iou:.3f} (min {iou_min})", metric=iou)


def run_all_gates(original_bgr: np.ndarray, stylized_bgr: np.ndarray, *, expected_texts: Sequence[ExpectedText], bars: Sequence[BarSpec], palette_rgb: Sequence[tuple[int, int, int]], reader: TextReader) -> list[GateReport]:
    if original_bgr.shape != stylized_bgr.shape:
        return [GateReport(name="edge_iou", passed=False, detail=f"shape mismatch {original_bgr.shape} vs {stylized_bgr.shape}")]
    return [
        text_integrity_gate(stylized_bgr, expected_texts, reader),
        bar_geometry_gate(original_bgr, stylized_bgr, bars),
        palette_gate(stylized_bgr, palette_rgb),
        edge_iou_gate(original_bgr, stylized_bgr),
    ]

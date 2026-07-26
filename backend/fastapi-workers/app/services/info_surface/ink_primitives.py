"""Seeded, hand-inked primitives used by deterministic information surfaces."""
from __future__ import annotations

import math

import numpy as np
from PIL import ImageDraw


def seeded_rng(scene_seed: int | str | None) -> np.random.Generator:
    if isinstance(scene_seed, str):
        scene_seed = sum((index + 1) * ord(char) for index, char in enumerate(scene_seed))
    return np.random.default_rng(int(scene_seed or 0) & 0xFFFFFFFF)


def wobble_path(
    points: list[tuple[float, float]], *, amp_px: float = 2.0, wavelength_px: float = 36.0, rng: np.random.Generator,
) -> list[tuple[int, int]]:
    """Perturb points only along the path normal; output is repeatable by seed."""
    if len(points) < 2:
        return [(round(x), round(y)) for x, y in points]
    result: list[tuple[int, int]] = []
    distance = 0.0
    for index, (x, y) in enumerate(points):
        before = points[max(0, index - 1)]
        after = points[min(len(points) - 1, index + 1)]
        dx, dy = after[0] - before[0], after[1] - before[1]
        length = max(1e-6, math.hypot(dx, dy))
        normal = (-dy / length, dx / length)
        if index:
            distance += math.hypot(x - points[index - 1][0], y - points[index - 1][1])
        offset = math.sin(distance / max(1.0, wavelength_px) * math.tau) * amp_px + rng.uniform(-amp_px * .18, amp_px * .18)
        result.append((round(x + normal[0] * offset), round(y + normal[1] * offset)))
    return result


def ink_line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], *, fill: str, width: int, rng: np.random.Generator) -> None:
    path = wobble_path(points, amp_px=max(1.0, width * .20), wavelength_px=max(18.0, width * 7), rng=rng)
    draw.line(path, fill=fill, width=width, joint="curve")


def ink_bar(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str,
    outline_px: int,
    rng: np.random.Generator,
) -> None:
    left, top, right, bottom = rect
    overshoot = max(1, outline_px // 2)
    polygon = [
        (left + rng.integers(-overshoot, overshoot + 1), bottom),
        (left + rng.integers(-overshoot, overshoot + 1), top + rng.integers(-overshoot, overshoot + 1)),
        (right + rng.integers(-overshoot, overshoot + 1), top + rng.integers(-overshoot, overshoot + 1)),
        (right + rng.integers(-overshoot, overshoot + 1), bottom),
    ]
    draw.polygon(polygon, fill=fill)
    draw.line(polygon + [polygon[0]], fill=outline, width=outline_px, joint="curve")
    # A sparse interior hatch reads as ink, not as a flat mobile UI widget.
    for x in range(left + outline_px * 2, right - outline_px, max(10, outline_px * 3)):
        draw.line((x, bottom - outline_px * 2, min(right - 1, x + (bottom - top) // 5), top + outline_px * 2), fill=outline, width=1)


def ink_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    fill: str,
    outline: str,
    width: int,
    rng: np.random.Generator,
) -> None:
    ink_line(draw, [start, end], fill=outline, width=width + 5, rng=rng)
    ink_line(draw, [start, end], fill=fill, width=width, rng=rng)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = max(14, width * 2)
    left = (end[0] - head * math.cos(angle - .55), end[1] - head * math.sin(angle - .55))
    right = (end[0] - head * math.cos(angle + .55), end[1] - head * math.sin(angle + .55))
    draw.polygon([end, left, right], fill=fill, outline=outline)


def ink_underline(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], *, fill: str, width: int, rng: np.random.Generator) -> None:
    ink_line(draw, [start, end], fill=fill, width=width, rng=rng)

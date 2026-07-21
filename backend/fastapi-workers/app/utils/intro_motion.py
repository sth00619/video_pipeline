"""Deterministic, intro-only image-to-video allocation.

This module intentionally contains no FFmpeg motion logic.  Fal/Kling clips
are the only animated visual treatment, and they occupy a contiguous opening
window; every later scene remains a static, jitter-free image.
"""
from __future__ import annotations

from typing import Iterable


MAX_MOTION_SECONDS_PER_CLIP = 5.0


def intro_motion_budget_seconds(
    total_duration: float,
    *,
    short_seconds: float,
    long_seconds: float,
    short_threshold: float,
) -> float:
    """Return the permitted contiguous opening motion duration in seconds."""
    if total_duration <= 0:
        return 0.0
    return float(short_seconds if total_duration <= short_threshold else long_seconds)


def scene_duration_seconds(scene: dict, default_seconds: float = 5.0) -> float:
    """Read a positive scene duration without allowing malformed metadata to grow cost."""
    for key in ("duration", "estimated_seconds"):
        try:
            value = float(scene.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    try:
        start = float(scene.get("start_seconds"))
        end = float(scene.get("end_seconds"))
        if end > start:
            return end - start
    except (TypeError, ValueError):
        pass
    return float(default_seconds)


def infer_total_duration_seconds(scenes: Iterable[dict], default_seconds: float = 5.0) -> float:
    """Infer a conservative duration before TTS timing is available for preflight."""
    scene_list = list(scenes)
    if not scene_list:
        return 0.0
    explicit_ends = []
    for scene in scene_list:
        try:
            end = float(scene.get("end_seconds"))
        except (TypeError, ValueError):
            continue
        if end > 0:
            explicit_ends.append(end)
    if explicit_ends:
        return max(explicit_ends)
    return sum(scene_duration_seconds(scene, default_seconds) for scene in scene_list)


def select_intro_motion_scene_indices(
    scenes: Iterable[dict],
    total_duration: float,
    *,
    short_seconds: float,
    long_seconds: float,
    short_threshold: float,
    max_clips: int,
    clip_seconds: float = MAX_MOTION_SECONDS_PER_CLIP,
) -> tuple[set[int], float, float]:
    """Select only the earliest complete scenes that fit the configured Fal budget.

    A scene is never partially animated just to fill a remaining fraction.  This
    avoids provider-duration ambiguity and prevents a motion/freeze seam inside
    an otherwise short hook scene.
    """
    scene_list = list(scenes)
    target = intro_motion_budget_seconds(
        total_duration,
        short_seconds=short_seconds,
        long_seconds=long_seconds,
        short_threshold=short_threshold,
    )
    if target <= 0 or max_clips <= 0:
        return set(), target, 0.0

    selected: set[int] = set()
    actual = 0.0
    for index, scene in enumerate(scene_list):
        if len(selected) >= int(max_clips):
            break
        slice_seconds = min(
            max(1.0, min(float(clip_seconds), 5.0)),
            scene_duration_seconds(scene),
        )
        if slice_seconds <= 0 or actual + slice_seconds > target + 1e-6:
            break
        selected.add(index)
        actual += slice_seconds
    return selected, target, round(actual, 3)

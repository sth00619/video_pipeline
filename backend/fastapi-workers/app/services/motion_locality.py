"""Fal 결과가 피사체 동작인지 전 화면 흔들림인지 결정론적으로 검사한다."""
from __future__ import annotations

import json
import subprocess
from typing import Any

import numpy as np


MOTION_LOCALITY_POLICY_VERSION = 1


def assess_motion_frames(frames: list[np.ndarray]) -> dict[str, Any]:
    """저해상도 회색 프레임의 변화 범위로 전역 지글링을 차단한다."""
    if len(frames) < 2:
        return {
            "policy_version": MOTION_LOCALITY_POLICY_VERSION,
            "passed": False,
            "reasons": ["insufficient_frames"],
        }
    normalized = [np.asarray(frame, dtype=np.int16) for frame in frames]
    if any(frame.shape != normalized[0].shape or frame.ndim != 2 for frame in normalized):
        return {
            "policy_version": MOTION_LOCALITY_POLICY_VERSION,
            "passed": False,
            "reasons": ["invalid_frame_shape"],
        }

    baseline = normalized[0]
    maximum_difference = np.maximum.reduce([np.abs(frame - baseline) for frame in normalized[1:]])
    changed = maximum_difference >= 12
    changed_ratio = float(changed.mean())
    height, width = changed.shape
    border_y = max(1, round(height * 0.14))
    border_x = max(1, round(width * 0.14))
    border = np.zeros_like(changed, dtype=bool)
    border[:border_y, :] = True
    border[-border_y:, :] = True
    border[:, :border_x] = True
    border[:, -border_x:] = True
    border_changed_ratio = float(changed[border].mean())

    active_tiles = 0
    tile_count = 0
    for row in np.array_split(changed, 6, axis=0):
        for tile in np.array_split(row, 10, axis=1):
            tile_count += 1
            if float(tile.mean()) >= 0.04:
                active_tiles += 1
    active_tile_ratio = active_tiles / max(tile_count, 1)

    reasons: list[str] = []
    if changed_ratio < 0.008:
        reasons.append("motion_not_detected")
    if changed_ratio > 0.55:
        reasons.append("whole_frame_change")
    if active_tile_ratio > 0.72:
        reasons.append("global_motion_coverage")
    if border_changed_ratio > 0.38:
        reasons.append("camera_or_border_jitter")
    return {
        "policy_version": MOTION_LOCALITY_POLICY_VERSION,
        "passed": not reasons,
        "reasons": reasons,
        "changed_pixel_ratio": round(changed_ratio, 5),
        "active_tile_ratio": round(active_tile_ratio, 5),
        "border_changed_ratio": round(border_changed_ratio, 5),
    }


def _duration_seconds(video_path: str) -> float:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        return float(completed.stdout.strip()) if completed.returncode == 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _frame(video_path: str, position: float, *, width: int = 160, height: int = 90) -> np.ndarray | None:
    completed = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{position:.3f}",
            "-i", video_path, "-frames:v", "1", "-vf", f"scale={width}:{height},format=gray",
            "-f", "rawvideo", "-",
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0 or len(completed.stdout) != width * height:
        return None
    return np.frombuffer(completed.stdout, dtype=np.uint8).reshape((height, width))


def assess_video_motion_locality(video_path: str) -> dict[str, Any]:
    """Fal 표준화 클립의 세 시점을 검사해 피사체 국소 동작만 승인한다."""
    duration = _duration_seconds(video_path)
    if duration <= 0:
        return {
            "policy_version": MOTION_LOCALITY_POLICY_VERSION,
            "passed": False,
            "reasons": ["video_duration_unavailable"],
        }
    positions = [0.08, min(duration * 0.42, duration - 0.08), min(duration * 0.78, duration - 0.08)]
    frames = [_frame(video_path, max(0.0, position)) for position in positions]
    result = assess_motion_frames([frame for frame in frames if frame is not None])
    result["sample_positions"] = [round(position, 3) for position in positions]
    result["duration_seconds"] = round(duration, 3)
    return result


def compact_motion_failure(result: dict[str, Any]) -> str:
    """감사 로그와 예외에 넣을 안정적인 짧은 JSON을 반환한다."""
    return json.dumps(result, ensure_ascii=False, sort_keys=True)

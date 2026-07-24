from __future__ import annotations

FRAME_16_9 = (1920, 1080)
FRAME_9_16 = (1080, 1920)


class SafeAreas:
    SUBTITLE_H_RATIO = .18
    WATERMARK = (.78, 0.0, 1.0, .10)
    CONTENT_MARGIN = .045


def subtitle_zone(height: int) -> tuple[int, int]:
    return int(height * (1 - SafeAreas.SUBTITLE_H_RATIO)), height

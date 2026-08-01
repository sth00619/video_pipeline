"""NAVER 검색어 트렌드의 그림 내부 지도 라벨 회귀 테스트."""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.diegetic_trend_overlay import (
    MapTrendAnnotation,
    annotations_from_visual_data_pack,
    apply_weather_map_search_interest,
)


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1200, 675), "#1f4d75").save(output, format="PNG")
    return output.getvalue()


def test_annotations_keep_the_last_raw_ratio_without_rounding():
    pack = {"trend_series": [{"id": "search_trend_01", "title": "코스피", "points": [
        {"period": "2026-07-27", "ratio": 75.62063},
    ]}]}
    annotations = annotations_from_visual_data_pack(pack)
    assert annotations[0].ratio_text == "75.62063"
    assert annotations[0].label == "KOSPI"


def test_weather_annotations_change_only_map_label_regions():
    base = _png()
    rendered = apply_weather_map_search_interest(base, (
        MapTrendAnnotation("KOSPI", "75.62063", .2, .34, "search_trend_01"),
    ))
    before = Image.open(io.BytesIO(base)).convert("RGB")
    after = Image.open(io.BytesIO(rendered)).convert("RGB")
    assert before.getpixel((20, 20)) == after.getpixel((20, 20))
    assert before.getpixel((240, 230)) != after.getpixel((240, 230))

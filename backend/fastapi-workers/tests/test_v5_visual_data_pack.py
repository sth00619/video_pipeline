"""V5 장면 내 지표ㆍ그래프 데이터 팩의 사실 검증 테스트."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.data.visual_data_pack import VisualDataPackError, build_visual_data_pack


def _trends():
    return {"results": [{"title": "코스피", "data": [
        {"period": "2026-07-01", "ratio": 42.1}, {"period": "2026-07-08", "ratio": 55.2},
    ]}]}


def _fact(value: str = "5663.24"):
    return {
        "fact": f"코스피 종가는 {value}였다.", "figure": value,
        "overlay_label": "코스피 종가", "source_url": "https://example.com/article",
        "source_title": "검증 기사", "published_at": "2026-07-30T10:00:00+09:00", "source_field": "news[0]",
    }


def test_data_pack_keeps_verified_metrics_and_relative_trends_separate():
    pack = build_visual_data_pack(
        topic="코스피 7월 전망", verified_facts=[_fact(), _fact("-10.84%")], search_trend_payload=_trends(),
        collected_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )
    assert pack["metrics"][0]["value"] == "5663.24"
    assert pack["metric_surfaces"][1]["surface_family"] == "warning_gauge"
    assert pack["trend_series"][0]["points"][1]["ratio"] == 55.2
    assert "주가 변동률" in pack["trend_series"][0]["ratio_note"]


def test_data_pack_rejects_a_value_not_present_in_the_verified_fact():
    fact = _fact("5663.24")
    fact["fact"] = "코스피 종가는 다른 값이었다."
    with pytest.raises(VisualDataPackError, match="원문"):
        build_visual_data_pack(topic="코스피", verified_facts=[fact], search_trend_payload=_trends())


def test_data_pack_rejects_malformed_trend_points():
    with pytest.raises(VisualDataPackError, match="ratio"):
        build_visual_data_pack(
            topic="코스피", verified_facts=[_fact()],
            search_trend_payload={"results": [{"title": "코스피", "data": [{"period": "2026-07", "ratio": "100"}]}]},
        )

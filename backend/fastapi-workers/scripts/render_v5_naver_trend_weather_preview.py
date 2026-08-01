#!/usr/bin/env python3
"""NAVER 검색어 트렌드 값을 기존 날씨 지도 세트에 직접 표기한 무비용 미리보기."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.diegetic_trend_overlay import annotations_from_visual_data_pack, apply_weather_map_search_interest


PACK = ROOT / "out/v5_pilot/kospi_july_2026/visual_data_pack/visual_data_pack.json"
BACKGROUND = ROOT / "out/benchmark/gemini_pro_diegetic_v5_bench_05_weather/bench_05_weather.png"
OUTPUT = ROOT / "out/v5_pilot/kospi_july_2026/naver_trend_weather_preview"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    annotations = annotations_from_visual_data_pack(pack)
    image = apply_weather_map_search_interest(BACKGROUND.read_bytes(), annotations)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "kospi_naver_search_interest_weather_map.png"
    target.write_bytes(image)
    (OUTPUT / "provenance.json").write_text(json.dumps({
        "source": "naver_search_trend",
        "ratio_note": "표기 값은 NAVER 상대 검색 관심도이며 주가 변동률이 아닙니다.",
        "background": str(BACKGROUND),
        "annotations": [item.__dict__ for item in annotations],
        "cost_usd": 0,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

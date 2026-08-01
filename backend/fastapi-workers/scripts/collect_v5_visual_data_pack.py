#!/usr/bin/env python3
"""NAVER API와 검증된 뉴스 사실로 V5 이미지용 데이터 팩을 수집한다.

이미지 생성이나 Claude 호출은 수행하지 않는다. API 키는 환경 변수에서만 읽고
출력하지 않으며, 실패하면 이전 데이터로 대체하지 않고 즉시 실패한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent.parent / ".env")

from app.services.naver_api_hub import NaverApiHubClient
from app.v5.data.visual_data_pack import build_visual_data_pack


DEFAULT_FACTS = ROOT / "out/v5_pilot/kospi_july_2026/verified_facts.json"
DEFAULT_OUTPUT = ROOT / "out/v5_pilot/kospi_july_2026/visual_data_pack"
KEYWORD_GROUPS = [
    {"groupName": "코스피", "keywords": ["코스피", "KOSPI"]},
    {"groupName": "삼성전자", "keywords": ["삼성전자"]},
    {"groupName": "SK하이닉스", "keywords": ["SK하이닉스", "하이닉스"]},
    {"groupName": "엔비디아", "keywords": ["엔비디아", "NVIDIA"]},
]


def main() -> int:
    parser = argparse.ArgumentParser(description="V5 장면 내 지표ㆍ그래프 데이터 팩 수집")
    parser.add_argument("--facts", default=str(DEFAULT_FACTS), help="검증된 뉴스 사실 JSON 경로")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="출력 디렉터리")
    parser.add_argument("--topic", default="코스피 7월 전망", help="데이터 팩 주제")
    parser.add_argument("--days", type=int, default=28, help="검색어 트렌드 조회 기간(1~365일)")
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        raise ValueError("--days는 1~365 범위여야 합니다.")
    facts_payload = json.loads(Path(args.facts).read_text(encoding="utf-8"))
    facts = facts_payload.get("facts")
    if not isinstance(facts, list):
        raise ValueError("facts JSON에 facts 배열이 필요합니다.")
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days - 1)
    trend_payload = NaverApiHubClient().search_trend(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        time_unit="week",
        keyword_groups=KEYWORD_GROUPS,
    )
    pack = build_visual_data_pack(
        topic=args.topic,
        verified_facts=facts,
        search_trend_payload=trend_payload,
    )
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "naver_search_trend_raw.json").write_text(json.dumps(trend_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "visual_data_pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "visual_data_pack_collected",
        "output_dir": str(output),
        "metric_count": len(pack["metrics"]),
        "trend_series_count": len(pack["trend_series"]),
        "trend_ratio_note": pack["data_contract"]["trend_policy"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

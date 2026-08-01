"""검증 사실과 NAVER 검색어 트렌드를 이미지용 데이터 팩으로 고정한다.

이 모듈은 숫자를 계산ㆍ추정ㆍ보정하지 않는다. 뉴스 본문에서 이미 검증된 값과
NAVER API가 반환한 상대 검색 비율만 보존하며, 이후 Pillow/SVG 렌더러가
장면 내부의 그래프ㆍ경보판ㆍ지도 라벨에 그대로 사용한다.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


class VisualDataPackError(ValueError):
    """검증되지 않은 값을 이미지 데이터 팩에 넣으려 할 때 발생한다."""


_DIGIT = re.compile(r"\d")


def _compact(value: str) -> str:
    """본문의 천 단위 쉼표와 공백 차이만 허용해 원문 존재 여부를 검사한다."""
    return re.sub(r"[\s,]", "", value or "").casefold()


def _validate_news_fact(item: dict[str, Any], index: int) -> dict[str, Any]:
    figure = str(item.get("figure") or "").strip()
    fact = str(item.get("fact") or "").strip()
    source_url = str(item.get("source_url") or "").strip()
    label = str(item.get("overlay_label") or "검증 지표").strip()
    if not figure or not _DIGIT.search(figure):
        raise VisualDataPackError(f"facts[{index}]에 숫자를 포함한 figure가 필요합니다.")
    if not fact or _compact(figure) not in _compact(fact):
        raise VisualDataPackError(f"facts[{index}]의 figure가 검증 사실 원문에 없습니다.")
    if not source_url.startswith(("https://", "http://")):
        raise VisualDataPackError(f"facts[{index}]에 공개 출처 URL이 필요합니다.")
    return {
        "id": f"news_fact_{index + 1:02d}",
        "label": label,
        "value": figure,
        "fact": fact,
        "source": {
            "type": "news_article_verified_fact",
            "url": source_url,
            "title": str(item.get("source_title") or ""),
            "published_at": str(item.get("published_at") or ""),
            "source_field": str(item.get("source_field") or ""),
        },
    }


def _surface_family(value: str, position: int) -> str:
    """표현 위치만 고른다. 수치의 의미나 방향을 새로 판단하지 않는다."""
    if "%" in value and value.lstrip().startswith("-"):
        return "warning_gauge"
    if "%" in value:
        return "risk_plaque"
    if position == 0:
        return "checkout_total"
    return "engraved_metric"


def _normalise_trends(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("results")
    if not isinstance(rows, list) or not rows:
        raise VisualDataPackError("NAVER 검색어 트렌드 응답에 results가 없습니다.")
    series: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise VisualDataPackError("NAVER 검색어 트렌드 결과 형식이 올바르지 않습니다.")
        title = str(row.get("title") or "").strip()
        data = row.get("data")
        if not title or not isinstance(data, list) or not data:
            raise VisualDataPackError(f"NAVER 검색어 트렌드 results[{index}]가 비어 있습니다.")
        points: list[dict[str, Any]] = []
        for point in data:
            if not isinstance(point, dict) or "period" not in point or "ratio" not in point:
                raise VisualDataPackError(f"NAVER 검색어 트렌드 {title}의 시계열 형식이 올바르지 않습니다.")
            ratio = point["ratio"]
            if not isinstance(ratio, (int, float)):
                raise VisualDataPackError(f"NAVER 검색어 트렌드 {title}의 ratio는 숫자여야 합니다.")
            points.append({"period": str(point["period"]), "ratio": ratio})
        series.append({
            "id": f"search_trend_{index + 1:02d}",
            "title": title,
            "points": points,
            "source": "naver_search_trend",
            "ratio_note": "ratio는 절대 검색량이나 주가 변동률이 아닌 요청 결과 내 상대 검색 관심도입니다.",
        })
    return series


def build_visual_data_pack(
    *,
    topic: str,
    verified_facts: list[dict[str, Any]],
    search_trend_payload: dict[str, Any],
    collected_at: datetime | None = None,
) -> dict[str, Any]:
    """이미지 생성 전 사용할 수치ㆍ그래프ㆍ다이어그램 후보를 확정한다."""
    if not topic.strip():
        raise VisualDataPackError("데이터 팩 주제가 비어 있습니다.")
    if not isinstance(verified_facts, list) or not verified_facts:
        raise VisualDataPackError("검증된 뉴스 사실이 하나 이상 필요합니다.")
    facts = [_validate_news_fact(item, index) for index, item in enumerate(verified_facts)]
    trend_series = _normalise_trends(search_trend_payload)
    collected = (collected_at or datetime.now(timezone.utc)).isoformat()
    return {
        "schema_version": "v5.visual-data-pack.v1",
        "topic": topic,
        "collected_at": collected,
        "data_contract": {
            "numeric_policy": "뉴스 수치는 검증 사실 원문에 존재하는 값만 사용",
            "trend_policy": "NAVER ratio는 상대 검색 관심도이며 주가 변동률로 해석 금지",
            "render_policy": "값과 그래프는 Pillow/SVG가 그림 속 지정 소품 내부에 결정론적으로 합성",
        },
        "metric_surfaces": [
            {
                "surface_id": f"metric_surface_{index + 1:02d}",
                "surface_family": _surface_family(fact["value"], index),
                "metric_ref": fact["id"],
                "display": {"label": fact["label"], "value": fact["value"]},
                "source": fact["source"],
            }
            for index, fact in enumerate(facts)
        ],
        "metrics": facts,
        "trend_charts": [
            {
                "chart_id": "search_interest_comparison",
                "chart_family": "diegetic_line_chart",
                "series_refs": [series["id"] for series in trend_series],
                "source": "naver_search_trend",
                "ratio_note": "상대 검색 관심도 차트이며 투자 성과 또는 주가 차트가 아닙니다.",
            }
        ],
        "trend_series": trend_series,
        "diagram_candidates": [
            {
                "diagram_id": "news_fact_to_market_context",
                "diagram_family": "diegetic_flow_map",
                "node_refs": [fact["id"] for fact in facts],
                "rule": "노드 문구는 각 검증 사실의 label과 value만 사용하며, 인과관계 화살표는 대본 검토자가 별도 승인할 때만 표시",
            }
        ],
    }

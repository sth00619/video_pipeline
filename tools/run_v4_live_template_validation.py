"""v4 템플릿의 실제 이미지 생성·워프 검증용 5개 독립 잡 러너."""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.workers.images_worker import ImagesWorker


def chart(label: str) -> dict:
    return {
        "verified": True, "source": "v4_live_validation.fixture", "source_ref": "v4_live_validation.fixture",
        "source_date": "2026-07-26", "label": label, "latest": 100, "change_pct": 2.5,
        "points": [{"date": "2026-07-24", "close": 96}, {"date": "2026-07-25", "close": 98}, {"date": "2026-07-26", "close": 100}],
    }


CASES = [
    (94101, "stages", {"title": "퇴직연금 3단계 조건", "content": "퇴직연금의 안전장치를 세 단계로 확인합니다.", "section": "data", "market_chart": chart("퇴직연금 조건"), "stage_items": [{"label": "가입", "state": "done", "source_refs": ["v4_live_validation.fixture"]}, {"label": "보존", "state": "locked", "source_refs": ["v4_live_validation.fixture"]}, {"label": "수령", "state": "locked", "emphasis": True, "source_refs": ["v4_live_validation.fixture"]}]}),
    (94102, "structure", {"title": "자산배분 구성", "content": "자산배분은 기둥을 나눠 설계해야 합니다.", "section": "data", "market_chart": {**chart("자산배분 설계"), "market_cap_pie": [{"label": "주식", "value": 50}, {"label": "채권", "value": 30}]}, "structure_items": [{"label": "성장", "source_refs": ["v4_live_validation.fixture"]}, {"label": "방어", "source_refs": ["v4_live_validation.fixture"]}, {"label": "현금", "source_refs": ["v4_live_validation.fixture"]}]}),
    (94103, "external_rate", {"title": "관세 외부요율", "content": "관세 충격이 지역별 비용을 다르게 흔듭니다.", "section": "data", "market_chart": {**chart("관세 영향"), "external_rates": [{"label": "한국", "value": "10%", "emphasis": True, "source_refs": ["v4_live_validation.fixture"]}, {"label": "미국", "value": "5%", "source_refs": ["v4_live_validation.fixture"]}]}}),
    (94104, "causal_chain", {"title": "금리 인과 논리", "content": "금리 변화가 소비와 기업 이익으로 이어지는 경로입니다.", "section": "data", "market_chart": chart("금리 경로"), "causal_nodes": [{"label": "금리", "source_refs": ["v4_live_validation.fixture"]}, {"label": "소비", "source_refs": ["v4_live_validation.fixture"]}, {"label": "이익", "source_refs": ["v4_live_validation.fixture"]}], "verdict_stamp": "점검"}),
    (94105, "alert", {"title": "시장 경보", "content": "지금은 위험 신호를 먼저 확인해야 합니다.", "section": "intro"}),
]


def main() -> None:
    output = Path("/app/data/jobs/v4_live_validation_manifest.json")
    worker = ImagesWorker()
    reports = []
    requested = {int(value) for value in os.getenv("V4_CASE_IDS", "").split(",") if value.strip()}
    job_offset = int(os.getenv("V4_JOB_OFFSET", "0"))
    for job_id, expected, scene in CASES:
        if requested and job_id not in requested:
            continue
        actual_job_id = job_id + job_offset
        result = worker.generate(scenes_meta=[scene], job_id=actual_job_id)
        generated = result["scenes"][0]
        reports.append({"job_id": actual_job_id, "expected_template": expected, "scene": generated, "cost_ledger_path": f"/app/data/jobs/{actual_job_id}/cost_ledger.json"})
    output.write_text(json.dumps(reports, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

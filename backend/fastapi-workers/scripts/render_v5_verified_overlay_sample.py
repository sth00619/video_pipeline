#!/usr/bin/env python3
"""V5 Gemini 배경에 원장 근거의 한글·수치 오버레이를 결정론적으로 합성한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.korean_overlay import InfoPanelSpec, VerifiedMetric, apply_info_panel


RUN_DIR = ROOT / "out" / "benchmark" / "gemini_pro_textless_v3_no_layout"
SOURCE = RUN_DIR / "bench_08_datalab.png"
LEDGER = RUN_DIR / "_request_ledger.json"
TARGET = RUN_DIR / "bench_08_datalab_verified_overlay_sample.png"
MANIFEST = RUN_DIR / "bench_08_datalab_verified_overlay_sample.json"


def _verified_metrics(ledger_path: Path) -> tuple[tuple[VerifiedMetric, ...], dict]:
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        items = payload["items"]
        item = next(candidate for candidate in items if candidate["scene_key"] == "bench_08_datalab")
    except (OSError, ValueError, KeyError, StopIteration, TypeError) as exc:
        raise RuntimeError("data_lab 요청 원장을 읽을 수 없습니다.") from exc
    if item.get("status") != "http_200":
        raise RuntimeError("HTTP 200으로 확인된 요청만 정보 패널 샘플의 근거가 될 수 있습니다.")
    amount_krw = int(item["amount_krw"])
    estimated_usd = float(item["estimated_usd"])
    model = str(item["model"])
    source = "V5 요청 원장: bench_08_datalab"
    return (
        (
            VerifiedMetric("생성 모델", model, source),
            VerifiedMetric("요청 상태", "HTTP 200", source),
            VerifiedMetric("승인 추정 단가", f"${estimated_usd:.3f}", source),
            VerifiedMetric("원화 예약액", f"₩{amount_krw:,}", source),
        ),
        {
            "source_ledger": str(ledger_path),
            "scene_id": item["scene_key"],
            "request_status": item["status"],
            "estimated_usd": estimated_usd,
            "reserved_krw": amount_krw,
            "cost_status": item["cost_status"],
        },
    )


def main() -> int:
    if not SOURCE.exists():
        print(f"ERROR 생성 배경이 없습니다: {SOURCE}")
        return 2
    metrics, provenance = _verified_metrics(LEDGER)
    panel = InfoPanelSpec(
        title="V5 생성 검증 기록",
        timestamp="수치·문자는 결정론 후처리",
        metrics=metrics,
        chart_value=provenance["estimated_usd"],
        chart_max=0.20,
        source_note="근거: 요청 원장 · AI 생성 문자/숫자를 사용하지 않음",
    )
    TARGET.write_bytes(apply_info_panel(SOURCE.read_bytes(), panel))
    MANIFEST.write_text(
        json.dumps({"output": str(TARGET), "provenance": provenance}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"PASS 결정론 오버레이 샘플: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""이미 생성된 V5 8씬을 규칙 기반 QualityGate로 채점한다.

새 API 호출이나 비용을 만들지 않는다. 결과는 사람이 확인해야 하는 시각 항목과
자동 차단 가능한 빈 화면·소품 밀도 실패를 분리해서 JSON으로 남긴다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.scene.prompt_builder import BENCHMARK_SCENES
from app.v5.scene.quality_gate import QualityGate


RUNS = {
    "bench_01_port": "gemini_pro_diegetic_v5_bench_01_port",
    "bench_02_retail": "gemini_pro_diegetic_v5_retail_solo_v2",
    "bench_03_classroom": "gemini_pro_diegetic_v5_bench_03_classroom",
    "bench_04_classroom2": "gemini_pro_diegetic_v5_bench_04_classroom2",
    "bench_05_weather": "gemini_pro_diegetic_v5_bench_05_weather",
    "bench_06_split": "gemini_pro_diegetic_v5_bench_06_split",
    "bench_07_trade": "gemini_pro_diegetic_v5_bench_07_trade",
    "bench_08_datalab": "gemini_pro_diegetic_v5_bench_08_datalab_v2",
}


def main() -> int:
    benchmark_root = ROOT / "out" / "benchmark"
    cards = []
    for spec in BENCHMARK_SCENES:
        image_path = benchmark_root / RUNS[spec.scene_id] / f"{spec.scene_id}.png"
        if not image_path.is_file():
            print(f"ERROR 벤치마크 이미지가 없습니다: {image_path}")
            return 2
        card = QualityGate.score(image_path.read_bytes(), spec)
        cards.append({
            "scene_id": card.scene_id,
            "image_path": str(image_path),
            "passed": card.passed,
            "score": card.score,
            "edge_density": card.edge_density,
            "blank_tile_ratio": card.blank_tile_ratio,
            "prop_detail_regions": card.prop_detail_regions,
            "gold_signal_ratio": card.gold_signal_ratio,
            "safe_zone_noise_ratio": card.safe_zone_noise_ratio,
            "failures": list(card.failures),
            "human_review": list(card.human_review),
        })
    report = {
        "quality_gate": "rule_based_v1",
        "text_leak_detection": "not_available: local OCR engine is not installed; do not interpret automatic pass as text-clean pass",
        "automatic_passed": sum(card["passed"] for card in cards),
        "scene_count": len(cards),
        "cards": cards,
        "note": "마스코트의 실제 얼굴·손 위치와 AI 장식 텍스트의 적합성은 사람 검토 항목입니다.",
    }
    output = benchmark_root / "v5_quality_gate_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS QualityGate: {report['automatic_passed']}/{report['scene_count']} 자동 통과")
    print(output)
    return 0 if report["automatic_passed"] == report["scene_count"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

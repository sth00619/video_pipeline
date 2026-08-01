#!/usr/bin/env python3
"""V5 최종 후보 8씬(보정본 포함)을 구조 QualityGate로 평가한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.scene.prompt_builder import BENCHMARK_SCENES
from app.v5.scene.quality_gate import QualityGate


BENCHMARK = ROOT / "out" / "benchmark"
BASE_RUN = BENCHMARK / "gemini_pro_strict_textless_v5_composition_8_scene_v3"
REPLACEMENTS = {
    "bench_01_port": BENCHMARK / "gemini_pro_strict_textless_v5_identity_continuity_01_port" / "bench_01_port.png",
    "bench_07_trade": BENCHMARK / "gemini_pro_strict_textless_v5_identity_continuity_07_trade" / "bench_07_trade.png",
}


def source_for(scene_id: str) -> Path:
    return REPLACEMENTS.get(scene_id, BASE_RUN / f"{scene_id}.png")


def main() -> int:
    cards = []
    for spec in BENCHMARK_SCENES:
        source = source_for(spec.scene_id)
        if not source.is_file():
            raise FileNotFoundError(f"최종 후보 이미지가 없습니다: {source}")
        card = QualityGate.score(source.read_bytes(), spec)
        cards.append({
            "scene_id": spec.scene_id,
            "source": str(source),
            "position": spec.character_position,
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
        "set": "v5_final_candidate_with_identity_continuity_replacements",
        "automatic_passed": sum(item["passed"] for item in cards),
        "scene_count": len(cards),
        "text_leak_detection": "not_available: OCR 엔진 부재. 자동 통과는 무문자 통과를 뜻하지 않음",
        "cards": cards,
    }
    target = BENCHMARK / "v5_final_candidate_quality_gate_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS QualityGate: {report['automatic_passed']}/{report['scene_count']}")
    print(target)
    return 0 if report["automatic_passed"] == report["scene_count"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""P1-c: P0.5 원장값으로 결정론적 정보 패널 합성을 검증한다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.korean_overlay import InfoPanelSpec, VerifiedMetric, apply_info_panel


def main() -> int:
    source = ROOT / "out" / "bench_01_port.png"
    target = ROOT / "out" / "bench_01_port_info_panel.png"
    if not source.exists():
        print(f"ERROR P0.5 생성 이미지가 없습니다: {source}")
        return 2
    # 값은 P0.5 [LEDGER] 성공 기록에서만 가져온 고정 검증 샘플이다.
    panel = InfoPanelSpec(
        title="P0.5 생성 검증 패널",
        timestamp="2026.07 · 실행 기록",
        metrics=(
            VerifiedMetric("모델", "FLUX KLEIN", "P0.5 실행 원장"),
            VerifiedMetric("출력 크기", "1280 × 720", "생성 파일 메타데이터"),
            VerifiedMetric("실제 비용", "$0.015", "P0.5 실행 원장"),
            VerifiedMetric("원화 기록", "₩25", "P0.5 실행 원장·보수 환율"),
        ),
        chart_value=0.015,
        chart_max=0.020,
        source_note="근거: P0.5 비용 원장 · AI 생성 숫자를 사용하지 않음",
    )
    target.write_bytes(apply_info_panel(source.read_bytes(), panel))
    print(f"PASS 결정론적 정보 패널 저장: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

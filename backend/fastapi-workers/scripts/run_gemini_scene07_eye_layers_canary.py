#!/usr/bin/env python3
"""WO-IMG-01-H 눈 구조 계약을 scene07 한 장으로만 실증한다."""
from __future__ import annotations

from contextlib import contextmanager

from scripts import run_gemini_scene07_surfacefix_canary as runner


@contextmanager
def _eye_layers_contract():
    """기존 canary 모듈의 역사적 상수를 오염시키지 않고 이번 범위만 적용한다."""
    previous = (
        runner.SCENE_KEY,
        runner.PRIOR_LEDGER_EXPOSURE_KRW,
        runner.CUMULATIVE_EXPOSURE_CAP_KRW,
    )
    runner.SCENE_KEY = "wo-img01-h-eye-layers:7"
    runner.PRIOR_LEDGER_EXPOSURE_KRW = 28_800
    runner.CUMULATIVE_EXPOSURE_CAP_KRW = 30_400
    try:
        yield
    finally:
        (
            runner.SCENE_KEY,
            runner.PRIOR_LEDGER_EXPOSURE_KRW,
            runner.CUMULATIVE_EXPOSURE_CAP_KRW,
        ) = previous


def validate_spec(spec: dict) -> None:
    with _eye_layers_contract():
        runner.validate_spec(spec)


def prepare_row(spec: dict, *, verify_expected_hash: bool = True) -> dict:
    with _eye_layers_contract():
        return runner.prepare_row(spec, verify_expected_hash=verify_expected_hash)


def main() -> int:
    # main 전체에서 상수가 유지되어야 원장 생성과 사후 검증도 같은 계보를 쓴다.
    with _eye_layers_contract():
        return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())

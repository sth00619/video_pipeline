"""Three Goals 4장면 이미지 파일럿의 비용 없는 사전 점검.

이 스크립트는 외부 API를 호출하거나 키 값을 출력하지 않는다. 실제 실행은
별도 승인 뒤 전용 E2E runner에서만 허용한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Docker Compose 밖에서 실행할 때도 프로젝트 루트의 비밀 설정을 읽는다.
# 이미 설정된 프로세스 환경 변수는 덮어쓰지 않는다.
load_dotenv(ROOT.parent.parent / ".env", override=False)

from app import runtime_config
from app.utils.budget import plan_preflight
from app.v5.overlay.korean_overlay import _load_font


def run() -> dict:
    cfg = runtime_config.get()
    plan = plan_preflight(4, "pro", 4, 0)
    gemini_key_configured = bool(
        os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    )
    font_loaded = False
    try:
        _load_font(24)
        font_loaded = True
    except Exception:
        font_loaded = False
    checks = {
        "gemini_key_configured": gemini_key_configured,
        "provider_is_gemini": cfg["image_provider"] == "gemini",
        "quality_tier_is_pro": cfg["image_quality_tier"] == "pro",
        "budget_preflight_allowed": bool(plan["allowed"]),
        "korean_font_available": font_loaded,
    }
    return {
        "mode": "preflight_only",
        "scene_types": ["standard", "chart", "diagram", "article"],
        "checks": checks,
        "budget_preflight": plan,
        "ready_for_external_e2e": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="실제 E2E는 이 스크립트에서 허용하지 않습니다.")
    args = parser.parse_args()
    if args.execute:
        print("실제 E2E는 API 비용 승인 후 전용 runner에서만 실행할 수 있습니다.", file=sys.stderr)
        return 2
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ready_for_external_e2e"]:
        print("외부 E2E 사전 점검에 실패했습니다. 필수 환경 변수와 정책을 확인하세요.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

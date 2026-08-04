"""Three Goals Kling 4장면 파일럿의 비용 없는 사전검증기.

이 스크립트는 외부 API에 요청하지 않는다. 실제 Kling/Fal 모델 식별자와
계정별 파라미터는 공식 콘솔에서 재검증된 뒤 별도 실행기로 연결해야 한다.
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
load_dotenv(ROOT.parent.parent / ".env", override=False)

from app.services.kling_prompt_builder import build_kling_motion_prompt
from app.utils.budget import plan_preflight


PILOT_SCENES = (
    {"scene_id": "graph", "motion_type": "chart_shock", "action": "takes one short backward step", "emotion": "surprised", "edit": "alert light beat"},
    {"scene_id": "diagram", "motion_type": "pointing_explain", "action": "presents the existing surface", "emotion": "confident", "edit": "single tap"},
    {"scene_id": "metric", "motion_type": "thinking_desk", "action": "rests chin and glances once", "emotion": "thoughtful", "edit": "lamp pulse"},
    {"scene_id": "general", "motion_type": "walking_intro", "action": "walks in place", "emotion": "friendly", "edit": "short wave"},
)


def run() -> dict:
    """키 존재, 4장면 예산, prompt/negative prompt 전달 계약만 검증한다."""
    motion_contracts = []
    for scene in PILOT_SCENES:
        contract = build_kling_motion_prompt(scene)
        if not contract.get("prompt") or not contract.get("negative_prompt"):
            raise ValueError(f"Kling 모션 프롬프트 계약이 비어 있습니다: {scene['scene_id']}")
        motion_contracts.append({
            "scene_id": scene["scene_id"],
            "motion_type": scene["motion_type"],
            "action_in_prompt": scene["action"] in contract["prompt"],
            "emotion_in_prompt": scene["emotion"] in contract["prompt"],
            "edit_in_prompt": scene["edit"] in contract["prompt"],
            "negative_prompt_present": bool(contract["negative_prompt"]),
        })
    preflight = plan_preflight(4, "pro", 4, 4)
    checks = {
        "kling_or_fal_key_configured": bool(
            os.getenv("KLING_API_KEY", "").strip()
            or os.getenv("KLING_ACCESS_KEY", "").strip()
            or os.getenv("FAL_KEY", "").strip()
            or os.getenv("FAL_API_KEY", "").strip()
        ),
        "budget_preflight_allowed": bool(preflight["allowed"]),
        "all_scene_metadata_reflected": all(
            item["action_in_prompt"] and item["emotion_in_prompt"] and item["edit_in_prompt"]
            and item["negative_prompt_present"]
            for item in motion_contracts
        ),
        "external_api_called": False,
    }
    ready_for_external_e2e = all(
        checks[name]
        for name in ("kling_or_fal_key_configured", "budget_preflight_allowed", "all_scene_metadata_reflected")
    )
    return {
        "mode": "preflight_only",
        "checks": checks,
        "motion_contracts": motion_contracts,
        "budget_preflight": preflight,
        "requires_official_provider_contract_revalidation": True,
        "ready_for_external_e2e": ready_for_external_e2e,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="이 사전검증기에서는 사용할 수 없습니다.")
    args = parser.parse_args()
    if args.execute:
        print("실제 Kling 호출은 공식 모델/파라미터 재검증 후 별도 실행기에서만 허용됩니다.", file=sys.stderr)
        return 2
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_external_e2e"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V5 유료 파일럿 전에 검증 대본·출처·오버레이 계약을 차단형으로 검사한다."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# 독립 실행 시에도 저장소 루트의 승인 단가 설정을 읽어, 사전검증과 실제
# 렌더러가 다른 환경을 보는 일을 막는다. 키 값 자체는 출력하지 않는다.
load_dotenv(ROOT.parent.parent / ".env")

from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts, facts_from_verified_scene
from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider, GeminiProviderError


def validate_payload(payload: dict[str, Any], *, root: Path = ROOT) -> list[dict[str, Any]]:
    scenes = payload.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 3:
        raise ValueError("V5 파일럿은 scenes 배열에 1~3개 장면만 허용합니다.")
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError("각 파일럿 장면은 객체여야 합니다.")
        scene_id = str(scene.get("scene_id") or "").strip()
        if not scene_id or scene_id in seen_ids:
            raise ValueError("scene_id는 비어 있지 않고 서로 달라야 합니다.")
        seen_ids.add(scene_id)
        background = Path(str(scene.get("background_path") or ""))
        if not background.is_absolute():
            background = root / background
        if not background.is_file():
            raise ValueError(f"{scene_id}: 배경 이미지가 없습니다.")
        facts = scene.get("verified_facts")
        if not isinstance(facts, list) or not facts:
            raise ValueError(f"{scene_id}: verified_facts가 필요합니다.")
        for index, fact in enumerate(facts):
            if not isinstance(fact, dict) or not str(fact.get("source_url") or "").strip():
                raise ValueError(f"{scene_id}: verified_facts[{index}]에 source_url이 필요합니다.")
        overlays = facts_from_verified_scene(scene)
        if not overlays:
            raise ValueError(f"{scene_id}: v5_verified_overlays가 하나 이상 필요합니다.")
        # 렌더링을 메모리에서 수행해 글꼴·좌표·크기 오류를 유료 호출 전에 차단한다.
        apply_verified_scene_facts(background.read_bytes(), scene)
        result.append({
            "scene_id": scene_id,
            "background_path": str(background),
            "verified_fact_count": len(facts),
            "overlay_count": len(overlays),
        })
    return result


def estimated_image_cost_usd(payload: dict[str, Any], scene_count: int) -> float:
    """신규 이미지 호출이 명시된 파일럿만 Gemini 예상 단가를 계산한다.

    기존 승인 배경에 Pillow 오버레이만 합성하는 검토는 이미지 API를 호출하지
    않으므로, 비용을 새 생성 비용처럼 표시해서는 안 된다.
    """
    if not bool(payload.get("requires_image_generation", True)):
        return 0.0
    return GeminiProvider().estimate_cost_usd(GeminiModel.PRO, 2048, 1152) * scene_count


def main() -> int:
    parser = argparse.ArgumentParser(description="V5 파일럿 입력 사전검증")
    parser.add_argument("--input", required=True, help="검증 대본과 오버레이가 담긴 JSON 파일")
    args = parser.parse_args()
    input_path = Path(args.input)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("최상위 JSON은 객체여야 합니다.")
        scenes = validate_payload(payload)
        cost_usd = estimated_image_cost_usd(payload, len(scenes))
    except (OSError, ValueError, GeminiProviderError) as exc:
        print(f"ERROR V5 파일럿 사전검증 실패: {exc}")
        return 2
    print(json.dumps({
        "status": "preflight_passed_no_api_call",
        "scene_count": len(scenes),
        "estimated_image_cost_usd": round(cost_usd, 6),
        "requires_image_generation": bool(payload.get("requires_image_generation", True)),
        "scenes": scenes,
        "gemini_api_key_configured": bool(os.environ.get("GEMINI_API_KEY")),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

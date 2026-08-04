"""Claude 대본과 Gemini Pro 이미지 경로를 함께 검증하는 10분 파일럿 실행기.

키워드에서 실제 Claude 대본을 생성한 뒤, 대본이 분류한 graph·diagram·metric
장면을 각각 두 개씩만 골라 ImagesWorker에 전달한다. 전체 10분 대본의 모든 장면을
무심코 생성하지 않으면서도, 운영 스크립트·검증 사실·시장 스냅샷을 그대로 소비하는
실제 E2E 검증을 수행한다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


REQUIRED_SCENE_TYPES = ("graph", "diagram", "metric")
PILOT_ARCHETYPES = {
    "graph": ("weather_map", "trade_calculator"),
    "diagram": ("classroom", "data_lab"),
    "metric": ("risk_control_room", "port_emergency"),
}


def _post(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{base_url.rstrip('/')}{path}", json=payload, timeout=900)
    if response.status_code >= 400:
        detail = response.text[:2000]
        raise RuntimeError(f"{path} 호출 실패 (HTTP {response.status_code}): {detail}")
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError(f"{path} 응답이 객체가 아닙니다.")
    return result


def select_two_per_scene_type(script_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Claude가 실제로 분류한 세 장면 유형에서 검증 가능한 후보만 두 개씩 고른다."""
    raw_scenes = script_result.get("sections")
    if not isinstance(raw_scenes, list):
        raise ValueError("Claude 대본 응답에 sections 목록이 없습니다.")

    selected: list[dict[str, Any]] = []
    for scene_type in REQUIRED_SCENE_TYPES:
        candidates = [
            dict(scene)
            for scene in raw_scenes
            if isinstance(scene, dict) and str(scene.get("scene_type") or "").lower() == scene_type
        ]
        if len(candidates) < 2:
            raise ValueError(
                f"Claude 대본에 {scene_type} 장면이 {len(candidates)}개뿐입니다. "
                "이 파일럿은 세 유형을 각각 두 개씩 실제 생성해야 하므로 대본 장면 계획을 먼저 보완해야 합니다."
            )
        # 같은 장 제목의 문장을 연달아 뽑으면 그림도 같은 구도로 반복된다.
        # 실제 대본 순서는 보존하되, 서로 다른 장의 문장을 우선 선택한다.
        def chapter_key(scene: dict[str, Any]) -> str:
            title = str(scene.get("title") or "").split("·", 1)[0].strip()
            return title or str(scene.get("content") or scene.get("text") or "")[:24]

        chosen: list[dict[str, Any]] = []
        seen_chapters: set[str] = set()
        for scene in candidates:
            key = chapter_key(scene)
            if key in seen_chapters:
                continue
            chosen.append(scene)
            seen_chapters.add(key)
            if len(chosen) == 2:
                break
        if len(chosen) < 2:
            chosen.extend(scene for scene in candidates if scene not in chosen)
        for ordinal, scene in enumerate(chosen[:2], start=1):
            scene["e2e_test_scene_type"] = scene_type
            scene["e2e_test_ordinal"] = ordinal
            scene["visual_archetype"] = PILOT_ARCHETYPES[scene_type][ordinal - 1]
            selected.append(scene)
    return selected


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--keyword", default="8월 코스피 전망")
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--reuse-script-result", type=Path,
        help="이전에 실제 Claude로 생성·검증한 script_result.json을 재사용한다.",
    )
    parser.add_argument("--execute-images", action="store_true", help="Gemini Pro 이미지 6장을 실제 생성")
    args = parser.parse_args()

    if args.reuse_script_result:
        script_result = json.loads(args.reuse_script_result.read_text(encoding="utf-8"))
        if not isinstance(script_result, dict):
            raise ValueError("재사용할 script_result.json의 최상위 값은 객체여야 합니다.")
    else:
        script_result = _post(args.base_url, "/workers/script/generate", {
            "keyword": args.keyword,
            "target_minutes": 10,
            "category": "STOCK",
            "job_id": args.job_id,
            "data_visuals_enabled": True,
            "storytelling_profile": "original_finance_storyteller_v1",
        })
    _write_json(args.output_dir / "script_result.json", script_result)

    if not script_result.get("used_real_llm"):
        raise RuntimeError("Claude 실호출이 아닌 fallback 대본이 반환되어 파일럿을 중단합니다.")
    providers = script_result.get("llm_provider_log") or []
    if not any(item.get("provider") == "claude-sonnet-4-6" and not item.get("fallback") for item in providers if isinstance(item, dict)):
        raise RuntimeError("고정 Claude Sonnet 4.6 실호출 증빙이 대본 결과에 없습니다.")

    selected_scenes = select_two_per_scene_type(script_result)
    _write_json(args.output_dir / "selected_scenes.json", selected_scenes)
    selection_summary = {
        "keyword": args.keyword,
        "job_id": args.job_id,
        "target_minutes": 10,
        "selected_scene_count": len(selected_scenes),
        "selected_by_type": {
            scene_type: sum(scene["e2e_test_scene_type"] == scene_type for scene in selected_scenes)
            for scene_type in REQUIRED_SCENE_TYPES
        },
        "used_real_llm": True,
        "claude_model": "claude-sonnet-4-6",
    }
    _write_json(args.output_dir / "selection_summary.json", selection_summary)

    if not args.execute_images:
        print(json.dumps({"mode": "script_and_selection_only", **selection_summary}, ensure_ascii=False, indent=2))
        return 0

    image_script_meta = {
        **script_result,
        # 재사용 실행에서도 ScriptWorker가 새로 생성한 응답과 동일하게 각
        # 장면에 검증 사실 원문을 전달한다. 이미지 모델에는 주입하지 않고
        # 결정론적 오버레이 검증에만 사용한다.
        "sections": [
            {**scene, "verified_facts": scene.get("verified_facts") or script_result.get("verified_facts") or []}
            for scene in selected_scenes
        ],
        "scenes": [
            {**scene, "verified_facts": scene.get("verified_facts") or script_result.get("verified_facts") or []}
            for scene in selected_scenes
        ],
    }
    image_request = {
        "job_id": args.job_id,
        "tts_meta": json.dumps({"target_seconds": 600}, ensure_ascii=False),
        "script_meta": json.dumps(image_script_meta, ensure_ascii=False),
        "character_image_path": "/app/assets/character/goldie_sheet_v1.png",
        "budget_limit_krw": 40_000,
        "budget_policy_version": "under-20m-40000-2026-08-02",
    }
    try:
        images_result = _post(args.base_url, "/workers/images/generate", image_request)
    except RuntimeError as exc:
        _write_json(args.output_dir / "images_error.json", {
            "stage": "images_generate",
            "job_id": args.job_id,
            "selected_scene_count": len(selected_scenes),
            "error": str(exc),
        })
        raise
    _write_json(args.output_dir / "images_result.json", images_result)
    if int(images_result.get("scene_count") or 0) != 6:
        raise RuntimeError(f"Gemini 결과 장면 수가 6이 아닙니다: {images_result.get('scene_count')}")
    methods = {str(scene.get("generation_method") or "") for scene in images_result.get("scenes", []) if isinstance(scene, dict)}
    # 이번 파일럿은 실제 Gemini Pro 생성 경로의 검증이 목적이다. 기사 캡처나
    # 이전 작업 재개 결과는 이미지 생성 성공으로 간주하지 않는다.
    disallowed = methods - {"pro_gemini", "composite"}
    if disallowed:
        raise RuntimeError(f"실제 Gemini 파일럿에 허용되지 않은 생성 방식이 포함됐습니다: {sorted(disallowed)}")

    print(json.dumps({"mode": "completed", **selection_summary, "image_methods": sorted(methods)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

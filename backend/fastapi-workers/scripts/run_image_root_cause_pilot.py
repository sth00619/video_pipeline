#!/usr/bin/env python3
"""Job52 공통 원인 수정의 대표 장면 1장을 실제 Gemini 경로로 검증한다.

기본 실행은 프롬프트·비용·참조 계보만 저장한다. ``--execute``일 때만 이미지
API를 한 번 호출하고, 같은 최종 PNG에 OCR 1차 검사와 멀티모달 시각 QA를 한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(REPO_ROOT / ".env")

from app.utils.budget import ProviderRequestAudit
from app.utils.visual_qa import assess_visual_alignment
from app.v5.cost_ledger import BudgetExceeded, Bucket, CostLedger, FxProvider
from app.v5.providers.gemini_provider import (
    GeminiModel,
    GeminiProvider,
    GeminiProviderError,
    _load_default_references,
    select_contextual_reference_paths,
)
from app.v5.scene.runtime_contract import attach_v5_scene_contracts
from app.workers.images_worker import (
    NonRetryableImageGenerationError,
    _bounded_text_generation_prompt,
    _inspect_generated_textless_image,
)


LAB_SCENE = {
    "scene_id": "job52_root_cause_korean_text_character",
    "index": 0,
    "scene_type": "diagram",
    "title": "실적의 구조를 확인하는 장면",
    "content": "코스피 영업이익이 늘어도 두 반도체 기업을 제외한 전체 흐름이 함께 좋아졌는지 확인해야 합니다.",
    "text": "코스피 영업이익이 늘어도 두 반도체 기업을 제외한 전체 흐름이 함께 좋아졌는지 확인해야 합니다.",
    "screen_texts": ["영업이익"],
    "screen_text_plan": [{
        "text": "영업이익",
        "surface": "existing solid machine-mounted production monitor",
        "surface_style": "opaque_equipment_display",
        "role": "supporting_metric_label",
        "prominence": "secondary",
        "max_occurrences": 1,
    }],
    "screen_text_validation": {"passed": True, "reasons": []},
    "visual_intent": (
        "A lively, saturated semiconductor analysis scene in the visual range of the supplied approved channel scenes. "
        "Two visually distinct microchip modules are being lifted away from a busy conveyor carrying many other chips, so the viewer can read "
        "the difference between two dominant firms and the rest of the market without company names or numbers. The production mechanism, "
        "chip groups, analytical arrows, and mascot share the frame; no headline board is the focal idea. The mascot acts as a semiconductor "
        "researcher for this scene; its lab costume and expression belong only to this scene, not to every video frame."
    ),
    "art_direction": {
        "character_required": True,
        "setting": "Korean semiconductor analysis room and wafer production line",
        "props": [
            "two highlighted chip modules being separated from a larger group of chips",
            "diagonal wafer-and-chip production conveyor",
            "integrated non-numeric analytical arrows",
        ],
        "composition": "layered diagonal production-line composition; medium mascot at lower left, machinery and chip groups carry most of the visual weight",
        "character_position": "left",
        "character_occupancy": 0.28,
    },
    "scene_spec": {
        "character_costume": "white semiconductor laboratory coat with optional goggles suited to this scene",
        "character_action": "using one inspection tool to separate two highlighted chips from a larger moving group in one coherent action",
        "camera": "dynamic wide three-quarter laboratory view looking along the diagonal production conveyor",
    },
    "verified_facts": [],
}

SPLIT_FORECAST_SCENE = {
    "scene_id": "contextual_split_forecast",
    "index": 0,
    "scene_type": "graph",
    "title": "현재 전망과 하향 전망 비교",
    "content": "현재 전망과 전망 하향 가능성을 서로 다른 두 분위기로 비교합니다.",
    "text": "현재 전망과 전망 하향 가능성을 서로 다른 두 분위기로 비교합니다.",
    "screen_texts": ["현재 전망", "전망 하향"],
    "screen_text_plan": [
        {"text": "현재 전망", "surface": "bright current-outlook zone", "role": "comparison_left"},
        {"text": "전망 하향", "surface": "stormy downgrade zone", "role": "comparison_right"},
    ],
    "screen_text_validation": {"passed": True, "reasons": []},
    "bubble_policy": "forbidden",
    "visual_archetype": "weather_map",
    "visual_intent": (
        "A wide editorial comparison in the supplied approved weather-map and risk-scene range. The left outlook feels clear and constructive; "
        "the right outlook turns stormy and uncertain. The two zones belong to one deliberate comparison composition rather than a generic studio wall."
    ),
    "art_direction": {
        "character_required": True,
        "setting": "economic forecast comparison stage",
        "props": ["sunlit rising outlook shapes", "storm cloud and descending outlook shapes"],
        "composition": "balanced two-zone comparison with the mascot mediating between them",
    },
    "scene_spec": {
        "character_costume": "scene-appropriate economic weather presenter outfit, not a mandatory navy suit or fedora",
        "character_action": "comparing the two forecast zones with one coherent open-hand gesture",
        "camera": "wide straight-on comparison view",
    },
    "verified_facts": [],
}

MARKET_FLOW_SCENE = {
    "scene_id": "contextual_market_flow",
    "index": 0,
    "scene_type": "metric",
    "title": "외국인과 개인 수급 흐름",
    "content": "외국인 매수와 개인 매도가 반대 방향으로 움직이는 수급 흐름을 보여 줍니다.",
    "text": "외국인 매수와 개인 매도가 반대 방향으로 움직이는 수급 흐름을 보여 줍니다.",
    "screen_texts": ["외국인 매수", "개인 매도"],
    "screen_text_plan": [
        {"text": "외국인 매수", "surface": "green inflow route", "role": "flow_in"},
        {"text": "개인 매도", "surface": "red outflow route", "role": "flow_out"},
    ],
    "screen_text_validation": {"passed": True, "reasons": []},
    "visual_archetype": "risk_control_room",
    "visual_intent": (
        "A dynamic market-flow control room in the supplied approved channel scene range, with green and red directional streams crossing through physical market gates. "
        "The mascot participates in the flow mechanism while small human trader silhouettes may appear in the background."
    ),
    "art_direction": {
        "character_required": True,
        "setting": "busy Korean brokerage market-flow room",
        "props": ["green inflow path", "red outflow path", "market gates", "background trader silhouettes"],
        "composition": "dynamic diagonal flow composition with multiple integrated information surfaces",
    },
    "scene_spec": {
        "character_costume": "active market-floor operator outfit chosen for this scene",
        "character_action": "redirecting two opposing market flows with one coherent action",
        "camera": "dynamic three-quarter market-room view",
    },
    "verified_facts": [],
}

SCENES = {
    "lab": LAB_SCENE,
    "split_forecast": SPLIT_FORECAST_SCENE,
    "market_flow": MARKET_FLOW_SCENE,
}


def _references(prompt: str) -> tuple[list[str], list[dict[str, str]]]:
    paths = [Path(value) for value in select_contextual_reference_paths(prompt, _load_default_references())]
    rows = []
    for path in paths:
        rows.append({"role": "channel_style_range", "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return [str(path) for path in paths], rows


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--variant", choices=tuple(SCENES), default="lab")
    parser.add_argument(
        "--output-dir", type=Path,
        default=REPO_ROOT / "artifacts" / "job52_full_audit_20260824" / "real_api_pilot",
    )
    args = parser.parse_args()

    scene = attach_v5_scene_contracts([dict(SCENES[args.variant])])[0]
    contract = scene["v5_render_contract"]
    prompt = _bounded_text_generation_prompt(contract["prompt_en"], audit_target=scene)
    references, reference_rows = _references(prompt)
    provider = GeminiProvider(use_batch=False)
    unit_usd = provider.estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
    rate = FxProvider().usd_to_krw()
    estimate_krw = round(unit_usd * rate)
    if estimate_krw > 4_000:
        raise BudgetExceeded("대표 이미지 1장 예상 비용이 4,000원을 초과합니다.")

    manifest = {
        "status": "preflight_passed_no_api_call" if not args.execute else "running",
        "scene": scene,
        "model": GeminiModel.PRO.value,
        "estimated_usd": unit_usd,
        "estimated_krw": estimate_krw,
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "references": reference_rows,
    }
    manifest_path = args.output_dir / "manifest.json"
    _write(manifest_path, manifest)
    if not args.execute:
        print(json.dumps({"status": manifest["status"], "manifest": str(manifest_path), "estimated_krw": estimate_krw}, ensure_ascii=False))
        return 0

    output_path = args.output_dir / f"{scene['scene_id']}.png"
    request_ledger = args.output_dir / "request_ledger.json"
    audit = ProviderRequestAudit.for_path(
        path=request_ledger,
        scene_key=scene["scene_id"],
        model=GeminiModel.PRO.value,
        unit_usd=unit_usd,
        usd_krw=rate,
        budget_limit_krw=4_000,
        request_metadata={
            "prompt_sha256": manifest["prompt_sha256"],
            "reference_sha256": [row["sha256"] for row in reference_rows],
            "text_contract": scene.get("image_text_contract"),
        },
    )
    ledger = CostLedger(video_id=f"job52_contextual_{args.variant}_pilot", fx=FxProvider())
    ledger.guard(Bucket.IMAGE_FINAL, unit_usd)
    started = time.monotonic()
    try:
        result = provider.generate(
            prompt,
            model=GeminiModel.PRO,
            width=2048,
            height=1152,
            seed=5207,
            reference_image_paths=references,
            request_audit=audit,
        )
    except GeminiProviderError as exc:
        # 네트워크 타임아웃 뒤 manifest가 running으로 남으면 재개 시 성공
        # 산출물로 오인할 수 있다. 실패 원장과 함께 명시적으로 종료한다.
        request_summary = {}
        if request_ledger.is_file():
            request_summary = json.loads(request_ledger.read_text(encoding="utf-8"))
        manifest.update({
            "status": "provider_request_failed_no_image",
            "error": str(exc),
            "request_ledger": request_summary,
            "seconds": round(time.monotonic() - started, 1),
        })
        _write(manifest_path, manifest)
        print(json.dumps({
            "status": manifest["status"],
            "manifest": str(manifest_path),
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 5
    output_path.write_bytes(result.image_bytes)
    ledger.record(
        scene_id=scene["scene_id"], provider="gemini", model=GeminiModel.PRO.value,
        request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=unit_usd,
        actual_usd=None, rate=rate, status="ok",
        cost_status="unverified_until_console_reconciliation", metadata=result.meta,
    )

    scene["image_path"] = str(output_path)
    scene["final_image_path"] = str(output_path)
    try:
        ocr = _inspect_generated_textless_image(scene, str(output_path))
    except NonRetryableImageGenerationError as exc:
        # OCR 실행기 장애는 이미 과금·저장된 이미지를 잃거나 같은 API를 다시
        # 호출할 이유가 아니다. 자동 승인은 막되 원본과 나머지 QA를 보존한다.
        ocr = {
            **(scene.get("image_text_contract") or {}),
            "passed": False,
            "status": "unavailable",
            "error": str(exc),
            "visible_tokens": [],
        }
    visual = assess_visual_alignment([scene], enabled=True, max_scenes=1)
    review = (visual.get("reviewed") or [{}])[0]
    passed = bool(ocr.get("passed")) and bool(review) and not review.get("retry_recommended", True)
    manifest.update({
        "status": "passed" if passed else "review_required",
        "output_path": str(output_path),
        "seconds": round(time.monotonic() - started, 1),
        "ocr": ocr,
        "visual_qa": visual,
        "ledger": ledger.summary(),
    })
    _write(manifest_path, manifest)
    print(json.dumps({
        "status": manifest["status"], "output_path": str(output_path),
        "manifest": str(manifest_path), "failure_categories": review.get("failure_categories", []),
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 4


if __name__ == "__main__":
    raise SystemExit(main())

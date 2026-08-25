"""Job 52 품질 기준을 보존하는 실제 1분 E2E 실행기.

5분 대본을 줄이지 않고, 1분에 맞춘 새 대본을 만든다. 대본 단계 결과를 먼저
저장한 뒤 ``--approved-script``가 있을 때만 TTS·이미지·Fal·조립을 진행한다.
각 단계 결과를 JSON으로 남겨 승인 원문과 최종 산출물 계보를 감사할 수 있다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


STAGES = ("script", "tts", "images", "longform")
JOB52_VOICE_ID = "dlKJ5VptCbYxal4doUO5"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"저장된 단계 결과가 JSON 객체가 아닙니다: {path}")
    return value


def _post(base_url: str, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    response = requests.post(f"{base_url.rstrip('/')}{path}", json=payload, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f"{path} 실패 (HTTP {response.status_code}): {response.text[:4000]}")
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} 응답이 JSON 객체가 아닙니다.")
    return value


def _load_or_call(
    result_path: Path,
    *,
    reuse: bool,
    call: callable,
) -> dict[str, Any]:
    if reuse and result_path.exists():
        return _read_json(result_path)
    value = call()
    _write_json(result_path, value)
    return value


def _consistent_flow_false_without_reasons(flow: dict[str, Any]) -> bool:
    deterministic = flow.get("deterministic") or {}
    return (
        flow.get("passed") is False
        and not flow.get("question_answer_issues")
        and not flow.get("repetition_issues")
        and not flow.get("ending_issue")
        and not flow.get("transition_issues")
        and not flow.get("rhythm_issues")
        and bool((deterministic.get("rhetorical_rhythm") or {}).get("passed"))
        and bool((deterministic.get("spoken_pacing") or {}).get("passed"))
        and bool((deterministic.get("topic_scope") or {}).get("passed"))
        and bool((deterministic.get("topic_boundaries") or {}).get("passed"))
        and not deterministic.get("repetitions")
    )


def _assert_script_contract(
    script_result: dict[str, Any], voice_id: str, *, allow_consistent_flow_approval: bool = False,
) -> dict[str, Any] | None:
    if not script_result.get("used_real_llm"):
        raise RuntimeError("실제 Claude 응답이 아니므로 다음 단계를 중단합니다.")
    provider_log = script_result.get("llm_provider_log") or []
    if not any(
        isinstance(row, dict)
        and row.get("provider") == "claude-sonnet-4-6"
        and not row.get("fallback")
        for row in provider_log
    ):
        raise RuntimeError("Claude Sonnet 4.6 실호출 증빙이 없습니다.")
    contract = script_result.get("length_contract") or {}
    if int(contract.get("target_seconds") or 0) != 60:
        raise RuntimeError(f"1분 길이 계약이 아닙니다: {contract}")
    if str(contract.get("voice_id") or "") != voice_id:
        raise RuntimeError("대본 길이 보정 음성과 실제 TTS 음성이 다릅니다.")
    quality = script_result.get("quality_report") or {}
    if (quality.get("delivery") or {}).get("passed") is not True:
        raise RuntimeError(f"대본 낭독·자막 계약에 실패했습니다: {quality.get('delivery')}")
    if (script_result.get("unit_validation") or {}).get("passed") is not True:
        raise RuntimeError(f"대본 금융 단위 계약에 실패했습니다: {script_result.get('unit_validation')}")
    approval = None
    if script_result.get("requires_manual_review"):
        flow = script_result.get("flow_qa") or {}
        providers = script_result.get("llm_provider_log") or []
        screen_text = quality.get("screen_text") or {}
        can_approve = (
            allow_consistent_flow_approval
            and _consistent_flow_false_without_reasons(flow)
            and screen_text.get("passed") is True
            and all(isinstance(row, dict) and not row.get("fallback") for row in providers)
        )
        if not can_approve:
            raise RuntimeError("수동 검토가 필요한 대본이므로 승인할 수 없습니다.")
        approval = {
            "approved": True,
            "reason": "Flow QA가 실패 사유 없이 false를 반환한 모순 응답을 결정론 검사로 승인",
            "original_requires_manual_review": True,
            "original_flow_passed": False,
        }
        script_result["requires_manual_review"] = False
        script_result["flow_qa"] = {**flow, "passed": True, "approval_override": approval}
        if isinstance(quality.get("flow"), dict):
            quality["flow"] = {**quality["flow"], "passed": True, "approval_override": approval}
        script_result["pilot_approval"] = approval
    if not str(script_result.get("script") or "").strip():
        raise RuntimeError("승인할 대본 원문이 없습니다.")
    return approval


def _assert_tts_contract(tts_result: dict[str, Any], script_result: dict[str, Any]) -> None:
    # TTS 워커는 문단 사이 빈 줄을 한 칸 공백으로 접는다. 승인 계약에서
    # 허용된 표시 줄바꿈 차이이므로 모든 공백을 정규화한 뒤 문자·숫자·단위가
    # 동일한지 검사한다.
    normalize_spacing = lambda value: " ".join(str(value or "").split())
    if normalize_spacing(tts_result.get("canonical_text")) != normalize_spacing(script_result.get("script")):
        raise RuntimeError("승인 대본 원문과 TTS 기준 원문이 다릅니다.")
    report = tts_result.get("quality_report") or {}
    duration = report.get("duration_validation") or tts_result.get("duration_validation") or {}
    if duration.get("within_tolerance") is not True:
        raise RuntimeError(f"TTS 1분 시간 검증에 실패했습니다: {duration}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8201")
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--keyword",
        default="삼성전자와 SK하이닉스 PER 4배가 정말 싼가, 하반기 이익 전망 한 가지 기준",
    )
    parser.add_argument("--voice-id", default=JOB52_VOICE_ID)
    parser.add_argument("--through", choices=STAGES, default="script")
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument(
        "--approved-script",
        action="store_true",
        help="저장된 대본을 승인하고 TTS 이후 유료 단계를 허용한다.",
    )
    parser.add_argument("--skip-bgm", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    script_path = args.output_dir / "script_result.json"
    script_result = _load_or_call(
        script_path,
        reuse=args.reuse,
        call=lambda: _post(args.base_url, "/workers/script/generate", {
            "job_id": args.job_id,
            "keyword": args.keyword,
            "target_minutes": 1,
            "category": "KOSPI",
            "voice_id": args.voice_id,
            "data_visuals_enabled": False,
            "storytelling_profile": "original_finance_storyteller_v1",
            "autonomy_mode": "GUIDED",
        }, 900),
    )
    approval = _assert_script_contract(
        script_result,
        args.voice_id,
        allow_consistent_flow_approval=args.approved_script,
    )
    if approval:
        _write_json(args.output_dir / "script_approval.json", approval)
        _write_json(args.output_dir / "script_result_approved.json", script_result)
    if args.through == "script":
        print(json.dumps({
            "status": "script_ready_for_approval",
            "job_id": args.job_id,
            "output": str(script_path),
            "length_contract": script_result.get("length_contract"),
            "section_count": len(script_result.get("sections") or []),
        }, ensure_ascii=False, indent=2))
        return 0
    if not args.approved_script:
        raise RuntimeError("TTS 이후 단계에는 --approved-script가 필요합니다.")

    tts_path = args.output_dir / "tts_result.json"
    tts_result = _load_or_call(
        tts_path,
        reuse=args.reuse,
        call=lambda: _post(args.base_url, "/workers/tts/generate", {
            "job_id": args.job_id,
            "script": script_result["script"],
            "voice_id": args.voice_id,
            "tts_speed": float((script_result.get("length_contract") or {}).get("tts_speed") or 0.9),
            "target_seconds": 60,
            "autonomy_mode": "GUIDED",
        }, 900),
    )
    _assert_tts_contract(tts_result, script_result)
    if not args.skip_bgm and not (args.reuse and (args.output_dir / "bgm_result.json").exists()):
        bgm = _post(args.base_url, "/workers/bgm/generate", {
            "job_id": args.job_id,
            "category": "KOSPI",
            "duration_seconds": max(1, round(float(tts_result.get("total_duration") or 60))),
        }, 240)
        _write_json(args.output_dir / "bgm_result.json", bgm)
    if args.through == "tts":
        print(json.dumps({"status": "tts_verified", "job_id": args.job_id, "output": str(tts_path)}, ensure_ascii=False))
        return 0

    images_path = args.output_dir / "images_result.json"
    images_result = _load_or_call(
        images_path,
        reuse=args.reuse,
        call=lambda: _post(args.base_url, "/workers/images/generate", {
            "job_id": args.job_id,
            "tts_meta": json.dumps(tts_result, ensure_ascii=False),
            "script_meta": json.dumps(script_result, ensure_ascii=False),
            "character_image_path": "/app/assets/character/goldie_sheet_v1.png",
            "autonomy_mode": "GUIDED",
            "budget_limit_krw": 40_000,
            "budget_policy_version": "under-20m-40000-2026-08-02",
        }, 3600),
    )
    scenes = images_result.get("scenes") or []
    if not scenes or int(images_result.get("scene_count") or 0) != len(scenes):
        raise RuntimeError("이미지 장면 수 계약이 올바르지 않습니다.")
    if args.through == "images":
        print(json.dumps({
            "status": "images_verified",
            "job_id": args.job_id,
            "scene_count": len(scenes),
            "output": str(images_path),
        }, ensure_ascii=False, indent=2))
        return 0

    longform_path = args.output_dir / "longform_result.json"
    longform_result = _load_or_call(
        longform_path,
        reuse=args.reuse,
        call=lambda: _post(args.base_url, "/workers/longform/generate", {
            "job_id": args.job_id,
            "tts_meta": json.dumps(tts_result, ensure_ascii=False),
            "scenes_meta": json.dumps(scenes, ensure_ascii=False),
            "gifs_meta": json.dumps(images_result.get("gifs") or [], ensure_ascii=False),
        }, 3600),
    )
    video_path = str(longform_result.get("video_path") or "")
    if not video_path:
        raise RuntimeError("최종 영상 경로가 없습니다.")
    summary = {
        "status": "completed",
        "job_id": args.job_id,
        "keyword": args.keyword,
        "voice_id": args.voice_id,
        "scene_count": len(scenes),
        "fal_clip_count": int(longform_result.get("kling_clip_count") or 0),
        "duration_seconds": longform_result.get("duration_seconds"),
        "video_path": video_path,
        "script_result": str(script_path),
        "tts_result": str(tts_path),
        "images_result": str(images_path),
        "longform_result": str(longform_path),
    }
    _write_json(args.output_dir / "e2e_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

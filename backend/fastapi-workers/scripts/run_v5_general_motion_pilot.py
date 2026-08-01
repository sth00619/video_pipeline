"""V5 일반 씬의 FAL/Kling 모션을 단 한 번 검증한다.

이 스크립트는 정보 오버레이가 없는 ``scene_type=general``만 허용한다.
이미지 API를 호출하지 않으며, FAL 요청은 ``fal_only=True``로 고정해
다른 Kling API 또는 자동 재시도로 넘어가지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(REPO_ROOT / ".env")

from app import runtime_config  # noqa: E402
from app.providers.real.video import KlingProvider  # noqa: E402
from app.services.kling_prompt_builder import build_kling_motion_prompt  # noqa: E402
from app.workers.longform_worker import (  # noqa: E402
    _article_capture_for_scene,
    _has_v5_verified_fact_overlay,
    _should_request_kling_for_scene,
    _upload_image_for_fal,
)


# Windows PowerShell 기본 코드페이지에서도 프롬프트 감사 JSON을 손상 없이 남긴다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_SOURCE = (
    ROOT
    / "out"
    / "benchmark"
    / "gemini_pro_strict_textless_v5_revalidation_01_port"
    / "bench_01_port.png"
)
DEFAULT_OUTPUT_DIR = ROOT / "out" / "v5_motion_pilot" / "general_port_walking_intro_20260801"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    """중단 중에도 마지막 영속 감사 상태가 남도록 원자적으로 기록한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _scene_contract() -> dict[str, Any]:
    """일반 씬 전용 계약을 명시해 정보 오버레이 경로와 분리한다."""
    return {
        "scene_id": "v5_general_port_motion_01",
        "scene_type": "general",
        "archetype": "port_emergency",
        "motion_type": "walking_intro",
        "use_kling": True,
        "v5_verified_overlays": [],
    }


def _preflight(source: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not source.is_file() or source.stat().st_size <= 1_000:
        raise RuntimeError(f"유효한 일반 씬 원본 이미지를 찾지 못했습니다: {source}")

    scene = _scene_contract()
    has_overlay = _has_v5_verified_fact_overlay(scene)
    article_capture = bool(_article_capture_for_scene(scene))
    is_candidate = _should_request_kling_for_scene(
        scene,
        selected_for_intro_motion=True,
        has_manual_kling_selection=True,
    )
    if has_overlay or article_capture or not is_candidate:
        raise RuntimeError("일반 씬 FAL 모션 안전 계약을 통과하지 못했습니다.")

    cfg = runtime_config.get()
    clip_seconds = int(cfg["intro_motion_clip_seconds"])
    if clip_seconds != 5:
        raise RuntimeError(f"이 파일럿은 5초 전용입니다. 현재 설정: {clip_seconds}초")
    cost_usd = float(cfg["kling_cost_per_clip_usd"])
    cost_krw = round(cost_usd * float(cfg["usd_krw"]))
    prompt = build_kling_motion_prompt(scene["motion_type"])

    audit = {
        "run_id": "general_port_walking_intro_20260801",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_kind": "single_general_scene_motion_pilot",
        "provider": "fal",
        "model": "fal-ai/kling-video/v2.6/pro/image-to-video",
        "automatic_retry": False,
        "fal_only": True,
        "scene": scene,
        "safety_checks": {
            "has_v5_verified_fact_overlay": has_overlay,
            "article_capture": article_capture,
            "kling_candidate": is_candidate,
        },
        "source": {"path": str(source), "sha256": _sha256(source)},
        "motion": {
            "duration_seconds": clip_seconds,
            "generate_audio": False,
            "camera": "locked",
            "motion_type": scene["motion_type"],
            "prompt": prompt["prompt"],
            "negative_prompt": prompt["negative_prompt"],
        },
        "cost": {
            "estimated_usd": cost_usd,
            "estimated_krw": cost_krw,
            "usd_krw_snapshot": float(cfg["usd_krw"]),
            "cost_status": "unverified_until_fal_console_reconciliation",
        },
    }
    return scene, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--execute", action="store_true", help="FAL에 단 한 번 실제 요청")
    args = parser.parse_args()

    _, audit = _preflight(args.source)
    audit_path = args.output_dir / "_request_audit.json"
    output_path = args.output_dir / "general_port_walking_intro.mp4"

    if not args.execute:
        print(json.dumps({"mode": "dry_run", **audit}, ensure_ascii=False, indent=2))
        return 0

    # 유료 추론 직전에 예약 상태를 먼저 남긴다. 업로드 실패도 재시도로 숨기지 않는다.
    audit["status"] = "reserved_before_fal_request"
    _write_json_atomically(audit_path, audit)
    start_image_url = _upload_image_for_fal(str(args.source))
    if not start_image_url:
        audit["status"] = "fal_upload_failed"
        _write_json_atomically(audit_path, audit)
        raise RuntimeError("FAL CDN 업로드에 실패했습니다. 추론 요청은 보내지 않았습니다.")

    try:
        asset = KlingProvider().generate(
            prompt=audit["motion"]["prompt"],
            negative_prompt=audit["motion"]["negative_prompt"],
            duration=audit["motion"]["duration_seconds"],
            image_path=str(args.source),
            image_url=start_image_url,
            output_path=str(output_path),
            fal_only=True,
        )
    except Exception as exc:
        audit["status"] = "fal_request_failed_no_retry"
        audit["failure_type"] = type(exc).__name__
        _write_json_atomically(audit_path, audit)
        raise

    if not output_path.is_file() or output_path.stat().st_size <= 1_000:
        audit["status"] = "fal_result_invalid_no_retry"
        _write_json_atomically(audit_path, audit)
        raise RuntimeError("FAL 응답 결과가 유효한 동영상 파일이 아닙니다.")

    audit["status"] = "success_unverified_until_fal_console_reconciliation"
    audit["result"] = {
        "path": str(output_path),
        "bytes": output_path.stat().st_size,
        "fal_request_id": (asset.meta or {}).get("fal_request_id"),
    }
    _write_json_atomically(audit_path, audit)
    print(json.dumps({"status": audit["status"], "audit_path": str(audit_path), "video_path": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""승인된 9장 정적 조립본의 계보와 계약을 외부 호출 없이 검증한다.

이 스크립트는 이미지·TTS·Fal·LLM API를 호출하지 않는다. 이미 조립에 사용된
파일과 결과 메타데이터만 읽어, 다음 유료 E2E 전에 기존 산출물이 보존됐는지 확인한다.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DIAGNOSTICS_ROOT = REPO_ROOT / "artifacts" / "diagnostics"
INPUT_PATH = DIAGNOSTICS_ROOT / "visual_mix_nine_scene_assembly_input_20260803.json"
RESULT_PATH = DIAGNOSTICS_ROOT / "visual_mix_nine_scene_assembly_result_20260803.json"
VIDEO_PATH = DIAGNOSTICS_ROOT / "visual_mix_nine_scene_assembly_920260805.mp4"
DOSSIER_PATH = (
    WORKER_ROOT
    / "out"
    / "v5_pilot"
    / "visual_mix_nine_scene"
    / "VISUAL_MIX_R4_REVIEW_DOSSIER_20260803.md"
)
REPORT_PATH = DIAGNOSTICS_ROOT / "visual_mix_nine_scene_lineage_preflight_20260803.json"
# 조립본은 스타일 계약 도입 전의 내부 식별자를 사용한다. 의미를 보존한 호환 매핑만
# 적용하며, 이미지 자체나 선택 순서는 변경하지 않는다.
MODE_FAMILY = {
    "article_evidence": "article_capture",
    "article_capture": "article_capture",
    "semantic_illustration": "semantic_illustration",
    "archetype_explainer": "info_archetype",
    "info_archetype": "info_archetype",
}
EXPECTED_MODES = Counter({"article_capture": 3, "semantic_illustration": 3, "info_archetype": 3})


def _host_asset_path(value: str) -> Path:
    """컨테이너 조립 입력의 /app/out 경로를 로컬 작업 경로로 되돌린다."""

    path = Path(value)
    if path.is_file():
        return path
    normalized = value.replace("\\", "/")
    marker = "/app/out/"
    if marker not in normalized:
        raise ValueError(f"지원하지 않는 이미지 경로입니다: {value}")
    return WORKER_ROOT / "out" / normalized.split(marker, 1)[1]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    assembly_input = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    assembly_result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))["result"]
    scenes = assembly_input["scenes"]
    tts = assembly_input["tts_meta"]
    failures: list[str] = []

    raw_mode_counts = Counter(scene["visual_mode"] for scene in scenes)
    mode_counts = Counter(MODE_FAMILY.get(scene["visual_mode"], scene["visual_mode"]) for scene in scenes)
    _require(len(scenes) == 9, "선정 장면 수가 9장이 아닙니다.", failures)
    _require(mode_counts == EXPECTED_MODES, "기사형·상황형·정보형이 각각 3장이 아닙니다.", failures)
    _require(not assembly_input["kling_started"], "정적 조립 입력에서 Kling이 시작됐습니다.", failures)
    _require(not assembly_input["thumbnail_started"], "정적 조립 입력에서 썸네일이 시작됐습니다.", failures)
    _require(not any(scene.get("use_kling") for scene in scenes), "검증된 9장에 Kling이 선택됐습니다.", failures)
    _require(DOSSIER_PATH.is_file(), "9장 검수 도시에 파일이 없습니다.", failures)
    _require(VIDEO_PATH.is_file() and VIDEO_PATH.stat().st_size > 0, "정적 MP4 산출물이 없습니다.", failures)

    asset_rows = []
    for scene in scenes:
        asset_path = _host_asset_path(scene["final_image_path"])
        exists = asset_path.is_file() and asset_path.stat().st_size > 0
        _require(exists, f"선정 이미지가 없습니다: {scene['scene_id']}", failures)
        asset_rows.append({
            "scene_id": scene["scene_id"],
            "visual_mode": scene["visual_mode"],
            "asset_path": str(asset_path.relative_to(REPO_ROOT)),
            "exists": exists,
            "use_kling": bool(scene.get("use_kling")),
        })

    canonical_text = tts["canonical_text"]
    _require(_sha256_text(canonical_text) == tts["canonical_sha256"], "TTS 원문 해시가 일치하지 않습니다.", failures)
    _require(
        assembly_result["quality_report"]["tts_subtitle_sync"]["passed"],
        "TTS/자막 동기화 검증이 통과하지 못했습니다.",
        failures,
    )
    _require(
        assembly_result["quality_report"]["tts_subtitle_sync"]["canonical_text_sha256"] == tts["canonical_sha256"],
        "MP4 검증의 대본 해시가 조립 입력과 다릅니다.",
        failures,
    )
    _require(
        assembly_result["quality_report"]["tts_subtitle_sync"]["subtitle_text_match"],
        "자막이 대본 원문과 일치하지 않습니다.",
        failures,
    )
    _require(assembly_result["scene_count"] == len(scenes), "MP4 장면 수가 조립 입력과 다릅니다.", failures)
    _require(assembly_result["kling_clip_count"] == 0, "정적 조립 결과에 Kling 클립이 포함됐습니다.", failures)

    semantic_candidates = [
        scene["scene_id"] for scene in scenes if scene["visual_mode"] == "semantic_illustration"
    ]
    report = {
        "run_id": "visual_mix_nine_scene_lineage_preflight_20260803",
        "scope": "approved_nine_images_static_assembly_read_only",
        "external_request_started": False,
        "image_or_video_generated": False,
        "status": "passed" if not failures else "failed",
        "failures": failures,
        "visual_mode_counts": dict(sorted(mode_counts.items())),
        "raw_visual_mode_counts": dict(sorted(raw_mode_counts.items())),
        "assets": asset_rows,
        "script_tts_subtitle_contract": {
            "canonical_sha256": tts["canonical_sha256"],
            "subtitle_text_match": assembly_result["quality_report"]["tts_subtitle_sync"]["subtitle_text_match"],
            "subtitle_cue_count": assembly_result["quality_report"]["tts_subtitle_sync"]["subtitle_cue_count"],
        },
        "motion_contract": {
            "current_assembly_selection": [],
            "eligible_only_after_explicit_editor_selection": semantic_candidates,
            "blocked_for_article_and_info": [
                scene["scene_id"] for scene in scenes if scene["visual_mode"] != "semantic_illustration"
            ],
        },
        "static_assembly": {
            "video_path": str(VIDEO_PATH.relative_to(REPO_ROOT)),
            "duration_seconds": assembly_result["duration_seconds"],
            "scene_count": assembly_result["scene_count"],
            "kling_clip_count": assembly_result["kling_clip_count"],
            "thumbnail_started": assembly_input["thumbnail_started"],
        },
        "review_dossier": str(DOSSIER_PATH.relative_to(REPO_ROOT)),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "scene_count": len(scenes),
        "visual_mode_counts": report["visual_mode_counts"],
        "external_request_started": False,
        "report_path": str(REPORT_PATH.relative_to(REPO_ROOT)),
        "failures": failures,
    }, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

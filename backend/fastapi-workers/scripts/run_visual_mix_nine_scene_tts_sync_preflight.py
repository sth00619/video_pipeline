"""선택한 9장과 승인 대본의 TTS·자막 계보를 API 호출 없이 점검한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from app.utils.narration_contract import NarrationContractError, build_script_contract, text_sha256


REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_SCRIPT = REPO_ROOT / "artifacts/gemini_pilot/kospi_august_2026_e2e/script_result.json"
VISUAL_INPUT = REPO_ROOT / "backend/fastapi-workers/pilot-inputs/visual_mix_nine_scene_input.json"
OUTPUT_PATH = REPO_ROOT / "artifacts/diagnostics/visual_mix_nine_scene_tts_sync_20260803.json"


def main() -> int:
    script_payload = json.loads(SOURCE_SCRIPT.read_text(encoding="utf-8"))
    visual_payload = json.loads(VISUAL_INPUT.read_text(encoding="utf-8"))
    sections = list(script_payload.get("sections") or [])
    script = str(script_payload.get("script") or "")

    report: dict = {
        "scope": "tts_subtitle_sync_only",
        "tts_api_called": False,
        "gemini_api_called": False,
        "kling_started": False,
        "mp4_assembly_started": False,
        "thumbnail_started": False,
        "selected_visual_scene_ids": [scene["scene_id"] for scene in visual_payload.get("scenes") or []],
        "source_script_path": str(SOURCE_SCRIPT.relative_to(REPO_ROOT)),
        "source_script_sha256": text_sha256(script),
        "source_section_count": len(sections),
        "result": "blocked",
    }
    try:
        report["narration_contract"] = build_script_contract(script, sections)
        report["result"] = "ready_for_tts_generation"
    except NarrationContractError as exc:
        report["blocker"] = str(exc)
        report["required_next_action"] = (
            "새 승인 대본을 장면 원문에서 다시 확정한 뒤 동일 원문으로 TTS를 생성하고, "
            "그 결과의 canonical_text_sha256과 자막 청크를 이 검증기에 다시 입력합니다."
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "ready_for_tts_generation" else 2


if __name__ == "__main__":
    raise SystemExit(main())

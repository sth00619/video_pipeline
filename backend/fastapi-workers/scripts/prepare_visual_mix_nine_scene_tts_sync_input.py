"""선택한 9장에 대응하는 승인 대본 발췌본을 계보와 함께 고정한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from app.utils.narration_contract import build_script_contract, text_sha256


REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_SCRIPT = REPO_ROOT / "artifacts/gemini_pilot/kospi_august_2026_e2e/script_result.json"
OUTPUT_PATH = REPO_ROOT / "artifacts/diagnostics/visual_mix_nine_scene_tts_sync_input_20260803.json"

# 각 묶음은 기존 승인 장면의 원문을 그대로 이어 붙인다. 새 문장을 만들지 않는다.
SCENE_BINDINGS = [
    ("article_kospi", "article_evidence", [47, 48, 49, 50, 51, 52], "visual_mix_nine_scene_r4_info_retry_20260803/article_kospi.png"),
    ("article_us_market", "article_evidence", [53, 54, 55, 56, 57, 58, 59, 60], "visual_mix_nine_scene_r4_info_retry_20260803/article_us_market.png"),
    ("article_sector", "article_evidence", [61, 62, 63, 64, 65, 66, 67], "visual_mix_nine_scene_r4_info_retry_20260803/article_sector.png"),
    ("semantic_rates_flow", "semantic_illustration", [55, 56, 57], "visual_mix_nine_scene_r4_semantic_rates_layout_retry_20260803/semantic_rates_flow.png"),
    ("semantic_bigtech_ai", "semantic_illustration", [62, 63, 64, 65], "visual_mix_nine_scene_r4_remaining_five_20260803/semantic_bigtech_ai.png"),
    ("semantic_chip_kospi", "semantic_illustration", [68, 69, 70, 71, 72, 73, 74], "visual_mix_nine_scene_r4_remaining_five_20260803/semantic_chip_kospi.png"),
    ("info_semiconductor", "archetype_explainer", [68, 69, 70, 71, 72, 73, 74], "visual_mix_nine_scene_r4_remaining_five_20260803/info_semiconductor.png"),
    ("info_dollar", "archetype_explainer", [32, 33, 34, 35, 36], "visual_mix_nine_scene_r4_info_retry_20260803/info_dollar.png"),
    ("info_fear", "archetype_explainer", [26, 27, 28, 29, 30, 31], "visual_mix_nine_scene_r4_info_retry_20260803/info_fear.png"),
]


def main() -> int:
    payload = json.loads(SOURCE_SCRIPT.read_text(encoding="utf-8"))
    source_sections = list(payload.get("sections") or [])
    selected_sections: list[dict] = []

    for scene_id, visual_mode, indexes, relative_asset in SCENE_BINDINGS:
        source_texts = [str(source_sections[index].get("content") or source_sections[index].get("text") or "").strip() for index in indexes]
        content = " ".join(text for text in source_texts if text)
        if not content:
            raise RuntimeError(f"{scene_id}에 연결할 승인 대본 원문이 없습니다.")
        selected_sections.append({
            "scene_id": scene_id,
            "content": content,
            "text": content,
            "visual_mode": visual_mode,
            "source_section_indexes": indexes,
            "source_text_sha256": [text_sha256(text) for text in source_texts],
            "selected_asset_path": str(REPO_ROOT / "backend/fastapi-workers/out/v5_pilot/visual_mix_nine_scene" / relative_asset),
        })

    script = "\n\n".join(section["content"] for section in selected_sections)
    contract = build_script_contract(script, selected_sections)
    result = {
        "run_id": "visual_mix_nine_scene_tts_sync_20260803",
        "scope": "tts_subtitle_sync_only",
        "source_script_path": str(SOURCE_SCRIPT.relative_to(REPO_ROOT)),
        "source_script_sha256": text_sha256(str(payload.get("script") or "")),
        "script": script,
        "sections": selected_sections,
        "narration_contract": contract,
        "tts_api_called": False,
        "gemini_api_called": False,
        "kling_started": False,
        "mp4_assembly_started": False,
        "thumbnail_started": False,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": result["run_id"], "scene_count": len(selected_sections), "canonical_text_sha256": contract["canonical_text_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

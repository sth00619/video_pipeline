import json
from pathlib import Path

from scripts.audit_script_reference_prompt_lineage import build_report


REPO = Path(__file__).resolve().parents[3]
SPEC = REPO / "docs/evidence/wo_provider_01_reopen_runtime_20260828/scene07-promptfix-canary-spec.json"


def test_scene07_lineage_reconstructs_actual_reference_order_and_final_prompt():
    report, bounded, final = build_report(SPEC)

    assert report["scope"].endswith("no external API call")
    assert [item["name"] for item in report["stages"]["reference_selection"]["selected"]] == [
        "channel_character_face_range_v2.png",
        "channel_character_face_scene05_v1.png",
        "channel_style_job52_data_lab.png",
    ]
    assert "FINAL GEMINI REFERENCE CONTRACT [job52-range-v2-operational-v3-eye-layers]" in final
    assert final.endswith(bounded)
    assert "non-linguistic shapes" not in bounded
    assert report["findings"]["deterministic_surface_prompt_conflict_after_fix"] is False


def test_scene07_lineage_distinguishes_pilot_surface_error_from_common_gap():
    report, _bounded, _final = build_report(SPEC)

    assert report["findings"]["pilot_surface_semantic_mismatch"] is True
    assert report["findings"]["pilot_only_plan_source"].endswith("prepare_pilot_scene")
    assert "object-level" in report["findings"]["common_pipeline_gap"]
    duplicates = report["findings"]["duplicate_active_reference_hashes"]
    assert duplicates == [[
        "channel_style_job52_semiconductor.png",
        "channel_style_semiconductor_production_scene_v1.png",
        "17ae053e86a9c99b2eda45d03c3ac9ae176f19a44e8b9cb5b0d0cb42be97479d",
    ]]

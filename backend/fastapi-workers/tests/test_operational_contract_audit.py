from pathlib import Path

from app.utils.operational_contract_audit import (
    PIPELINE_OPERATIONAL_CONTRACT_VERSION,
    build_operational_contract_audit,
)


def test_operational_contract_registry_is_global_and_stage_specific() -> None:
    audit = build_operational_contract_audit(
        "images",
        checks={"tts_subtitle_sync": True},
    )

    assert audit["version"] == PIPELINE_OPERATIONAL_CONTRACT_VERSION
    assert audit["scope"] == "all_jobs_all_topics"
    assert audit["entrypoint"] == "video_generation_button"
    assert audit["job_specific_patch"] is False
    assert audit["stage"] == "images"
    assert audit["checks"] == {"tts_subtitle_sync": True}
    assert {
        "research_and_script",
        "timing_and_caption",
        "image_semantics_and_style",
        "text_and_fact_integrity",
        "character_integrity",
        "provider_request_control",
        "motion_and_assembly",
    }.issubset(audit["contracts"])


def test_every_paid_or_approval_stage_emits_the_operational_contract_audit() -> None:
    root = Path("/repo")
    expected = {
        "backend/fastapi-workers/app/workers/script_worker.py": 'build_operational_contract_audit("script"',
        "backend/fastapi-workers/app/workers/tts_worker.py": 'build_operational_contract_audit("tts"',
        "backend/fastapi-workers/app/workers/images_worker.py": 'build_operational_contract_audit("images"',
        "backend/fastapi-workers/app/workers/longform_worker.py": 'build_operational_contract_audit("longform"',
    }
    for relative, marker in expected.items():
        assert marker in (root / relative).read_text(encoding="utf-8"), relative


def test_spring_preserves_the_audit_in_every_stage_asset() -> None:
    root = Path("/repo/backend/spring-app/src/main/java/com/pipeline/video/dto")
    for name in (
        "ScriptGenerateResponse.java",
        "TtsGenerateResponse.java",
        "ImagesGenerateResponse.java",
        "LongformGenerateResponse.java",
    ):
        source = (root / name).read_text(encoding="utf-8")
        assert '@JsonProperty("operational_contract_audit")' in source, name

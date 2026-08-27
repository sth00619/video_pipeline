from pathlib import Path

from PIL import Image

from app.main import SingleImageGenerateRequest
from app.workers.images_worker import ImagesWorker


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class _Provider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_image(self, **kwargs) -> bool:
        self.calls.append(kwargs)
        Image.effect_noise((1920, 1080), 24).convert("RGB").save(kwargs["output_path"])
        return True


def test_single_scene_request_preserves_complete_scene_contract() -> None:
    fields = SingleImageGenerateRequest.model_fields

    assert "scene_meta" in fields


def test_single_scene_regeneration_uses_the_operational_image_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = _Provider()
    worker = ImagesWorker()
    inspections: list[str] = []

    monkeypatch.setattr(
        "app.providers.factory.get_image_provider",
        lambda: provider,
    )
    monkeypatch.setattr(
        "app.workers.images_worker._inspect_generated_textless_image",
        lambda scene, path: inspections.append(f"base:{Path(path).name}") or {"passed": True},
    )
    monkeypatch.setattr(
        "app.workers.images_worker._inspect_generated_visual_image",
        lambda scene, path: inspections.append(f"final:{Path(path).name}") or {"passed": True},
    )
    monkeypatch.setattr(
        "app.workers.images_worker._apply_fal_motion_safety_contract",
        lambda scenes: {"eligible": 0, "blocked": len(scenes)},
    )
    monkeypatch.setattr(
        "app.workers.images_worker._load_default_references",
        lambda: [],
    )
    monkeypatch.setattr(
        "app.workers.images_worker.ProviderRequestAudit.for_job",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "app.workers.images_worker.acquire_image_job_lock",
        lambda job_id: "test-lock",
    )
    monkeypatch.setattr(
        "app.workers.images_worker.release_image_job_lock",
        lambda job_id, token: None,
    )

    result = worker.generate_single_scene(
        scene={
            "index": 7,
            "text": "반도체 생산라인의 수익 구조를 확인합니다.",
            "prompt_en": "A semiconductor production line with one gold coin analyst.",
            "section": "data",
            "screen_texts": [],
            "screen_text_plan": [],
            "bubble_policy": "forbidden",
            "art_direction": {"character_required": True},
        },
        job_id=9007,
        output_dir=tmp_path,
        character_image_path=None,
        character_style_prompt=None,
    )

    assert result["index"] == 7
    assert result["generation_method"] == "single_scene_operational"
    assert result["image_text_contract"]["approved_texts"] == []
    assert result["character_integrity_contract"]["bubble_policy"] == "forbidden"
    assert provider.calls
    assert "FINAL CHARACTER QUALITY BOUNDARY" in provider.calls[0]["prompt"]
    assert provider.calls[0]["gemini_request_audit"] is not None
    assert inspections == [
        "base:scene_007_regenerate_raw.png",
        "final:scene_007_regenerate_final.png",
    ]


def test_single_scene_regeneration_does_not_silently_fallback_to_a_chart() -> None:
    source = Path("app/main.py").read_text(encoding="utf-8")
    endpoint = source.split("async def generate_single_image", 1)[1].split(
        "# ============================\n# [S2-2]", 1
    )[0]

    assert "Matplotlib 차트 폴백" not in endpoint
    assert "_render_section" not in endpoint


def test_spring_has_no_metadata_free_single_scene_bypass() -> None:
    source = (
        REPOSITORY_ROOT
        / "backend/spring-app/src/main/java/com/pipeline/video/service/FastApiClient.java"
    ).read_text(encoding="utf-8")

    assert source.count('postJson(fastApiUrl + "/workers/images/generate-single"') == 1
    assert 'bodyMap.put("scene_meta"' in source

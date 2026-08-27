"""V5 Gemini 어댑터는 비용 단가 없이 유료 실행을 준비하지 못해야 한다."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.providers.gemini_provider import (
    GeminiModel,
    GeminiProvider,
    GeminiProviderError,
    _load_default_references,
    select_contextual_reference_paths,
)


def test_gemini_estimate_requires_explicit_approved_rate():
    prior = os.environ.pop("V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD", None)
    try:
        try:
            GeminiProvider(api_key="test-key").estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
            assert False, "명시적 단가 없이 비용 추정이 통과했습니다."
        except GeminiProviderError:
            pass
    finally:
        if prior is not None:
            os.environ["V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD"] = prior


def test_p1_comparison_forces_one_provider_attempt(tmp_path: Path, monkeypatch):
    observed = {}

    class FakeNanaBananaProvider:
        def generate(self, **kwargs):
            observed.update(kwargs)
            Path(kwargs["output_path"]).write_bytes(b"test-image")

    import app.providers.real.image as image_module
    monkeypatch.setattr(image_module, "NanaBananaProvider", FakeNanaBananaProvider)
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference")
    class Audit:
        def summary(self):
            return {"entries": []}
    audit = Audit()

    result = GeminiProvider(api_key="test-key").generate(
        "prompt", model=GeminiModel.PRO, reference_image_paths=[str(reference)], request_audit=audit,
    )

    assert result.image_bytes == b"test-image"
    assert observed["gemini_max_attempts"] == 1
    assert observed["gemini_request_audit"] is audit
    assert observed["gemini_reference_contract_declared"] is True
    assert observed["character_style_prompt"] == "none"
    assert observed["suppress_legacy_style_lock"] is True
    assert "explicitly selected character reference" in observed["prompt"]
    assert "let the written scene choose expression, costume, action, headwear, and framing" in observed["prompt"]
    assert "do not force every scene into one studio template" in observed["prompt"].lower()


def test_provider_selects_scene_relevant_job52_references_when_callers_omit_them(tmp_path: Path, monkeypatch):
    observed = {}

    class FakeNanaBananaProvider:
        def generate(self, **kwargs):
            observed.update(kwargs)
            Path(kwargs["output_path"]).write_bytes(b"test-image")

    import app.providers.real.image as image_module
    import app.v5.providers.gemini_provider as provider_module

    monkeypatch.setattr(image_module, "NanaBananaProvider", FakeNanaBananaProvider)
    face_range = tmp_path / "channel_character_face_range_v2.png"
    semiconductor = tmp_path / "channel_style_semiconductor_production_scene_v1.png"
    lab = tmp_path / "channel_style_semiconductor_growth_scene_v1.png"
    briefing = tmp_path / "channel_style_job52_briefing.png"
    face_range.write_bytes(b"face-range")
    semiconductor.write_bytes(b"semiconductor")
    lab.write_bytes(b"lab")
    briefing.write_bytes(b"briefing")
    monkeypatch.setattr(
        provider_module,
        "_load_default_references",
        lambda: [str(face_range), str(briefing), str(lab), str(semiconductor)],
    )

    GeminiProvider(api_key="test-key").generate("semiconductor wafer production line", model=GeminiModel.PRO)

    assert observed["character_image_paths"] == [str(face_range), str(semiconductor), str(lab)]
    assert "shared face construction as the identity contract" in observed["prompt"]
    assert "Costume and headwear remain scene-specific" in observed["prompt"]
    assert "detached translucent glass card" in observed["prompt"].lower()


def test_style_only_reference_does_not_turn_into_a_mascot_identity(tmp_path: Path, monkeypatch):
    observed = {}

    class FakeNanaBananaProvider:
        def generate(self, **kwargs):
            observed.update(kwargs)
            Path(kwargs["output_path"]).write_bytes(b"test-image")

    import app.providers.real.image as image_module
    monkeypatch.setattr(image_module, "NanaBananaProvider", FakeNanaBananaProvider)
    style = tmp_path / "style_reference_v4_medium_clean.png"
    style.write_bytes(b"style")

    GeminiProvider(api_key="test-key").generate(
        "NO mascot in this scene", model=GeminiModel.PRO, reference_image_paths=[str(style)],
    )

    assert "No single authoritative mascot model sheet is supplied" in observed["prompt"]
    assert "collectively define the channel's acceptable visual range" in observed["prompt"]
    assert "same face proportions" not in observed["prompt"]


def test_default_reference_bank_uses_job52_scene_range_not_mismatched_single_sheets():
    names = [Path(path).name for path in _load_default_references()]

    assert len(names) == 8
    assert names[0] == "channel_character_face_range_v2.png"
    assert "channel_style_semiconductor_growth_scene_v1.png" in names
    assert "channel_style_semiconductor_production_scene_v1.png" in names
    assert "character_reference_v4_identity_clean.png" not in names
    assert "style_reference_v4_medium_clean.png" not in names


def test_semiconductor_context_uses_approved_production_scenes_not_hologram_data_lab():
    selected = select_contextual_reference_paths(
        "semiconductor wafer production line",
        _load_default_references(),
    )

    assert [Path(path).name for path in selected] == [
        "channel_character_face_range_v2.png",
        "channel_style_semiconductor_production_scene_v1.png",
        "channel_style_semiconductor_growth_scene_v1.png",
    ]
    assert "channel_style_job52_data_lab.png" not in [Path(path).name for path in selected]


def test_contextual_reference_selection_preserves_explicit_character_and_uses_only_nearby_style_refs(tmp_path: Path):
    character = tmp_path / "user_character_reference.png"
    character.write_bytes(b"character")
    selected = select_contextual_reference_paths(
        "stormy forecast weather-map outlook",
        [str(character), *_load_default_references()],
    )

    assert selected[0] == str(character)
    assert len(selected) == 3
    assert [Path(path).name for path in selected[1:]] == [
        "channel_style_job52_risk_map.png",
        "channel_style_job52_market_flow.png",
    ]


def test_contextual_reference_selection_can_reduce_only_the_second_style_reference_after_transient_failure():
    selected = select_contextual_reference_paths(
        "semiconductor wafer production line",
        _load_default_references(),
        max_references=2,
    )

    assert [Path(path).name for path in selected] == [
        "channel_character_face_range_v2.png",
        "channel_style_semiconductor_production_scene_v1.png",
    ]

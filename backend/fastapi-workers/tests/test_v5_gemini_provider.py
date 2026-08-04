"""V5 Gemini 어댑터는 비용 단가 없이 유료 실행을 준비하지 못해야 한다."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider, GeminiProviderError


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
    audit = object()

    result = GeminiProvider(api_key="test-key").generate(
        "prompt", model=GeminiModel.PRO, reference_image_paths=[str(reference)], request_audit=audit,
    )

    assert result.image_bytes == b"test-image"
    assert observed["gemini_max_attempts"] == 1
    assert observed["gemini_request_audit"] is audit
    assert observed["gemini_reference_contract_declared"] is True
    assert observed["character_style_prompt"] == "none"
    assert observed["suppress_legacy_style_lock"] is True
    assert "same face proportions" in observed["prompt"]
    assert "one continuous full-bleed scene" in observed["prompt"]


def test_provider_loads_both_approved_references_when_callers_omit_them(tmp_path: Path, monkeypatch):
    observed = {}

    class FakeNanaBananaProvider:
        def generate(self, **kwargs):
            observed.update(kwargs)
            Path(kwargs["output_path"]).write_bytes(b"test-image")

    import app.providers.real.image as image_module
    import app.v5.providers.gemini_provider as provider_module

    monkeypatch.setattr(image_module, "NanaBananaProvider", FakeNanaBananaProvider)
    character = tmp_path / "character.png"
    style = tmp_path / "style.png"
    character.write_bytes(b"character")
    style.write_bytes(b"style")
    monkeypatch.setattr(provider_module, "_load_default_references", lambda: [str(character), str(style)])

    GeminiProvider(api_key="test-key").generate("prompt", model=GeminiModel.PRO)

    assert observed["character_image_paths"] == [str(character), str(style)]


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

    assert "No mascot identity reference is supplied" in observed["prompt"]
    assert "visual style only" in observed["prompt"]
    assert "same face proportions" not in observed["prompt"]

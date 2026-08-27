"""WO-IMG-01-D 얼굴 참조·프롬프트 계약의 선행 실패 명세."""
from pathlib import Path

from app.v5.providers import gemini_provider
from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider


def test_default_face_reference_uses_user_approved_six_scene_v2():
    assert gemini_provider._FACE_RANGE_REF_NAME == "channel_character_face_range_v2.png"
    path = Path(gemini_provider.__file__).resolve().parents[3] / "out/references" / gemini_provider._FACE_RANGE_REF_NAME
    assert path.is_file()


def test_face_reference_prompt_prioritizes_measured_face_without_freezing_costume(tmp_path: Path, monkeypatch):
    observed = {}

    class FakeNanaBananaProvider:
        def generate(self, **kwargs):
            observed.update(kwargs)
            Path(kwargs["output_path"]).write_bytes(b"test-image")

    import app.providers.real.image as image_module

    monkeypatch.setattr(image_module, "NanaBananaProvider", FakeNanaBananaProvider)
    face_range = tmp_path / "channel_character_face_range_v2.png"
    style = tmp_path / "channel_style_job52_briefing.png"
    face_range.write_bytes(b"face-range-v2")
    style.write_bytes(b"style")

    GeminiProvider(api_key="test-key").generate(
        "economic briefing with the gold coin mascot",
        model=GeminiModel.PRO,
        reference_image_paths=[str(face_range), str(style)],
    )

    prompt = observed["prompt"]
    assert "38% to 58% of the full visible eye width" in prompt
    assert "soft forehead reflection highlight is required" in prompt
    assert "gently curved eyebrows" in prompt
    assert "sharply angled or deeply furrowed eyebrows" in prompt
    assert "face construction takes priority over background and prop detail" in prompt
    assert "Costume and headwear remain scene-specific" in prompt
    assert "Do not force one outfit" in prompt

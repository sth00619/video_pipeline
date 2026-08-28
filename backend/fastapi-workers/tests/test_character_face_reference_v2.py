"""WO-IMG-01-D 얼굴 참조·프롬프트 계약의 선행 실패 명세."""
from pathlib import Path

from app.v5.providers import gemini_provider
from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider
from scripts.audit_character_face_contract import build_report


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
    assert "white sclera is a surrounding eye region" in prompt
    assert "catchlight dot inside an otherwise solid black oval does not count as sclera" in prompt
    assert "warm brown iris inside the sclera" in prompt
    assert "darker pupil inside that iris" in prompt
    assert "soft forehead reflection highlight is required" in prompt
    assert "gently curved eyebrows" in prompt
    assert "sharply angled or deeply furrowed eyebrows" in prompt
    assert "face construction takes priority over background and prop detail" in prompt
    assert "Costume and headwear remain scene-specific" in prompt
    assert "Do not force one outfit" in prompt


def test_existing_pilot_face_failures_are_quantitatively_reproduced():
    # archive 격리 테스트는 외부 대형 산출물 없이 좌표·산술 계약을 검증한다.
    # 실제 파일 해시는 증거 생성 스크립트의 기본 경로에서 별도로 강제한다.
    report = build_report(verify_sources=False)
    assert report["source_hashes_verified"] is False
    assert report["approved_reference_pass_count"] == 6
    assert report["pilot_failure_reproduced_count"] == 3
    pilot_rows = [row for row in report["samples"] if row["kind"] == "pilot_failure"]
    assert {row["scene"] for row in pilot_rows} == {2, 7, 35}
    assert all(not row["face_contract_pass"] for row in pilot_rows)


def test_scene07_reopen_candidate_still_fails_measured_face_contract():
    report = build_report(verify_sources=False)
    rows = [row for row in report["samples"] if row["kind"] == "reopen_candidate"]
    assert report["reopen_candidate_failure_count"] == 1
    assert len(rows) == 1
    assert rows[0]["scene"] == 7
    assert rows[0]["mean_iris_eye_width_ratio"] == 1.0
    assert rows[0]["checks"]["sclera_visible"] is False
    assert rows[0]["checks"]["warm_brown_iris"] is False
    assert rows[0]["checks"]["layered_catchlights"] is False
    assert rows[0]["face_contract_pass"] is False


def test_scene07_promptfix_candidate_improves_sclera_but_still_fails_face_contract():
    report = build_report(verify_sources=False)
    rows = [row for row in report["samples"] if row["kind"] == "promptfix_candidate"]
    assert report["promptfix_candidate_failure_count"] == 1
    assert len(rows) == 1
    assert rows[0]["scene"] == 7
    assert rows[0]["checks"]["sclera_visible"] is True
    assert rows[0]["checks"]["iris_width_ratio_in_range"] is False
    assert rows[0]["checks"]["warm_brown_iris"] is False
    assert rows[0]["checks"]["layered_catchlights"] is False
    assert rows[0]["checks"]["eyebrow_shape_allowed"] is False
    assert rows[0]["face_contract_pass"] is False


def test_common_quality_floor_scene07_reproduces_black_oval_without_sclera():
    report = build_report(verify_sources=False)
    rows = [row for row in report["samples"] if row["kind"] == "common_quality_floor_candidate"]
    assert report["common_quality_floor_candidate_failure_count"] == 1
    assert len(rows) == 1
    assert rows[0]["scene"] == 7
    assert rows[0]["checks"]["sclera_visible"] is False
    assert rows[0]["checks"]["warm_brown_iris"] is False
    assert rows[0]["observation"].startswith("흰 캐치라이트 점은 있으나")
    assert rows[0]["face_contract_pass"] is False

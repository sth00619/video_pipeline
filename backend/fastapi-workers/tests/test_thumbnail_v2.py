from pathlib import Path

import pytest
from PIL import Image, ImageFilter

from app.services.thumbnail.v2.brief import ThumbnailBriefV2, validate_brief
from app.services.thumbnail.v2.compose import ThumbnailV2Composer
from app.services.thumbnail.v2.semantic_emphasis import SemanticEmphasis
from app.services.thumbnail.v2.typography import BLACK_HAN_PROFILE


def _scene(tmp_path: Path, kind: str = "chart") -> dict:
    path = tmp_path / "chart.png"
    Image.new("RGB", (1920, 1080), (25, 70, 95)).save(path)
    # New scene contract persists a pre-character clean plate. Tests that
    # exercise a cutout-led preset must opt into that contract explicitly.
    return {"scene_id": "s1", "image_path": str(path), "clean_plate_path": str(path), "scene_kind": kind, "used_in_final_video": True,
            "asset_layout_metadata": {"clean_plate_path": str(path), "negative_space": {"x": .07, "y": .08, "width": .39, "height": .38}, "duplicate_character_count": 0}}


def _brief() -> dict:
    return {"template": "chart_warning", "headline": [{"text": "반도체 주가", "tone": "white"}, {"text": "지금 확인할 핵심", "tone": "yellow"}, {"text": "12.5% 급등", "tone": "red"}], "primary_subject": {"kind": "chart", "asset_id": "chart", "source_ref": "facts[0]"}, "secondary_subject": {"allowed": False}, "emphasis": {"kind": "circle"}, "speech_bubble": "이 구간을 보세요!"}


def test_contract_rejects_article_without_evidence():
    with pytest.raises(ValueError):
        ThumbnailBriefV2.model_validate({**_brief(), "template": "article_evidence", "primary_subject": {"kind": "article", "asset_id": "a"}})


def test_contract_rejects_reference_channel_phrase():
    brief = ThumbnailBriefV2.model_validate({**_brief(), "headline": [{"text": "경제 사냥꾼", "tone": "white"}, {"text": "지금 확인", "tone": "yellow"}]})
    assert any("banned phrase" in item for item in validate_brief(brief))


def test_semantic_arrow_requires_source_and_display_font_is_packaged():
    assert BLACK_HAN_PROFILE.require_font().is_file()
    with pytest.raises(ValueError, match="requires source"):
        SemanticEmphasis.model_validate({
            "kind": "arrow", "target": {"x": .1, "y": .1, "width": .2, "height": .2}, "reason_ref": "facts[0]",
        })


def test_v2_composes_provenance_backed_png(tmp_path):
    primary = _scene(tmp_path)
    support = dict(primary)
    support["scene_id"] = "s2"
    support_path = tmp_path / "support.png"
    Image.new("RGB", (1920, 1080), (95, 30, 35)).save(support_path)
    support["image_path"] = str(support_path)
    support["scene_kind"] = "ai_bg"
    result = ThumbnailV2Composer().render(output_path=str(tmp_path / "thumb.png"), format_name="longform", candidates=[primary, support], brief=_brief(), verified_facts=[{"claim": "검증"}])
    assert result["mode"] == "v2_template"
    assert Path(result["provenance_path"]).is_file()
    assert result["variants"][0]["supporting_scene_ids"] == ["s2"]
    assert len(result["variants"]) == 3
    for variant in result["variants"]:
        copy = " ".join(item["text"] for item in variant["headline"])
        assert copy.count("'") == 2
        assert len(variant["headline"]) == 2
        assert variant["qa"]["copy_fill"] >= .58
        assert variant["qa"]["text_scale"] >= .74
        assert variant["qa"]["mobile_font_px"] >= 18
    assert result["variants"][0]["headline"] != result["variants"][1]["headline"]
    with Image.open(tmp_path / "thumb.png") as image:
        assert image.size == (1920, 1080)


def test_blurred_face_is_rejected_and_sharp_approved_face_is_used(tmp_path):
    scene = _scene(tmp_path, kind="person")
    sharp_path = tmp_path / "sharp-person.png"
    sharp = Image.effect_noise((500, 700), 110).convert("RGBA")
    sharp.save(sharp_path)
    blurred_path = tmp_path / "blurred-person.png"
    sharp.filter(ImageFilter.GaussianBlur(24)).save(blurred_path)

    def photo(photo_id, path, person_id="person-1", person_name="테스트 인물"):
        return {
            "photo_id": photo_id,
            "person_id": person_id,
            "person_name": person_name,
            "match_term": person_name,
            "match_source": "script_context",
            "cutout_path": str(path),
            "license_type": "OWNED",
            "approved": True,
            "rights_review_status": "APPROVED",
        }

    brief = {
        **_brief(),
        "template": "person_headline",
        "primary_subject": {"kind": "person", "asset_id": "approved-person"},
    }
    result = ThumbnailV2Composer().render(
        output_path=str(tmp_path / "person-thumb.png"),
        format_name="longform",
        candidates=[scene],
        brief=brief,
        person_photos=[photo("blurred", blurred_path), photo("sharp", sharp_path)],
        verified_facts=[{"claim": "검증"}],
    )
    assert [item["photo_id"] for item in result["asset_rejections"]] == ["blurred"]
    assert result["variants"][0]["qa"]["face_sharpness"] >= 120
    assert result["variants"][0]["qa"]["passed"] is True
    person_meta = result["variants"][0]["person"]
    assert {key: person_meta[key] for key in ["person_id", "person_name", "photo_id", "match_term", "match_source"]} == {
        "person_id": "person-1",
        "person_name": "테스트 인물",
        "photo_id": "sharp",
        "match_term": "테스트 인물",
        "match_source": "script_context",
    }
    assert person_meta["rights"]["license_type"] == "OWNED"
    assert person_meta["rights"]["approved"] is True
    assert person_meta["rights"]["rights_review_status"] == "APPROVED"
    assert person_meta["rendering"] == {
        "source": "approved_licensed_photo",
        "effects": ["mask_only_red_glow", "white_outline", "drop_shadow"],
        "generative_face_edit": False,
    }


def test_two_people_rotate_across_automatic_recommendations(tmp_path):
    scene = _scene(tmp_path, kind="person")
    first_path = tmp_path / "first-person.png"
    second_path = tmp_path / "second-person.png"
    Image.effect_noise((520, 720), 105).convert("RGBA").save(first_path)
    Image.effect_noise((500, 700), 115).convert("RGBA").save(second_path)

    def photo(photo_id, person_id, person_name, path):
        return {
            "photo_id": photo_id,
            "person_id": person_id,
            "person_name": person_name,
            "match_term": person_name,
            "match_source": "script_context",
            "cutout_path": str(path),
            "license_type": "OWNED",
            "approved": True,
            "rights_review_status": "APPROVED",
        }

    brief = {
        **_brief(),
        "template": "person_headline",
        "primary_subject": {"kind": "person", "asset_id": "approved-person"},
    }
    result = ThumbnailV2Composer().render(
        output_path=str(tmp_path / "people-thumb.png"),
        format_name="longform",
        candidates=[scene],
        brief=brief,
        person_photos=[
            photo("first", "person-1", "첫 인물", first_path),
            photo("second", "person-2", "두 번째 인물", second_path),
        ],
        verified_facts=[{"claim": "검증"}],
    )

    assert result["variants"][0]["person"]["photo_id"] != result["variants"][2]["person"]["photo_id"]
    assert all(variant["preset"] == "person_led" for variant in result["variants"])
    assert all(variant["creative_mode"] == "real_person" for variant in result["variants"])


def test_person_and_mascot_are_separate_recommendation_modes(tmp_path):
    scene = _scene(tmp_path, kind="person")
    person_path = tmp_path / "person.png"
    Image.effect_noise((520, 720), 115).convert("RGBA").save(person_path)
    mascot_path = tmp_path / "selected-mascot.png"
    Image.new("RGBA", (380, 560), (245, 193, 26, 255)).save(mascot_path)
    brief = {
        **_brief(),
        "template": "person_headline",
        "primary_subject": {"kind": "person", "asset_id": "approved-person"},
        "speech_bubble": "지금 봐야 해요!",
    }
    photo = {
        "photo_id": "approved", "person_id": "person-1", "person_name": "테스트 인물",
        "match_term": "테스트", "match_source": "script_context", "cutout_path": str(person_path),
        "license_type": "OWNED", "approved": True, "rights_review_status": "APPROVED",
    }
    result = ThumbnailV2Composer().render(
        output_path=str(tmp_path / "split-modes.png"), format_name="longform",
        candidates=[scene], brief=brief, person_photos=[photo], mascot_path=str(mascot_path),
        verified_facts=[{"claim": "검증"}],
    )
    assert [item["creative_mode"] for item in result["variants"]] == [
        "real_person", "real_person", "mascot_only",
    ]
    assert result["variants"][2]["person"] is None
    assert result["variants"][2]["template_id"] == "mascot_headline"


def test_mascot_only_template_is_a_separate_creative_mode(tmp_path):
    scene = _scene(tmp_path, kind="chart")
    mascot_path = tmp_path / "selected-mascot.png"
    mascot = Image.new("RGBA", (440, 600), (0, 0, 0, 0))
    for y in range(60, 540):
        for x in range(70, 370):
            if ((x - 220) / 150) ** 2 + ((y - 300) / 240) ** 2 < 1:
                mascot.putpixel((x, y), (116, 205, 108, 255))
    mascot.save(mascot_path)
    brief = {
        **_brief(),
        "template": "mascot_headline",
        "headline": [
            {"text": "반도체 상승 신호", "tone": "white"},
            {"text": "지금 확인할 핵심", "tone": "yellow"},
        ],
        "secondary_subject": {"allowed": True, "emotion": "worried"},
        "speech_bubble": "이 구간을 보세요!",
    }

    result = ThumbnailV2Composer().render(
        output_path=str(tmp_path / "mascot-thumb.png"),
        format_name="longform",
        candidates=[scene],
        brief=brief,
        mascot_path=str(mascot_path),
        verified_facts=[{"claim": "검증"}],
    )

    assert result["variants"][0]["template_id"] == "mascot_headline"
    assert result["variants"][0]["preset"] == "mascot_led"
    assert result["variants"][0]["creative_mode"] == "mascot_only"
    assert result["variants"][0]["qa"]["passed"] is True


def test_legacy_integrated_scene_is_not_reused_for_cutout_mode(tmp_path):
    source_path = tmp_path / "integrated-character.png"
    source = Image.new("RGB", (1920, 1080), (24, 40, 72))
    # Bright red left third models an existing in-video mascot; the blue right
    # board is the clean visual plate we expect the thumbnail to retain.
    Image.new("RGB", (820, 1080), (220, 35, 35)).save(tmp_path / "left.png")
    source.paste(Image.open(tmp_path / "left.png"), (0, 0))
    source.save(source_path)
    scene = {
        "scene_id": "integrated",
        "image_path": str(source_path),
        "scene_kind": "chart",
        "used_in_final_video": True,
        "character_regions": [{"x": .015, "y": .1, "width": .41, "height": .79}],
    }
    mascot_path = tmp_path / "mascot.png"
    Image.new("RGBA", (320, 500), (240, 196, 20, 255)).save(mascot_path)
    brief = {
        **_brief(),
        "template": "mascot_headline",
        "headline": [{"text": "캐릭터 하나만", "tone": "white"}, {"text": "선명하게 보여요", "tone": "yellow"}],
        "secondary_subject": {"allowed": True, "emotion": "worried"},
    }
    result = ThumbnailV2Composer().render(
        output_path=str(tmp_path / "clean-mascot.png"),
        format_name="longform",
        candidates=[scene],
        brief=brief,
        mascot_path=str(mascot_path),
        verified_facts=[{"claim": "검증"}],
        variants=1,
    )
    # Old jobs have no pre-composite plate: the planner must fall back to a
    # chart candidate instead of cropping/guessing around an embedded mascot.
    assert result["variants"][0]["template_id"] == "chart_warning"
    assert result["variants"][0]["creative_mode"] == "chart_only"

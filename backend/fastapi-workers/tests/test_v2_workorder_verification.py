"""Workorder v2/v3 specific feature verification tests."""
import pytest
import json
from app.utils.art_direction import direct_scenes, ARCHETYPE_TO_COSTUME, SHARED_STYLE_LOCK_PROMPT, SHARED_MASCOT_STYLE_LOCK_PROMPT
from app.utils.quality_gate import assess_image_qa_gates
from app.providers.real.prompt_builder import STYLE_LOCK, TEMPLATE_STYLE_LOCK


def test_character_required_policy_enforcement():
    scenes = direct_scenes([
        {"text": "기사 출처 뉴스 화면", "section": "background", "visual_mode": "article_evidence"},
        {"text": "로켓 발사 상징 장면", "section": "scenario", "visual_mode": "semantic_illustration"},
        {"text": "계기판 관제실 수치 설명", "section": "data", "visual_mode": "archetype_explainer"},
    ])
    reqs = [s["art_direction"]["character_required"] for s in scenes]
    assert reqs == [False, True, True], f"Expected [False, True, True], got {reqs}"


def test_archetype_to_costume_single_source_of_truth():
    assert "port_emergency" in ARCHETYPE_TO_COSTUME
    assert ARCHETYPE_TO_COSTUME["port_emergency"] == "safety_vest"
    assert ARCHETYPE_TO_COSTUME["retail_shock"] == "detective"
    assert ARCHETYPE_TO_COSTUME["briefing_podium"] == "tuxedo_host"

    scenes = direct_scenes([
        {"text": "항구 물류 비상", "section": "intro", "archetype": "port_emergency"},
        {"text": "마트 물가 쇼크", "section": "data", "archetype": "retail_shock"},
        {"text": "브리핑 발표", "section": "conclusion", "archetype": "briefing_podium"},
    ])
    costumes = [s["art_direction"]["role_costume"] for s in scenes]
    assert costumes == ["safety_vest", "detective", "tuxedo_host"]


def test_qa_gates_all_four_items():
    # 1. Valid scene
    valid_scene = {
        "visual_mode": "semantic_illustration",
        "art_direction": {"character_required": True, "costume_role": "analyst"},
        "character_regions": [{"height": 0.45}],
        "prompt_en": "Goldie standing in a laboratory with clean unlabeled screens (3-5px equivalent outlines)",
    }
    gate = assess_image_qa_gates(valid_scene)
    assert gate["passed"] is True
    assert gate["checked_items"] == [
        "character_presence", "frame_height_one_third", "coin_face_visibility", "background_textless_digits"
    ]

    # 2. Failing scene (missing character, height < 1/3, obscured face, baked-in digits)
    invalid_scene = {
        "visual_mode": "semantic_illustration",
        "art_direction": {"character_required": False, "costume_role": "full_helmet"},
        "character_regions": [{"height": 0.20}],
        "prompt_en": "Mascot standing next to a screen showing number 8930 and KOSPI 5593",
    }
    fail_gate = assess_image_qa_gates(invalid_scene)
    assert fail_gate["passed"] is False
    assert "character_missing_when_required" in fail_gate["warnings"]
    assert any("character_height_below_one_third" in w for w in fail_gate["warnings"])
    assert "coin_face_obscured_by_headwear" in fail_gate["warnings"]
    assert any("background_screen_contains_digits" in w for w in fail_gate["warnings"])


def test_template_style_lock_preserves_textless_numeric_ban():
    assert "NO numbers" in STYLE_LOCK
    assert "NO numbers" in TEMPLATE_STYLE_LOCK
    assert "Depict exactly one large unlabeled physical information board" in TEMPLATE_STYLE_LOCK

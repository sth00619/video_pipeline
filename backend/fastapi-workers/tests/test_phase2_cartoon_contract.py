from app.pipeline.scene_director import fallback_spec
from app.providers.real.prompt_builder import build_prompt
from app.utils.art_direction import compile_editorial_prompt, direct_scenes
from app.workers.character_library_worker import ROLE_COSTUME_CONFIGS


def test_every_directed_scene_uses_a_role_costume_asset_with_legacy_fallback():
    scenes = direct_scenes([
        {"section": "intro", "content": "시장 하락 위험을 점검합니다."},
        {"section": "background", "content": "공급망 구조를 살펴봅니다."},
        {"section": "data", "content": "KOSPI 최근 추이를 확인합니다."},
        {"section": "action", "content": "두 조건을 비교합니다."},
        {"section": "conclusion", "content": "회복 가능성을 정리합니다."},
    ])
    for scene in scenes:
        direction = scene["art_direction"]
        assert direction["role_costume"] in {"field_reporter", "professor", "anchor", "referee", "analyst"}
        assert direction["costume_state"] in {"neutral", "highlight", "worried"}
        assert direction["pose_asset"].startswith(direction["role_costume"] + "_")
        assert direction["fallback_pose"]
        assert scene["style_profile"] == "editorial_comic_2d"
        assert direction["layer_pipeline"]["render_clean_plate"] is True
        assert direction["layer_pipeline"]["z_order"] == [
            "clean_background", "verified_info_surface", "character_foreground", "editorial_text",
        ]


def test_role_costume_library_has_the_phase_two_fifteen_assets():
    assert len(ROLE_COSTUME_CONFIGS) == 15
    assert set(ROLE_COSTUME_CONFIGS) >= {
        "field_reporter_worried", "professor_neutral", "anchor_highlight",
        "referee_neutral", "analyst_worried",
    }


def test_locked_prompt_keeps_background_and_data_surface_in_one_cartoon_medium():
    prompt = build_prompt(fallback_spec("scene-1", "시장 위험을 설명합니다."), {"verified": True})
    lower = prompt.lower()
    assert "non-negotiable art direction" in lower
    assert "same hand-illustrated cartoon medium" in lower
    assert "no photorealism" in lower
    assert "chalkboard" in lower


def test_editorial_prompt_never_allows_model_generated_decorative_labels():
    prompt = compile_editorial_prompt(
        {"section": "data", "art_direction": {"decorative_text_allowed": True}},
        "A cartoon market scene",
    ).lower()
    assert "no decorative labels" in prompt


def test_data_composition_alternates_mascot_and_information_surface_sides():
    scenes = direct_scenes([
        {"section": "data", "content": "KOSPI 최근 추이를 확인합니다."},
        {"section": "data", "content": "관련 종목의 등락률을 비교합니다."},
    ])
    first, second = (scene["art_direction"] for scene in scenes)
    assert first["reference_composition"]["id"] == "data_lab"
    assert first["character_placement"] == "right third"
    assert first["data_surface"]["x"] < 500
    assert first["data_surface_kind"] == "monitor"
    assert first["surface_contract"]["geometry"] == "planar_quad"
    assert second["reference_composition"]["id"] == "factory_panel"
    assert second["character_placement"] == "left third"
    assert second["data_surface"]["x"] > 900
    assert second["data_surface_kind"] == "inspection_clipboard"
    assert second["surface_contract"]["marker_rgb"] is not None


def test_data_prompt_uses_the_actual_composition_side_not_a_hard_coded_board_side():
    prompt = compile_editorial_prompt(
        {
            "section": "data",
            "market_chart": {"visual_theme": "chalkboard", "visual_kind": "trend_dashboard"},
            "art_direction": {"character_required": True, "character_placement": "right third"},
        },
        "A cartoon market scene",
    ).lower()
    assert "right third" in prompt
    assert "left-side board" in prompt


def test_character_library_uses_korean_pose_briefs_and_background_free_cartoon_prompt():
    from app.workers.character_library_worker import CharacterLibraryWorker, POSE_CONFIGS
    configs = {**POSE_CONFIGS, **ROLE_COSTUME_CONFIGS}
    assert all(any("가" <= char <= "힣" for char in config["desc"]) for config in configs.values())
    prompt = CharacterLibraryWorker._build_character_prompt(
        "노란 금화 카툰 마스코트", POSE_CONFIGS["thinking"]["desc"], POSE_CONFIGS["thinking"]["model_desc"], POSE_CONFIGS["thinking"]["model_wardrobe"],
    ).lower()
    assert "finger touching the temple" in prompt
    assert "no cast shadow" in prompt
    assert "no human person" in prompt
    assert "tailored navy presenter blazer" in prompt

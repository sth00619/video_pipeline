import json
from pathlib import Path

from app.utils.composition_density_profile import (
    COMPOSITION_DENSITY_PROFILES,
    composition_density_profile_for_scene,
    composition_density_prompt,
)
from app.v5.scene.prompt_builder import ARCHETYPES
from app.v5.scene.runtime_contract import attach_v5_scene_contracts
from app.workers.images_worker import _bounded_text_generation_prompt


def _job52_scenes() -> dict[int, dict]:
    path = Path(__file__).resolve().parent / "fixtures/job52_sparse_density_scenes.json"
    return {int(scene["index"]): scene for scene in json.loads(path.read_text(encoding="utf-8"))}


def test_every_operational_archetype_has_a_separate_density_profile():
    assert set(ARCHETYPES) <= set(COMPOSITION_DENSITY_PROFILES)
    for archetype in ARCHETYPES:
        profile = COMPOSITION_DENSITY_PROFILES[archetype]
        assert profile.min_background_elements >= 5
        assert profile.required_depth_layers == ("foreground", "midground", "background")
        assert profile.text_surface_anchors
        assert profile.reference_background_type
        assert 0 < profile.max_unmotivated_peripheral_blank_ratio <= .35


def test_density_prompt_requires_layers_without_inviting_filler_text_or_numbers():
    profile = COMPOSITION_DENSITY_PROFILES["risk_control_room"]
    prompt = composition_density_prompt(profile).lower()

    assert "composition density profile [risk_control_room]" in prompt
    assert f"at least {profile.min_background_elements}" in prompt
    assert "foreground" in prompt and "midground" in prompt and "background" in prompt
    assert "do not use words, pseudo-text, digits, tick labels, equations, microprint" in prompt
    assert "approved scene-local text contract" in prompt


def test_job52_sparse_regression_scenes_resolve_profiles_without_scene_number_branches():
    scenes = _job52_scenes()

    scene00 = composition_density_profile_for_scene(scenes[0])
    scene07 = composition_density_profile_for_scene(scenes[7])
    scene28 = composition_density_profile_for_scene(scenes[28])

    assert scene00.id == "trade_calculator"
    assert scene07.id == "data_lab"
    assert scene28.id == "risk_control_room"


def test_common_bounded_prompt_carries_density_profile_and_preserves_text_contract():
    scene = dict(_job52_scenes()[7])
    scene["screen_texts"] = ["삼성전자", "SK하이닉스", "코스피", "143조 원"]
    prompt = _bounded_text_generation_prompt(scene["prompt_en"], audit_target=scene)

    assert "COMPOSITION DENSITY PROFILE [data_lab]" in prompt
    assert "143조 원" not in prompt
    assert scene["composition_density_profile"]["id"] == "data_lab"
    assert scene["screen_texts"] == ["삼성전자", "SK하이닉스", "코스피", "143조 원"]


def test_split_comparison_legacy_scene_gets_density_without_becoming_an_archetype_patch():
    scene = dict(_job52_scenes()[15])
    profile = composition_density_profile_for_scene(scene)

    assert profile.id == "split_comparison"
    assert "legacy scene" not in composition_density_prompt(profile).lower()


def test_trade_calculator_has_one_explanation_device_and_does_not_duplicate_the_scale_on_a_board():
    profile = COMPOSITION_DENSITY_PROFILES["trade_calculator"]
    prompt = composition_density_prompt(profile).lower()

    assert profile.max_primary_explanation_devices == 1
    assert "one balance scale" in profile.device_role_contract.lower()
    assert "chalkboard" in profile.device_role_contract.lower()
    assert "must not duplicate" in profile.device_role_contract.lower()
    assert "environment and props only" in prompt
    assert "mascot face, eye structure, line weight" in prompt


def test_reference_benchmark_drives_archetype_specific_blank_space_budgets():
    assert COMPOSITION_DENSITY_PROFILES["classroom"].max_unmotivated_peripheral_blank_ratio == .04
    assert COMPOSITION_DENSITY_PROFILES["data_lab"].max_unmotivated_peripheral_blank_ratio == .05
    assert COMPOSITION_DENSITY_PROFILES["risk_control_room"].max_unmotivated_peripheral_blank_ratio == .08
    assert COMPOSITION_DENSITY_PROFILES["evidence_insert"].max_unmotivated_peripheral_blank_ratio == .35
    prompt = composition_density_prompt(COMPOSITION_DENSITY_PROFILES["classroom"])
    assert "below about 4%" in prompt
    assert "not an invitation to add text" in prompt


def test_risk_control_room_does_not_invite_an_ambiguous_handheld_risk_prop():
    profile = COMPOSITION_DENSITY_PROFILES["risk_control_room"]
    prompt = composition_density_prompt(profile).lower()

    assert "one narration-essential risk prop" not in prompt
    assert "mounted to the console" in prompt
    assert "ambiguous handheld" in prompt
    assert "weapon" in prompt


def test_explicit_operational_archetype_survives_v5_contract_attachment():
    scenes = _job52_scenes()
    planned = attach_v5_scene_contracts([scenes[0], scenes[7], scenes[28]])
    assert [scene["v5_render_contract"]["selection"]["archetype"] for scene in planned] == [
        "trade_calculator", "data_lab", "risk_control_room",
    ]

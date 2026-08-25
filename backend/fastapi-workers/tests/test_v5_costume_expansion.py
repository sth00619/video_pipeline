"""8종 역할은 유지하되 한 모자·의상을 전 장면에 고정하지 않는지 검증한다."""
from __future__ import annotations

from app.v5.scene.prompt_builder import COSTUME_MAP, SceneSpec, build_prompt
from app.v5.scene.runtime_contract import PRESENTATION_BY_ARCHETYPE
from app.v5.scene.scene_type_archetypes import ARCHETYPE_SURFACES, ArchetypeSelection


def test_costume_map_has_eight_entries():
    assert len(COSTUME_MAP) == 8


def test_new_costumes_are_routed_to_real_archetypes():
    assert PRESENTATION_BY_ARCHETYPE["briefing_podium"][1] == "tuxedo_host"
    assert PRESENTATION_BY_ARCHETYPE["real_estate_office"][1] == "architect_planner"
    # classroom keeps the existing "professor" key; only its headwear text changed.
    assert PRESENTATION_BY_ARCHETYPE["classroom"][1] == "professor"


def _selection(archetype: str) -> ArchetypeSelection:
    surfaces = ARCHETYPE_SURFACES[archetype]
    return ArchetypeSelection(
        scene_type="general", archetype=archetype, physical_surfaces=surfaces,
        primary_physical_surface=surfaces[0], alternatives=(), selection_reason="test",
    )


def test_tuxedo_host_prompt_keeps_event_specific_formal_range():
    prompt = build_prompt(
        SceneSpec("host-01", "briefing_podium", "confidence", "tuxedo_host", "present"),
        scene_type_selection=_selection("briefing_podium"),
    ).lower()
    assert "formal stage-host outfit" in prompt
    assert "this particular event" in prompt
    assert "exactly one brown fedora" not in prompt


def test_architect_planner_prompt_requires_context_before_engineering_costume():
    prompt = build_prompt(
        SceneSpec("architect-01", "real_estate_office", "explain", "architect_planner", "calculator_hold"),
        scene_type_selection=_selection("real_estate_office"),
    ).lower()
    assert "only when blueprints, construction, or physical design is central" in prompt
    assert "exactly one yellow hard hat" not in prompt


def test_professor_prompt_allows_scene_specific_academic_variation():
    prompt = build_prompt(
        SceneSpec("prof-01", "classroom", "explain", "professor", "point_left"),
        scene_type_selection=_selection("classroom"),
    ).lower()
    assert "academic explainer outfit suited to this scene" in prompt
    assert "mortarboard, jacket, glasses, or pointer may be used" in prompt


def test_reporter_prompt_does_not_keep_one_fedora_or_navy_uniform():
    prompt = build_prompt(
        SceneSpec("reporter-01", "weather_map", "explain", "reporter", "present"),
        scene_type_selection=_selection("weather_map"),
    ).lower()
    assert "location-appropriate reporter or presenter outfit" in prompt
    assert "formal suit, cap, weather gear, or no hat" in prompt
    assert "brown fedora hat as its only headwear" not in prompt

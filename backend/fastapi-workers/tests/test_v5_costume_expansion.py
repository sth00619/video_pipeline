"""8종 의상 확장: 신규 의상이 실제 아키타입에 배선됐는지, 프롬프트에 헤드웨어
겹침 없이 반영되는지 검증한다."""
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


def test_tuxedo_host_prompt_has_no_fedora_and_no_stacked_headwear():
    prompt = build_prompt(
        SceneSpec("host-01", "briefing_podium", "confidence", "tuxedo_host", "present"),
        scene_type_selection=_selection("briefing_podium"),
    ).lower()
    assert "bare-headed" in prompt
    assert "no fedora" in prompt
    assert "brown fedora hat as its only headwear" not in prompt


def test_architect_planner_prompt_uses_hard_hat_not_fedora():
    prompt = build_prompt(
        SceneSpec("architect-01", "real_estate_office", "explain", "architect_planner", "calculator_hold"),
        scene_type_selection=_selection("real_estate_office"),
    ).lower()
    assert "yellow hard hat" in prompt
    assert "no fedora" in prompt


def test_professor_prompt_uses_mortarboard_not_fedora():
    prompt = build_prompt(
        SceneSpec("prof-01", "classroom", "explain", "professor", "point_left"),
        scene_type_selection=_selection("classroom"),
    ).lower()
    assert "graduation mortarboard cap" in prompt
    assert "no fedora" in prompt


def test_reporter_prompt_still_keeps_the_fedora():
    prompt = build_prompt(
        SceneSpec("reporter-01", "weather_map", "explain", "reporter", "present"),
        scene_type_selection=_selection("weather_map"),
    ).lower()
    assert "brown fedora hat as its only headwear" in prompt

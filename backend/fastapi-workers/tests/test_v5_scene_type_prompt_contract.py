import pytest

from app.v5.scene.prompt_builder import SceneSpec, build_prompt
from app.v5.scene.scene_type_archetypes import (
    ARCHETYPE_SURFACES,
    ArchetypeSelection,
    recommend_v5_archetype,
)


def _new_archetype_selection(archetype: str, scene_type: str = "graph") -> ArchetypeSelection:
    surfaces = ARCHETYPE_SURFACES[archetype]
    return ArchetypeSelection(
        scene_type=scene_type,
        archetype=archetype,
        physical_surfaces=surfaces,
        primary_physical_surface=surfaces[0],
        alternatives=(),
        selection_reason="테스트용 신규 archetype primary 표면 선택",
    )


def test_information_scene_prompt_requires_one_in_world_physical_surface():
    selection = recommend_v5_archetype({
        "scene_type": "metric",
        "content": "시장의 급락과 변동률을 설명합니다.",
    })
    spec = SceneSpec("metric-risk", selection.archetype, "concern", "formal", "present")

    prompt = build_prompt(spec, scene_type_selection=selection).lower()

    assert "in-scene fact-surface contract" in prompt
    assert "the only permitted information-bearing prop is the single large central analog gauge dial face" in prompt
    assert "every other gauge, screen, map, placard, document, and console must show only needles" in prompt
    assert "single large central analog gauge dial face embedded at eye level in the curved operations wall must contain two or three short, clearly readable decorative english labels" in prompt
    assert "do not distribute labels across multiple props" in prompt
    assert "diegetic text placement" not in prompt
    assert "populated analog gauges, labeled control dials" not in prompt
    assert "must visibly include at least two or three short, clearly readable decorative english labels" in prompt
    assert "all gauges, screens, maps, placards, documents, signs, and consoles other than the single large central analog gauge dial face" in prompt
    assert "never place a number or text in a floating card" in prompt
    assert "exact verified facts are composited later by deterministic rendering" in prompt
    assert "do not include any visible typographic mark" not in prompt
    assert "non-negotiable visual style contract" in prompt
    assert "uniform, bold dark-brown ink outline" in prompt


def test_strict_textless_contract_reserves_the_same_prop_without_text_conflict():
    selection = recommend_v5_archetype({
        "scene_type": "graph",
        "content": "시장 추이 차트를 설명합니다.",
    })
    spec = SceneSpec("graph-data", selection.archetype, "explain", "reporter", "present")

    prompt = build_prompt(
        spec,
        visual_text_policy="strict_textless",
        scene_type_selection=selection,
    ).lower()

    assert "in-scene fact-surface contract" in prompt
    assert "do not draw text, digits, symbols, chart labels, or factual values there" in prompt
    assert "never create a blank monitor, detached ui card" in prompt
    assert "must be engraved, painted, chalked, printed, or projected directly" not in prompt
    assert "do not include any visible typographic mark" in prompt


def test_general_scene_does_not_receive_a_number_or_fact_surface_instruction():
    selection = recommend_v5_archetype({
        "scene_type": "general",
        "content": "항만의 긴장된 현장을 설명합니다.",
    })
    spec = SceneSpec("general-port", selection.archetype, "alarm", "safety_vest", "alarmed_run")

    prompt = build_prompt(spec, scene_type_selection=selection).lower()

    assert "fact-surface contract" not in prompt
    assert "does not request numbers, chart ticks, metric displays, or factual data readouts" in prompt
    assert "do not include korean text, korean subtitles, a channel logo, watermark, numbers" in prompt
    assert "sample figures" not in prompt


def test_mismatched_archetype_selection_fails_before_prompt_generation():
    selection = recommend_v5_archetype({"scene_type": "graph", "content": "시장 추이 차트"})
    mismatched = SceneSpec("wrong", "weather_map", "explain", "reporter", "present")

    with pytest.raises(ValueError, match="archetype"):
        build_prompt(mismatched, scene_type_selection=selection)


def test_trade_calculator_forbids_substitute_information_panels():
    selection = recommend_v5_archetype({
        "scene_type": "graph",
        "content": "비교 막대와 비율을 설명합니다.",
    })
    spec = SceneSpec("trade-primary", selection.archetype, "confidence", "vest", "think")

    prompt = build_prompt(spec, scene_type_selection=selection).lower()

    assert selection.archetype == "trade_calculator"
    assert "broad engraved front plinth directly beneath the scale's central pillar" in prompt
    assert "do not substitute the designated plinth with a freestanding information plaque" in prompt
    assert "desk display, framed dashboard, separate board" in prompt


def test_risk_control_room_forbids_substitute_gauge_panels():
    selection = recommend_v5_archetype({
        "scene_type": "metric",
        "content": "시장의 급락과 변동률을 설명합니다.",
    })
    spec = SceneSpec("risk-primary", selection.archetype, "concern", "formal", "present")

    prompt = build_prompt(spec, scene_type_selection=selection).lower()

    assert selection.archetype == "risk_control_room"
    assert "single large central analog gauge dial face embedded at eye level in the curved operations wall" in prompt
    assert "separate warning plaque, independent console screen, floating alert panel" in prompt
    assert "every secondary gauge, warning plaque, console screen, control dial, signal lamp" in prompt
    assert "shipping crate, and closed umbrella must remain non-textual" in prompt


def test_weather_map_keeps_decorative_text_on_one_central_map_wall_region():
    selection = recommend_v5_archetype({
        "scene_type": "graph",
        "content": "미국 지역별 날씨와 시장 변동률 지도 그래프를 설명합니다.",
    })
    spec = SceneSpec("weather-primary", selection.archetype, "explain", "reporter", "present")

    prompt = build_prompt(spec, scene_type_selection=selection).lower()

    assert selection.archetype == "weather_map"
    assert "broad central geographic region of the single large curved illuminated map wall" in prompt
    assert "freestanding forecast board, separate weather card, side monitor" in prompt
    assert "studio camera, tripod, pointer, ceiling spotlight, studio floor device" in prompt
    assert "including cloud icons, directional arrows, and weather bands, must remain non-textual" in prompt


def test_classroom_keeps_decorative_text_on_one_central_chalk_area():
    selection = recommend_v5_archetype({
        "scene_type": "diagram",
        "content": "공급망의 단계와 인과 관계를 설명하는 흐름도입니다.",
    })
    spec = SceneSpec("classroom-primary", selection.archetype, "explain", "professor", "point_left")

    prompt = build_prompt(spec, scene_type_selection=selection).lower()

    assert selection.archetype == "classroom"
    assert "broad central chalk-writing area of the large green teaching wall" in prompt
    assert "pinned paper note, framed wall poster, hanging chart, separate blackboard" in prompt
    assert "wooden desk, open book, wooden pointer, green banker lamp, pinned paper note" in prompt
    assert "including map silhouettes, arrows, circles, and connected marks, must remain non-textual" in prompt


def test_port_and_retail_forbid_their_likely_substitute_surfaces():
    port_selection = recommend_v5_archetype({"scene_type": "text", "content": "항만 물류 컨테이너 경고"})
    port = build_prompt(
        SceneSpec("port-primary", port_selection.archetype, "alarm", "safety_vest", "alarmed_run"),
        scene_type_selection=port_selection,
    ).lower()
    retail_selection = recommend_v5_archetype({"scene_type": "metric", "content": "매장 가격과 소비 지표"})
    retail = build_prompt(
        SceneSpec("retail-primary", retail_selection.archetype, "surprise", "analyst", "calculator_hold"),
        scene_type_selection=retail_selection,
    ).lower()

    assert "single largest foreground shipping container nearest the center dock" in port
    assert "dock warning plate, customs sign, cargo manifest, ship-name marking" in port
    assert "every other stacked shipping container, every non-front face of the designated container" in port
    assert "side wall, end door, roof, corner post, or locking bar" in port
    assert "built-in receipt window recessed into the upper face of the single large checkout device" in retail
    assert "shelf price tag, product package, freestanding total-price card" in retail
    assert "extra wall display, overhead promotional screen, digital signage, or secondary monitor" in retail
    assert "every product shelf, price tag, package, conveyor-belt item" in retail


@pytest.mark.parametrize(
    "archetype",
    ("earnings_stage", "briefing_podium", "real_estate_office", "job_market_hall"),
)
def test_new_archetypes_ban_nonprimary_screen_devices_by_shape(archetype: str):
    selection = _new_archetype_selection(archetype)
    prompt = build_prompt(
        SceneSpec(f"{archetype}-screenless", archetype, "explain", "reporter", "present"),
        scene_type_selection=selection,
    ).lower()

    assert "outside the designated primary surface, do not create any monitor, screen, display, dashboard, kiosk" in prompt
    assert "screen-shaped rectangular information device at all, even when blank or filled only with color blocks" in prompt
    assert "must visibly include at least two or three short, clearly readable decorative english labels" in prompt


def test_real_estate_and_job_market_keep_their_device_like_props_noninformational():
    real_estate = build_prompt(
        SceneSpec("real-estate-blank-device", "real_estate_office", "explain", "reporter", "present"),
        scene_type_selection=_new_archetype_selection("real_estate_office"),
    ).lower()
    job_market = build_prompt(
        SceneSpec("job-market-blank-device", "job_market_hall", "explain", "reporter", "present"),
        scene_type_selection=_new_archetype_selection("job_market_hall"),
    ).lower()

    assert "desk calculator display must remain completely blank and empty" in real_estate
    assert "physical calculator, not a second information surface" in real_estate
    assert "queue-ticket machine must be a mechanical paper dispenser with no screen or display" in job_market
    assert "resume folders must stay closed with no visible paper face" in job_market


@pytest.mark.parametrize(
    ("archetype", "required_rule"),
    (
        (
            "earnings_stage",
            "do not create any additional wall-mounted chart frame, bordered graph panel, or rectangular data display on either side wall",
        ),
        (
            "job_market_hall",
            "do not create any ceiling-mounted or wall-mounted monitor, and the area in front of the consultation counter must not contain any kiosk",
        ),
    ),
)
def test_third_attempt_rules_repeat_in_all_three_prompt_contract_sections(archetype: str, required_rule: str):
    prompt = build_prompt(
        SceneSpec(f"{archetype}-third-attempt", archetype, "explain", "reporter", "present"),
        scene_type_selection=_new_archetype_selection(archetype),
    ).lower()

    assert prompt.count(required_rule) == 3

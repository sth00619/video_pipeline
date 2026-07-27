import hashlib
import pytest
from app.services.info_surface.info_scene_templates import CharacterContract, InfoSceneTemplate, claim_shape_from_payload, select_template
from app.services.info_surface.contracts import plan_from_scene
from app.services.info_surface.narrative_diagrams import DiagramItem, DiagramSpec, render_diagram
from app.pipeline.scene_director import fallback_spec
from app.providers.real.prompt_builder import build_prompt


def _scene(**extra):
    data = {"market_chart": {"verified": True, "source_ref": "fixture"}}
    data.update(extra)
    return data


@pytest.mark.parametrize(("scene", "expected"), [
    (_scene(stage_items=[{"label":"1","source_refs":["x"]}, {"label":"2","source_refs":["x"]}]), "vault_stages"),
    (_scene(structure_items=[{"label":"A"},{"label":"B"}]), "blueprint_board"),
    (_scene(market_chart={"external_rates":[{"label":"한국","value":"10%","source_refs":["x"]}]}), "weather_map_studio"),
    (_scene(causal_nodes=[{"label":"A","source_refs":["x"]},{"label":"B","source_refs":["x"]}]), "chalk_logic_class"),
    (_scene(section="intro"), "field_alert"),
    (_scene(market_chart={"comparison_values":[{"label":"A","value":1},{"label":"B","value":2}]}), None),
])
def test_matcher_is_payload_authoritative(scene, expected):
    selected = select_template(scene, "chalk_logic_class")
    assert (selected.template_id if selected else None) == expected


def test_character_and_board_same_side_is_rejected():
    with pytest.raises(ValueError):
        InfoSceneTemplate(template_id="bad", claim_shape="stages", diagram_kind="stage_locks", character=CharacterContract(costume="x", pose_asset="x", side="left"), surface_kind="monitor", board_side="left", prompt_en="x")


def test_template_prompt_has_no_board_prohibition():
    template = select_template(_scene(stage_items=[{"label":"1","source_refs":["x"]}, {"label":"2","source_refs":["x"]}]))
    prompt = build_prompt(fallback_spec("0", "검증"), None, template)
    assert "Do not depict screens" not in prompt
    assert "large unlabeled physical information board" in prompt


@pytest.mark.parametrize("kind", ["stage_locks", "blueprint_callouts", "map_clouds", "flow_chalk"])
def test_diagram_is_transparent_and_seed_deterministic(kind):
    spec = DiagramSpec(kind=kind, title="검증 제목", items=[DiagramItem("첫째", "10%", emphasis=True), DiagramItem("둘째", "20%")], seed="fixture")
    first = render_diagram(spec, (720, 460)); second = render_diagram(spec, (720, 460))
    assert first.mode == "RGBA" and first.getbbox() is not None
    assert hashlib.sha256(first.tobytes()).digest() == hashlib.sha256(second.tobytes()).digest()


def test_stage_diagram_keeps_10_percent_horizontal_safety_margin():
    spec = DiagramSpec(kind="stage_locks", title="퇴직연금 3단계", items=[
        DiagramItem("가입"), DiagramItem("보장"), DiagramItem("수령", emphasis=True),
    ], seed="fixture")
    rendered = render_diagram(spec, (720, 460))
    bbox = rendered.getchannel("A").getbbox()
    assert bbox is not None
    assert bbox[0] >= 720 * .10 - 8
    assert bbox[2] <= 720 * .90 + 8


def test_external_rate_template_does_not_require_hero_stat_values():
    scene = _scene(market_chart={
        "verified": True,
        "source_ref": "fixture",
        "external_rates": [{"label": "전기차", "value": "100%", "source_refs": ["fixture"]}],
    })
    plan = plan_from_scene(scene)
    assert plan is not None
    assert plan.template_id == "weather_map_studio"
    assert plan.diagram_kind == "map_clouds"
    assert plan.hero_stat is None
    assert plan.surface.marker_rgb == (216, 240, 248)
    assert plan.surface.marker_rgb_candidates == [(138, 183, 188)]
    assert plan.surface.marker_delta_e_max == 12.0

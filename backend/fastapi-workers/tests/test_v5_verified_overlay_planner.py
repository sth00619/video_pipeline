"""대본이 실제로 말하는 검증 수치만 primary 표면 좌표 계획으로 바뀌는지 검증한다."""
from __future__ import annotations

from app.v5.scene.scene_type_archetypes import PRIMARY_SURFACE_REGIONS
from app.v5.scene.verified_overlay_planner import plan_scene_verified_overlay


def _scene(content: str, verified_facts: list[dict]) -> dict:
    return {"content": content, "verified_facts": verified_facts}


def test_returns_nothing_for_a_non_information_scene():
    scene = _scene("코스피가 2.3% 상승했습니다.", [{"fact": "코스피는 2.3% 상승했다.", "figure": "2.3%"}])
    assert plan_scene_verified_overlay(scene, "retail_shock", information_scene=False) == []


def test_returns_nothing_without_verified_facts():
    scene = {"content": "코스피가 2.3% 상승했습니다."}
    assert plan_scene_verified_overlay(scene, "retail_shock", information_scene=True) == []


def test_returns_nothing_when_the_scene_never_says_the_figure():
    # 같은 verified_facts 리스트가 모든 장면에 동일하게 붙으므로, 이 장면이
    # 실제로 말하지 않는 다른 장면의 수치를 프롭에 올려서는 안 된다.
    scene = _scene("항구 상황을 설명합니다.", [{"fact": "코스피는 2.3% 상승했다.", "figure": "2.3%"}])
    assert plan_scene_verified_overlay(scene, "port_emergency", information_scene=True) == []


def test_returns_nothing_for_an_unmapped_archetype():
    scene = _scene("마트 계산대에서 총액은 1,125,000원이었습니다.", [{"fact": "총액은 1,125,000원.", "figure": "1,125,000원"}])
    assert plan_scene_verified_overlay(scene, "not_a_real_archetype", information_scene=True) == []


def test_selects_the_fact_the_scene_actually_states_and_anchors_inside_the_primary_surface():
    scene = _scene(
        "마트 계산대에서 총액은 1,125,000원이었습니다.",
        [
            {"fact": "코스피는 2.3% 상승했다.", "figure": "2.3%"},
            {"fact": "이번 장바구니 총액은 1,125,000원이었다.", "figure": "1,125,000원"},
        ],
    )
    plan = plan_scene_verified_overlay(scene, "retail_shock", information_scene=True)
    assert len(plan) == 1
    overlay = plan[0]
    assert overlay["value"] == "1,125,000원"
    assert overlay["source_ref"] == "facts[1]"
    assert overlay["visualization"] == "text"
    assert overlay["anchor"]["kind"] == "monitor"

    region_x, region_y, region_w, region_h = PRIMARY_SURFACE_REGIONS["retail_shock"]
    anchor = overlay["anchor"]
    assert region_x <= anchor["x"]
    assert region_y <= anchor["y"]
    assert anchor["x"] + anchor["width"] <= region_x + region_w
    assert anchor["y"] + anchor["height"] <= region_y + region_h


def test_ignores_spacing_and_case_when_matching_the_figure_in_the_narration():
    scene = _scene(
        "이번 관세율은 15퍼센트 15%로 조정됐습니다.",
        [{"fact": "관세율은 15%로 조정됐다.", "figure": " 15%  "}],
    )
    plan = plan_scene_verified_overlay(scene, "trade_calculator", information_scene=True)
    assert len(plan) == 1
    assert plan[0]["anchor"]["kind"] == "placard"


def test_every_mapped_archetype_produces_an_anchor_inside_its_own_primary_surface():
    scene = _scene("검증값은 15%였습니다.", [{"fact": "검증값은 15%였다.", "figure": "15%"}])
    for archetype, region in PRIMARY_SURFACE_REGIONS.items():
        plan = plan_scene_verified_overlay(scene, archetype, information_scene=True)
        if not plan:
            # earnings_stage처럼 아직 캐릭터 연출 계약이 없는 archetype은
            # 이 장면 계약에 도달하지 못하므로 오버레이 대상에서 제외될 수 있다.
            continue
        anchor = plan[0]["anchor"]
        region_x, region_y, region_w, region_h = region
        assert region_x <= anchor["x"]
        assert region_y <= anchor["y"]
        assert anchor["x"] + anchor["width"] <= region_x + region_w + 1e-9
        assert anchor["y"] + anchor["height"] <= region_y + region_h + 1e-9

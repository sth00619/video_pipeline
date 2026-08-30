from app.utils.scene_screen_text_planner import (
    attach_scene_screen_texts,
    derive_scene_screen_text_plan,
    derive_scene_screen_texts,
)
from app.v5.scene.runtime_contract import attach_v5_scene_contracts, prompt_for_scene
from app.workers.images_worker import _bounded_text_generation_prompt


def test_extracts_only_exact_scene_local_terms_and_values():
    scene = {"content": "삼성전자가 110조 원 규모의 주주환원 계획을 발표했습니다."}
    assert derive_scene_screen_texts(scene) == ["삼성전자", "주주환원", "110조 원"]


def test_exact_quoted_phrase_prevents_duplicate_numeric_fragment():
    scene = {"content": "매일경제는 '10퍼센트 족쇄'라는 표현을 썼죠."}
    assert derive_scene_screen_texts(scene) == ["10퍼센트 족쇄"]


def test_existing_scene_contract_is_never_overwritten():
    scene = {"content": "코스피는 6696포인트로 마감했습니다.", "screen_texts": ["승인 문구"]}
    assert derive_scene_screen_texts(scene) == ["승인 문구"]
    assert attach_scene_screen_texts([scene])[0]["screen_text_source"] == "explicit_scene_contract"


def test_does_not_invent_a_generic_caption_when_no_approved_display_term_exists():
    assert derive_scene_screen_texts({"content": "시장은 그 선물을 받지 않았죠."}) == []


def test_groups_korean_large_number_units_and_does_not_treat_weeks_as_shares():
    scene = {"content": "약 26조 1640억 원이었고 불과 2주 만에 반등했습니다."}
    assert derive_scene_screen_texts(scene) == ["26조 1640억 원"]


def test_preserves_range_and_composite_won_values_as_complete_approved_strings():
    range_scene = {"content": "삼성전자는 90조에서 110조 원 수준의 주주환원을 공시했습니다."}
    price_scene = {"content": "종가는 25만 7000원을 기록했습니다."}
    percent_scene = {"content": "장중 3~4퍼센트 내려가는 모습이었습니다."}

    assert derive_scene_screen_texts(range_scene) == ["삼성전자", "주주환원", "90조에서 110조 원"]
    assert derive_scene_screen_texts(price_scene) == ["25만 7000원"]
    assert derive_scene_screen_texts(percent_scene) == ["3~4퍼센트"]


def test_keeps_three_entity_labels_and_one_scene_local_numeric_range():
    scene = {
        "content": "미국 반도체주가 급락했고 삼성전자와 SK하이닉스도 장중 3~4퍼센트 내려갔습니다."
    }
    assert derive_scene_screen_texts(scene) == ["반도체", "삼성전자", "SK하이닉스", "3~4퍼센트"]


def test_extracts_general_outlook_and_risk_terms_from_approved_narration():
    scenes = [
        {"content": "이 엇갈림 자체가 불확실성을 보여줍니다. SK하이닉스 이야기를 더 해봅니다."},
        {"content": "왜 이 종목들이 부각된 걸까요? 대형주에 대한 불안감이 존재합니다."},
        {"content": "하지만 동시에 경고도 공존합니다. 전망치가 하향 조정된다는 경고입니다."},
    ]

    assert derive_scene_screen_texts(scenes[0]) == ["엇갈림", "SK하이닉스"]
    assert derive_scene_screen_texts(scenes[1]) == ["대형주"]
    assert derive_scene_screen_texts(scenes[2]) == ["경고", "전망치"]


def test_rederives_old_automatic_screen_texts_but_preserves_explicit_contracts():
    old_auto = {
        "content": "종가는 25만 7000원을 기록했습니다.",
        "screen_texts": ["7000원"],
        "screen_text_source": "approved_narration_exact_extract_v1",
    }
    explicit = {
        "content": "종가는 25만 7000원을 기록했습니다.",
        "screen_texts": ["승인 표기"],
        "screen_text_source": "explicit_scene_contract",
    }

    planned_auto, planned_explicit = attach_scene_screen_texts([old_auto, explicit])
    assert planned_auto["screen_texts"] == ["25만 7000원"]
    assert planned_auto["screen_text_source"] == "approved_narration_exact_extract_v3"
    assert planned_explicit["screen_texts"] == ["승인 표기"]
    assert planned_explicit["screen_text_source"] == "explicit_scene_contract"


def test_auto_plan_maps_comparison_entities_and_summary_to_distinct_scene_objects():
    scene = {
        "content": (
            "삼성전자와 SK하이닉스를 제외해도 코스피 전체 영업이익은 "
            "143조 원으로 집계됐습니다."
        ),
    }
    texts = ["삼성전자", "SK하이닉스", "코스피", "143조 원"]

    plan = derive_scene_screen_text_plan(scene, texts)

    assert [(item["text"], item["semantic_object_id"], item["surface_id"]) for item in plan] == [
        ("삼성전자", "comparison_entity_1", "comparison_prop_left"),
        ("SK하이닉스", "comparison_entity_2", "comparison_prop_right"),
        ("코스피", "market_summary", "summary_monitor"),
        ("143조 원", "market_summary", "summary_monitor"),
    ]
    assert plan[2]["region"] == [0.08, 0.08, 0.84, 0.4]
    assert plan[3]["region"] == [0.08, 0.52, 0.84, 0.4]
    assert plan[3]["purpose"] == "information"


def test_attach_adds_common_auto_surface_plan_without_enabling_unready_renderer():
    scene = {
        "content": "삼성전자와 SK하이닉스를 제외해도 코스피는 143조 원입니다.",
    }

    planned = attach_scene_screen_texts([scene])[0]

    assert planned["screen_text_plan_source"] == "approved_narration_semantic_surface_plan_v1"
    assert len(planned["screen_text_plan"]) == 4
    assert "text_render_policy" not in planned


def test_common_auto_surface_plan_reaches_final_gemini_prompt_without_financial_value():
    scene = {
        "scene_type": "metric",
        "content": (
            "삼성전자와 SK하이닉스를 제외해도 코스피 전체 영업이익은 "
            "143조 원으로 집계됐습니다."
        ),
    }

    planned = attach_scene_screen_texts([scene])
    contracted = attach_v5_scene_contracts(planned)[0]
    final_prompt = _bounded_text_generation_prompt(
        prompt_for_scene(contracted) or "",
        audit_target=contracted,
    )

    assert "143조" not in final_prompt
    assert "left comparison prop" in final_prompt
    assert "right comparison prop" in final_prompt
    assert "central framed summary monitor" in final_prompt
    assert "lower reserved region" in final_prompt
    assert contracted["image_profile"]["model"] == "gemini-3-pro-image"


def test_trade_calculator_uses_one_balance_device_instead_of_a_duplicate_summary_board():
    scene = {
        "scene_type": "metric",
        "content": "PER 4배, 들어보셨나요? 삼성전자와 SK하이닉스 얘기입니다.",
        "v5_scene_type_selection": {"archetype": "trade_calculator"},
    }

    planned = attach_scene_screen_texts([scene])
    contracted = attach_v5_scene_contracts(planned)[0]
    surface_plan = contracted["v5_render_contract"]["surface_caption"]["surface_plan"]

    assert contracted["screen_texts"] == ["삼성전자", "SK하이닉스", "PER 4배"]
    assert {item["visual_device_id"] for item in surface_plan} == {"balance_scale"}
    assert {item["surface_id"] for item in surface_plan} == {
        "balance_scale_plinth",
        "balance_scale_left_pan_label",
        "balance_scale_right_pan_label",
    }
    assert "summary_monitor" not in {item["surface_id"] for item in surface_plan}
    metric = next(item for item in surface_plan if item["surface_id"] == "balance_scale_plinth")
    assert metric["locator_region"] == [0.18, 0.62, 0.42, 0.36]
    assert "scale base" in metric["surface_description"]


def test_shared_summary_monitor_reserves_a_distinct_lower_region_for_numeric_post_render():
    scene = {
        "content": "삼성전자와 SK하이닉스를 제외해도 코스피 전체 영업이익은 143조 원입니다.",
    }

    plan = derive_scene_screen_text_plan(
        scene, ["삼성전자", "SK하이닉스", "코스피", "143조 원"],
    )
    label = next(item for item in plan if item["text"] == "코스피")
    value = next(item for item in plan if item["text"] == "143조 원")

    assert label["surface_id"] == value["surface_id"] == "summary_monitor"
    assert label["region"] == [0.08, 0.08, 0.84, 0.4]
    assert value["region"] == [0.08, 0.52, 0.84, 0.4]
    assert value["locator_region"] == [0.35, 0.08, 0.5, 0.62]
    assert "lower reserved region" in value["surface_description"]

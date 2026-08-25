from app.utils.image_text_contract import (
    build_scene_text_contract,
    detected_deterministic_texts,
    prompt_text_contract_violations,
    require_sanitized_generated_text_prompt,
    visible_text_contract_result,
)


def test_scene_local_approved_english_or_korean_text_is_preserved():
    prompt = (
        'A semiconductor lab with a monitor labeled "SK하이닉스" and '
        'a second sign reading "SILVER", Goldie points at one wafer'
    )

    cleaned, report = require_sanitized_generated_text_prompt(
        prompt, allowed_texts=["SK하이닉스"],
    )

    assert '"SK하이닉스"' in cleaned
    assert "SILVER" not in cleaned
    assert "unlettered scene-integrated visual surface" in cleaned
    assert report["violations_after"] == []


def test_financial_number_is_reserved_for_deterministic_surface_renderer():
    contract = build_scene_text_contract({
        "screen_texts": ["코스피", "6860포인트"],
        "screen_text_validation": {"passed": True},
    })

    assert contract["generated_texts"] == ["코스피"]
    assert contract["deterministic_texts"] == ["6860포인트"]
    assert contract["placement_mode"] == "contextual_supporting"
    assert contract["hierarchy_policy"] == "script_objects_and_action_above_supporting_text"
    assert contract["surface_material_policy"] == "integrated_opaque_scene_surface"
    assert contract["detached_translucent_card_allowed"] is False


def test_generated_base_raster_financial_number_is_detected_even_when_approved():
    scene = {
        "screen_texts": ["거래대금", "10조 2901억 원"],
        "screen_text_validation": {"passed": True},
    }

    assert detected_deterministic_texts(["거래대금", "10조", "2901억 원"], scene) == ["10조 2901억 원"]
    assert detected_deterministic_texts(["거래대금"], scene) == []


def test_global_verified_facts_do_not_expand_current_scene_allowlist():
    contract = build_scene_text_contract({
        "screen_texts": ["PER"],
        "screen_text_validation": {"passed": True},
        "verified_facts": [{"fact": "은 가격", "figure": "257퍼센트"}],
    })

    assert contract["approved_texts"] == ["PER"]
    assert "SILVER" not in contract["approved_texts"]
    assert "257퍼센트" not in contract["approved_texts"]


def test_unapproved_job52_prompt_payloads_are_detected_without_banning_all_text():
    prompt = (
        'A calculator monitor labeled "NET PROFIT", showing exactly 4x multiplier, '
        'and a banner reading "HISTORICAL LOW?"'
    )

    violations = prompt_text_contract_violations(prompt, ["NET PROFIT"])
    cleaned, report = require_sanitized_generated_text_prompt(
        prompt, allowed_texts=["NET PROFIT"],
    )

    assert violations
    assert "NET PROFIT" in cleaned
    assert "HISTORICAL LOW" not in cleaned
    assert report["violations_after"] == []


def test_removing_unapproved_short_label_does_not_create_a_malformed_word():
    prompt = 'A rising chart labeled with a confident "UP" expectation glow'

    cleaned, report = require_sanitized_generated_text_prompt(prompt, allowed_texts=[])

    assert "UP" not in cleaned
    assert "typographylow" not in cleaned
    assert "unlettered scene-integrated visual surface" in cleaned
    assert report["violations_after"] == []


def test_ocr_fast_gate_defers_unlisted_nonnumeric_text_to_visual_review():
    scene = {
        "screen_texts": ["SK하이닉스"],
        "screen_text_validation": {"passed": True},
    }
    accepted = visible_text_contract_result(["SK하이닉스"], scene)
    rejected = visible_text_contract_result(["SK 하이느"], scene)

    assert accepted["passed"] is True
    assert rejected["passed"] is True
    assert rejected["unexpected_texts"] == []
    assert rejected["review_required_nonnumeric_texts"] == ["SK 하이느"]


def test_ocr_fast_gate_rejects_unplanned_duplicate_even_when_spelling_is_approved():
    scene = {
        "screen_texts": ["영업이익"],
        "screen_text_validation": {"passed": True},
    }

    result = visible_text_contract_result(["영업이익", "영업이익"], scene)

    assert result["unexpected_texts"] == []
    assert result["occurrence_counts"] == {"영업이익": 2}
    assert result["duplicate_texts"] == ["영업이익"]
    assert result["passed"] is False


def test_ocr_fast_gate_allows_repetition_only_when_surface_plan_requests_it():
    scene = {
        "screen_texts": ["영업이익"],
        "screen_text_plan": [
            {"text": "영업이익", "surface": "left chart"},
            {"text": "영업이익", "surface": "right chart"},
        ],
        "screen_text_validation": {"passed": True},
    }

    result = visible_text_contract_result(["영업이익", "영업이익"], scene)

    assert result["duplicate_texts"] == []
    assert result["passed"] is True


def test_unapproved_bubble_is_never_promoted_from_bubble_text_alone():
    contract = build_scene_text_contract({
        "bubble_text": "PAST WINS?",
        "bubble_validation": {"passed": True},
    })
    assert contract["bubble_allowed"] is False


def test_multiple_approved_text_surfaces_are_preserved_as_scene_layout_not_one_board():
    contract = build_scene_text_contract({
        "screen_texts": ["현재 전망", "전망 하향"],
        "screen_text_plan": [
            {"text": "현재 전망", "surface": "left forecast zone", "role": "comparison_left"},
            {"text": "전망 하향", "surface": "right forecast zone", "role": "comparison_right"},
        ],
        "screen_text_validation": {"passed": True},
    })

    assert contract["approved_texts"] == ["현재 전망", "전망 하향"]
    assert contract["generated_texts"] == ["현재 전망", "전망 하향"]
    assert contract["surface_count"] == 2
    assert contract["placement_mode"] == "explicit_plan"
    assert contract["hierarchy_policy"] == "follow_explicit_scene_plan"
    assert [item["surface"] for item in contract["surface_plan"]] == [
        "left forecast zone", "right forecast zone",
    ]


def test_holographic_text_surface_requires_explicit_scene_local_material():
    ordinary = build_scene_text_contract({
        "screen_texts": ["영업이익"],
        "screen_text_plan": [{
            "text": "영업이익",
            "surface": "machine-mounted production monitor",
            "surface_style": "opaque_equipment_display",
        }],
        "screen_text_validation": {"passed": True},
    })
    holographic = build_scene_text_contract({
        "screen_texts": ["위험 신호"],
        "screen_text_plan": [{
            "text": "위험 신호",
            "surface": "operations hologram",
            "surface_style": "holographic",
        }],
        "screen_text_validation": {"passed": True},
    })

    assert ordinary["surface_material_policy"] == "integrated_opaque_scene_surface"
    assert ordinary["detached_translucent_card_allowed"] is False
    assert holographic["surface_material_policy"] == "explicit_scene_plan_allows_holographic"
    assert holographic["detached_translucent_card_allowed"] is True

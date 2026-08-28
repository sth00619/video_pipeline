from app.utils.character_integrity_contract import (
    apply_character_integrity_contract,
    resolve_pose_conflicts,
)


def test_pointing_and_arms_crossed_conflict_keeps_one_action():
    prompt = "Goldie stands foreground pointing skeptically at the board, arms crossed in doubt."
    cleaned, reasons = resolve_pose_conflicts(prompt)

    assert "pointing skeptically" in cleaned
    assert "arms crossed" not in cleaned
    assert reasons == ["removed_conflicting_arms_crossed_action"]


def test_unplanned_speech_bubble_is_removed_without_freezing_expression_or_outfit():
    prompt, report = apply_character_integrity_contract(
        "Goldie beside a speech bubble reading the result",
        {"art_direction": {"wardrobe": "navy analyst suit"}},
    )

    assert "speech bubble reading" not in prompt.lower()
    assert "do not force one outfit or one neutral expression" in prompt.lower()
    assert "soft forehead reflection highlight" in prompt.lower()
    assert "natural connected anatomy" in prompt.lower()
    assert "unrelated police or law-enforcement costume" in prompt.lower()
    assert "generic finance-presenter uniform" in prompt.lower()
    assert report["bubble_allowed"] is False


def test_scene_specific_costume_and_expression_are_not_replaced_by_navy_uniform():
    prompt, report = apply_character_integrity_contract(
        "Goldie wears a white laboratory coat and goggles with a delighted face",
        {"scene_spec": {"character_costume": "white laboratory coat and optional goggles"}},
    )

    assert "white laboratory coat and optional goggles" in prompt
    assert "navy finance-presenter suit" not in prompt
    assert "expression and acting change" in prompt.lower()
    assert report["version"] == "character-integrity-v5-coin-silhouette"
    assert report["scene_wardrobe"] == "white laboratory coat and optional goggles"

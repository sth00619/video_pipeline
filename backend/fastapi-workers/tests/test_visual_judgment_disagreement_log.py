from app.utils.visual_judgment_disagreement_log import compare_visual_judgments


def test_disagreement_is_preserved_without_automatic_resolution():
    result = compare_visual_judgments(
        {"style_fidelity": True, "unexpected_or_ambiguous_props": True},
        {"style_fidelity": True, "unexpected_or_ambiguous_props": False},
    )

    assert result["compared_check_count"] == 2
    assert result["agreement_rate"] == 0.5
    assert result["automatic_resolution"] is False
    assert result["disagreements"] == [{
        "check": "unexpected_or_ambiguous_props",
        "automated": True,
        "user": False,
        "resolution": "unresolved_user_review_controls_approval",
    }]

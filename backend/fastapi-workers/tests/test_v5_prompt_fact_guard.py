import pytest

from app.v5.scene.prompt_fact_guard import (
    PromptContainsVerifiedDataError,
    assert_prompt_has_no_verified_numbers,
)


def test_verified_number_in_final_prompt_is_rejected():
    scene = {"scene_id": "s-1", "verified_facts": [{"figure": "15%"}]}
    with pytest.raises(PromptContainsVerifiedDataError, match="15%"):
        assert_prompt_has_no_verified_numbers("Show a 15% rise on a blank board.", scene)


def test_unrelated_prompt_number_is_allowed():
    scene = {"scene_id": "s-2", "verified_facts": [{"figure": "15%"}]}
    assert_prompt_has_no_verified_numbers("Use a clean 2D editorial illustration with no readable text.", scene)


def test_fact_without_number_does_not_block_prompt():
    scene = {"verified_facts": [{"figure": "수입 관세"}]}
    assert_prompt_has_no_verified_numbers("Use a clean editorial illustration.", scene)

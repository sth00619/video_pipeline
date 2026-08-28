from app.utils.scene_visual_quality_contract import build_scene_visual_quality_contract
from app.workers.images_worker import _bounded_text_generation_prompt


def _scene(*, costume: str, emotion: str, action: str, texts: list[str]) -> dict:
    return {
        "text": "승인 대본의 장면별 경제 인과를 설명합니다.",
        "screen_texts": texts,
        "screen_text_validation": {"passed": True},
        "scene_spec": {
            "character_costume": costume,
            "character_emotion": emotion,
            "character_action": action,
        },
        "art_direction": {"character_required": True},
    }


def test_diverse_scenes_share_quality_floor_without_freezing_scene_variables():
    laboratory = _scene(
        costume="semiconductor laboratory coat and goggles",
        emotion="curious surprise",
        action="examining two memory chips",
        texts=["영업이익"],
    )
    field = _scene(
        costume="rainproof field reporter coat",
        emotion="urgent concern",
        action="reporting beside a congested port",
        texts=["수출", "감소"],
    )

    laboratory_contract = build_scene_visual_quality_contract(laboratory)
    field_contract = build_scene_visual_quality_contract(field)

    assert laboratory_contract["version"] == field_contract["version"]
    assert laboratory_contract["shared_quality_floor"] == field_contract["shared_quality_floor"]
    assert laboratory_contract["scene_variables"]["wardrobe"] != field_contract["scene_variables"]["wardrobe"]
    assert laboratory_contract["scene_variables"]["emotion"] != field_contract["scene_variables"]["emotion"]
    assert laboratory_contract["scene_variables"]["action"] != field_contract["scene_variables"]["action"]


def test_deterministic_surface_budget_is_bounded_and_scales_with_content_count():
    one = build_scene_visual_quality_contract(
        _scene(costume="analyst suit", emotion="focused", action="pointing", texts=["143조 원"])
    )
    four = build_scene_visual_quality_contract(
        _scene(
            costume="analyst suit",
            emotion="focused",
            action="comparing two firms",
            texts=["코스피", "영업이익", "143조 원", "두 기업 제외"],
        )
    )

    assert one["deterministic_surface"]["max_single_surface_frame_ratio"] <= 0.16
    assert four["deterministic_surface"]["max_single_surface_frame_ratio"] <= 0.22
    assert one["deterministic_surface"]["max_single_surface_frame_ratio"] < four["deterministic_surface"]["max_single_surface_frame_ratio"]
    assert four["deterministic_surface"]["minimum_storytelling_frame_ratio"] >= 0.60


def test_generation_prompt_carries_shared_floor_and_scene_specific_roles():
    scene = _scene(
        costume="semiconductor laboratory coat and goggles",
        emotion="curious surprise",
        action="examining two memory chips",
        texts=["영업이익"],
    )

    prompt = _bounded_text_generation_prompt(
        "A dense semiconductor laboratory with two chips on a balance.",
        audit_target=scene,
    ).lower()

    assert "common cross-scene acceptance floor" in prompt
    assert "semiconductor laboratory coat and goggles" in prompt
    assert "curious surprise" in prompt
    assert "examining two memory chips" in prompt
    assert "not a fixed costume, expression, pose, or background template" in prompt
    assert "no more than 16 percent of the frame" in prompt
    assert "information-rich economic storytelling" in prompt
    assert scene["scene_visual_quality_contract"]["version"]


def test_targeted_retry_repairs_only_failed_quality_dimensions():
    scene = _scene(
        costume="rainproof field reporter coat",
        emotion="urgent concern",
        action="reporting beside a congested port",
        texts=["수출", "감소"],
    )

    prompt = _bounded_text_generation_prompt(
        "A port scene with one reporter and cargo cranes.",
        retry=True,
        retry_feedback={
            "failure_categories": [
                "character_expression_role",
                "deterministic_surface_oversized",
                "scene_information_density",
            ],
            "reason": "표정 역할, 표면 크기, 정보 밀도 미달",
        },
        audit_target=scene,
    ).lower()

    assert "correct only the face and body acting" in prompt
    assert "shrink only the text-bearing physical surface" in prompt
    assert "restore useful job-52-like information density" in prompt
    assert "preserve every element that was not named" in prompt
    assert "rainproof field reporter coat" in prompt


def test_approved_text_surface_budget_removes_legacy_massive_monitor_conflict():
    scene = _scene(
        costume="white laboratory coat and goggles",
        emotion="confident",
        action="comparing two excluded companies with the market total",
        texts=["삼성전자", "SK하이닉스", "코스피", "143조 원"],
    )

    prompt = _bounded_text_generation_prompt(
        "A dense data laboratory. Behind the mascot, a massive central monitor shows the result. "
        "Two excluded-company containers remain on a side shelf.",
        audit_target=scene,
    ).lower()

    assert "massive central monitor" not in prompt
    assert "bounded central monitor" in prompt
    assert "two excluded-company containers remain" in prompt
    assert "no more than 22 percent of the frame" in prompt


def test_surface_budget_does_not_shrink_non_text_storytelling_props():
    scene = _scene(
        costume="navy analyst jacket",
        emotion="uneasy",
        action="watching unstable large-cap indicators",
        texts=["대형주"],
    )

    prompt = _bounded_text_generation_prompt(
        "A risk control room with a large monitor wall and huge industrial turbines outside. "
        "The mascot studies the market mechanism.",
        audit_target=scene,
    ).lower()

    assert "large monitor wall" not in prompt
    assert "bounded monitor wall" in prompt
    assert "huge industrial turbines" in prompt
    assert "no more than 16 percent of the frame" in prompt

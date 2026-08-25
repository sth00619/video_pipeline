from app.utils.scene_screen_text_planner import attach_scene_screen_texts, derive_scene_screen_texts


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
    assert planned_auto["screen_text_source"] == "approved_narration_exact_extract_v2"
    assert planned_explicit["screen_texts"] == ["승인 표기"]
    assert planned_explicit["screen_text_source"] == "explicit_scene_contract"

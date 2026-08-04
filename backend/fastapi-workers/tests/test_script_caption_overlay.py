from app.postprocess.text_overlay import script_caption, script_visual_phrase, script_visual_plan


def test_script_visual_plan_adds_script_specific_non_numeric_objects():
    plan = script_visual_plan({"content": "반도체 주가 하락 가능성을 살펴봅니다."})

    assert plan["caption"] == "SEMICONDUCTOR GOES DOWN"
    assert plan["direction"] == "down"
    assert "microchip" in plan["prop_visuals"]
    assert "electronics-factory" in plan["background_visuals"]


def test_script_visual_plan_uses_a_single_semantic_caption_for_buy_signal():
    plan = script_visual_plan({"content": "매수 신호를 확인합니다."})

    assert plan["caption"] == "BUY SIGNAL"
    assert plan["direction"] == "up"
    assert "green signal lamp" in plan["prop_visuals"]


def test_script_visual_plan_keeps_an_explicit_non_numeric_visual_intent():
    plan = script_visual_plan({
        "content": "빅테크 실적이 AI 투자 우려를 해소할지 살펴봅니다.",
        "visual_intent": "A processor pipeline feeds an uncertain profit turbine, no text and no numbers.",
    })

    assert "processor pipeline feeds an uncertain profit turbine" in plan["background_visuals"]


def test_script_caption_prefers_script_title_and_removes_numeric_values():
    caption = script_caption({
        "title": "씬 2: 38퍼센트 폭락의 무게 · 4",
        "content": "코스피는 6,595.45포인트로 마감했습니다.",
    })

    assert caption == "폭락의 무게"
    assert not any(character.isdigit() for character in caption)


def test_script_caption_prefers_script_title_over_auxiliary_bubble():
    caption = script_caption({
        "title": "씬 7: 공포 지수가 식었다 · 2",
        "bubble_text": "공포는 조금씩 가라앉고 있습니다",
    })

    assert caption == "공포 지수가 식었다"


def test_script_visual_phrase_tracks_script_meaning_without_numeric_values():
    assert script_visual_phrase({"content": "반도체 주가 하락이 예상됩니다."}) == "SEMICONDUCTOR GOES DOWN"
    assert script_visual_phrase({"title": "씬 7: 공포 지수가 식었다"}) == "FEAR IS COOLING"


def test_script_visual_plan_gives_retail_scenes_a_grocery_theme_instead_of_generic_outlook():
    plan = script_visual_plan({"content": "마트 계산대에서 확인한 장바구니 물가가 크게 상승했다."})

    assert plan["caption"] == "GROCERY BILL SPIKES"
    assert plan["direction"] == "up"
    assert "shopping-basket" in plan["prop_visuals"]
    assert "Korean hypermarket" in plan["background_visuals"]


def test_script_visual_plan_gives_market_share_scenes_a_pie_chart_shape():
    plan = script_visual_plan({"content": "국내 라면 시장에서 농심과 삼양의 시장점유율 구도를 살펴봅니다."})

    assert plan["caption"] == "MARKET SHARE SPLIT"
    assert "pie-chart" in plan["prop_visuals"]
    assert "no numbers and no labels" in plan["prop_visuals"]

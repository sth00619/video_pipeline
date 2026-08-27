from scripts.run_gemini_eight_scene_pilot import _find_exact_token_sequence, prepare_pilot_scene


def _row(text, word, left=0, width=20):
    return {"text": text, "word_num": str(word), "left": str(left), "top": "10",
            "width": str(width), "height": "30"}


def test_exact_korean_label_can_span_complete_ocr_tokens():
    rows = [_row("|", 1), _row("엇", 2, 30), _row("갈", 3, 60), _row("림", 4, 90), _row("ㅣ", 5, 120)]
    hit = _find_exact_token_sequence(rows, "엇갈림", 400)
    assert hit["token_range"] == [1, 3]
    assert hit["character_height_ratio"] == .075


def test_prefix_or_suffix_hangul_cannot_hide_altered_approved_text():
    assert _find_exact_token_sequence([_row("비", 1), _row("영업이익", 2, 30)], "영업이익", 400) is None
    assert _find_exact_token_sequence([_row("영업이익", 1), _row("률", 2, 30)], "영업이익", 400) is None


def test_short_approved_label_lane_explicitly_enables_strict_ocr_policy():
    scene = prepare_pilot_scene(
        {"index": 35, "content": "이익 전망치가 더 내려가는지 보세요."},
        {
            "index": 35,
            "lane": "pilot_only_short_approved_label_measurement",
            "exact_texts": ["전망치"],
            "visual_contract": "승인된 한 문구만 쓴다.",
        },
    )

    assert scene["generated_text_ocr_policy"] == {
        "version": "strict-scene-local-generated-text-v1",
        "require_all_approved": True,
        "reject_unapproved": True,
        "targeted_exact_retry": "local_2x3_tiles_psm6",
    }

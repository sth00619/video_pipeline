from scripts.run_gemini_eight_scene_pilot import _find_exact_token_sequence


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

from app.utils.korean_tts import normalize_korean_numbers_for_tts


def test_financial_decimals_use_compact_natural_korean_reading():
    assert normalize_korean_numbers_for_tts("3.75퍼센트") == "삼쩜칠오퍼센트"
    assert normalize_korean_numbers_for_tts("17.91퍼센트") == "십칠쩜구일퍼센트"

import re

from app.utils.sentence_splitter import split_sentences


def test_decimal_and_sentence_boundaries_are_lossless():
    cases = [
        ("코스닥도 만만치 않았습니다. 5.2% 상승 마감했죠.", 2, "5.2%"),
        ("VIX 지수는 16.5를 기록했습니다. 전일 대비 3.1% 하락입니다.", 2, "16.5"),
        ("달러인덱스 DXY는 100.81이에요. 전날보다 0.3% 내렸습니다.", 2, "100.81"),
        ("오늘 거래량도 주목해야 해요. 오늘 상승을 이끈 주역은 따로 있습니다.", 2, None),
        ("코스피는 2,650.31로 마감! 놀랍죠? 네, 그렇습니다.", 3, "2,650.31"),
        ("이게 바로 3.5세대 반도체입니다.", 1, "3.5세대"),
    ]

    for source, expected_count, protected_text in cases:
        actual = split_sentences(source)
        assert len(actual) == expected_count
        assert protected_text is None or any(protected_text in part for part in actual)
        assert re.sub(r"\s+", "", "".join(actual)) == re.sub(r"\s+", "", source)

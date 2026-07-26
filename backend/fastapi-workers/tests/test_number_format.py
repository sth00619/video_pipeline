import pytest

from app.utils.number_format import format_verified_value


def test_verified_number_formats_are_stable_and_unit_safe():
    assert format_verified_value(1_125_000, "numeral_grouped") == "1,125,000"
    assert format_verified_value(1_125_000, "korean_compact") == "112만 5천 원"
    assert format_verified_value(.021, "percent", sign=True) == "+2.1%"
    assert format_verified_value(12.4, "point", sign=True) == "+12.4pt"
    assert format_verified_value("2026-07-24", "date_ym") == "2026.07"


def test_verified_number_formats_do_not_coerce_incompatible_values():
    with pytest.raises(ValueError):
        format_verified_value(12.4, "numeral_grouped")
    with pytest.raises(ValueError):
        format_verified_value("12.4%", "point")
    with pytest.raises(ValueError):
        format_verified_value("2026년 7월", "date_ym")

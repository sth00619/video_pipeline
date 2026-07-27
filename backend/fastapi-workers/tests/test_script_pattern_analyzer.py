import json
from pathlib import Path

from app.tools.build_reference_baseline import build_reference_baseline
from app.tools.compare_scripts import compare_scripts, render_markdown
from app.utils.quality_gate import assess_script_house_style
from app.utils.script_pattern_analyzer import analyze_script


FIXTURES = Path(__file__).parent / "fixtures" / "scripts"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_good_shorts_has_required_house_style_signals():
    row = _fixture("shorts_good.json")
    profile = analyze_script(row["script"], row).to_dict()

    assert profile["axis1_structure"]["devices_present"]["D1"]
    assert profile["axis1_structure"]["devices_present"]["D6"]
    assert profile["axis1_structure"]["devices_present"]["D8"]
    assert profile["axis5_analogy"]["coverage"] >= 0.8
    assert profile["axis6_hook"]["opening_three_sentence_number_count"] >= 1
    assert profile["axis6_hook"]["has_direct_address"]
    assert profile["axis8_fact"]["numbers_total"] == profile["axis8_fact"]["numbers_traceable"]


def test_missing_hook_is_a_hard_gate_failure():
    row = _fixture("shorts_bad_no_hook.json")
    result = assess_script_house_style(row["script"], format_name="shorts", verified_facts=row["verified_facts"], enabled=True)
    assert not result["passed"]
    assert any(failure["code"] == "MISSING_NUMBER_FIRST_HOOK" for failure in result["hard_failures"])


def test_direct_address_number_intro_does_not_require_a_question():
    script = (
        "님들, 금리 목표 범위는 3.5퍼센트에서 3.75퍼센트야. 또 그대로야. "
        "그래서 이번 발표를 그냥 넘기는 사람도 있어. 근데 숫자 옆 문장을 같이 읽어야 해."
    )
    verified_facts = [{"fact": "금리 목표 범위는 3.5%에서 3.75%로 유지됐다.", "figure": "3.5%~3.75%"}]
    result = assess_script_house_style(script, format_name="shorts", verified_facts=verified_facts, enabled=True)

    assert not any(failure["code"] == "MISSING_NUMBER_FIRST_HOOK" for failure in result["hard_failures"])


def test_disabled_house_style_preserves_existing_generation_path():
    row = _fixture("shorts_bad_no_hook.json")
    result = assess_script_house_style(row["script"], format_name="shorts", verified_facts=row["verified_facts"], enabled=False)
    assert result == {
        "enabled": False,
        "passed": True,
        "hard_failures": [],
        "advisories": [],
        "profile": None,
    }


def test_buy_sell_and_untraceable_number_are_hard_failures():
    buy_sell = _fixture("bad_buy_sell.json")
    buy_sell_result = assess_script_house_style(buy_sell["script"], format_name="shorts", verified_facts=buy_sell["verified_facts"], enabled=True)
    assert any(failure["code"] == "FORBIDDEN_INVESTMENT_OR_HYPE" for failure in buy_sell_result["hard_failures"])

    number = _fixture("bad_untraceable_number.json")
    number_result = assess_script_house_style(number["script"], format_name="shorts", verified_facts=number["verified_facts"], enabled=True)
    assert any(failure["code"] == "UNTRACEABLE_NUMBER" for failure in number_result["hard_failures"])


def test_similarity_gate_and_compare_report_use_aggregate_only():
    good = _fixture("shorts_good.json")
    similar = _fixture("bad_similarity.json")
    similarity = assess_script_house_style(
        similar["script"], format_name="shorts", verified_facts=similar["verified_facts"],
        reference_texts=[similar["script"]], enabled=True,
    )
    assert any(failure["code"] == "REFERENCE_NGRAM_SIMILARITY" for failure in similarity["hard_failures"])

    references = [
        {"source_id": "internal-1", "channel": "benchmark_stock", "rights_basis": "internal_review_or_permission", "format": "shorts", "register": "banmal", "transcript": good["script"]},
        {"source_id": "internal-2", "channel": "general_econ", "rights_basis": "internal_review_or_permission", "format": "shorts", "register": "jondaetmal", "transcript": "복잡한 흐름은 우산을 고르는 일과 같습니다. 조건을 하나씩 확인해 보세요."},
    ]
    baseline = build_reference_baseline(references)
    assert "benchmark_stock:shorts" in baseline["groups"]
    assert "banmal_ratio" not in baseline["groups"]["general_econ:shorts"]["metrics"]
    report = compare_scripts(references, good, "shorts")
    markdown = render_markdown(report)
    assert "상위 격차 3" in markdown
    assert good["script"] not in markdown

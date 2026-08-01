"""V5 walking skeleton의 무료 계약 테스트."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.cost_ledger import Bucket, BudgetExceeded, CostLedger, FxProvider
from app.v5.scene.prompt_builder import ARCHETYPES, BENCHMARK_SCENES, SceneSpec, build_prompt


def test_prompt_excludes_blank_board():
    prompt = build_prompt(BENCHMARK_SCENES[2])
    assert "empty boards" in prompt and "DO NOT INCLUDE" in prompt
    assert "teaching wall" in prompt and "wooden pointer" in prompt


def test_prompt_no_korean_requested():
    assert "DO NOT INCLUDE Korean text" in build_prompt(BENCHMARK_SCENES[0])


def test_prompt_requires_dense_non_factual_background_information():
    prompt = build_prompt(BENCHMARK_SCENES[0])
    assert "BACKGROUND INFORMATION DENSITY" in prompt
    assert "populated analog gauges" in prompt
    assert "sample figures" in prompt


def test_all_benchmark_scenes_valid():
    assert len(BENCHMARK_SCENES) == 8
    for scene in BENCHMARK_SCENES:
        scene.validate()
        assert 0.25 <= scene.frame_occupancy <= 0.50


def test_frame_occupancy_bounds():
    try:
        SceneSpec("bad", "classroom", "happy", "professor", "point_left", 0.60).validate()
        assert False, "범위 밖 화면 점유율이 통과했습니다."
    except ValueError:
        pass


def test_budget_guard_blocks_over_limit():
    os.environ["FX_USD_KRW"] = "1500"
    ledger = CostLedger("test", fx=FxProvider(conservative_buffer=1.0))
    try:
        ledger.guard(Bucket.IMAGE_DRAFT, 2.5)
        assert False, "버킷 초과가 통과했습니다."
    except BudgetExceeded:
        pass


def test_budget_records_and_accumulates():
    os.environ["FX_USD_KRW"] = "1500"
    ledger = CostLedger("test", fx=FxProvider(conservative_buffer=1.0))
    _, rate = ledger.guard(Bucket.IMAGE_DRAFT, 0.015)
    ledger.record(scene_id="s1", provider="bfl", model="flux-2-klein-9b", request_kind="generate", bucket=Bucket.IMAGE_DRAFT, estimated_usd=0.015, actual_usd=0.015, rate=rate, status="ok")
    assert ledger.total_spent_krw() == round(0.015 * 1500)


def test_archetypes_cover_diverse_sets_without_a_split_frame_requirement():
    assert {"port_emergency", "retail_shock", "classroom", "weather_map", "risk_control_room", "trade_calculator", "data_lab"}.issubset(ARCHETYPES)
    assert all(scene.archetype != "split_stage" for scene in BENCHMARK_SCENES)


if __name__ == "__main__":
    import traceback
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")
    raise SystemExit(0 if passed == len(tests) else 1)

import unittest
from unittest.mock import patch

from app import runtime_config
from app.utils.script_length import effective_duration_tolerance, make_length_contract
from app.workers.tts_worker import TtsWorker
from app.workers.script_worker import _is_market_level_forecast


class DeliveryDefaultsTests(unittest.TestCase):
    def test_five_minute_contract_uses_voice_calibrated_baseline(self):
        contract = make_length_contract(5, base_cpm=445, speed=1.0)
        self.assertEqual(contract["target_seconds"], 300)
        self.assertEqual(contract["target_chars"], 2225)

    def test_default_voice_delivery_matches_reference_breaths(self):
        self.assertEqual(runtime_config.value("tts_speed"), 0.9)
        self.assertEqual(runtime_config.value("tts_sentence_pause_ms"), 350)

    @patch("app.utils.script_length.resolve_cpm", return_value=(400.0, 2))
    def test_speed_specific_calibration_is_not_scaled_twice(self, _resolve_cpm):
        contract = make_length_contract(5, base_cpm=445, speed=0.9)

        self.assertEqual(contract["target_chars"], 2000)
        self.assertEqual(contract["effective_cpm"], 400.0)
        self.assertEqual(runtime_config.value("tts_paragraph_pause_ms"), 400)
        self.assertEqual(runtime_config.value("tts_thought_group_pause_ms"), 110)
        characters = [
            {"text": "A", "start": 0.0, "end": 0.1},
            {"text": ".", "start": 0.1, "end": 0.2},
            {"text": "B", "start": 0.2, "end": 0.3},
        ]
        # No native boundary/whitespace: do not cut through connected speech.
        self.assertEqual(TtsWorker._sentence_pause_points(characters), [])

    @patch("app.utils.script_length.resolve_cpm", return_value=(473.87, 1))
    def test_one_matching_real_tts_sample_corrects_the_next_script_length(self, _resolve_cpm):
        contract = make_length_contract(5, base_cpm=445, speed=0.9)

        self.assertEqual(contract["target_chars"], 2369)
        self.assertEqual(contract["effective_cpm"], 473.87)
        self.assertEqual(contract["calibration_samples"], 1)

    @patch("app.runtime_config.value", return_value=0.25)
    @patch("app.utils.script_length.resolve_cpm", return_value=(473.87, 1))
    def test_broad_env_tolerance_cannot_allow_a_short_five_minute_script(self, _resolve_cpm, _value):
        contract = make_length_contract(5, base_cpm=400, speed=0.9)

        self.assertEqual(contract["min_chars"], 2251)
        self.assertEqual(contract["max_chars"], 2487)
        self.assertEqual(contract["tolerance_pct"], 5)
        self.assertEqual(effective_duration_tolerance(0.25), 0.05)

    def test_default_images_are_pro_2k_with_a_mascot(self):
        self.assertEqual(runtime_config.value("image_quality_tier"), "pro")

    def test_broad_market_outlook_does_not_require_an_exact_news_headline(self):
        self.assertTrue(_is_market_level_forecast(["미국 주식 하반기 전망"]))
        self.assertFalse(_is_market_level_forecast(["삼성전자 반도체 실적"]))


if __name__ == "__main__":
    unittest.main()

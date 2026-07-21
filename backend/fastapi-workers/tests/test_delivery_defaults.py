import unittest

from app import runtime_config
from app.utils.script_length import make_length_contract
from app.workers.tts_worker import TtsWorker
from app.workers.script_worker import _is_market_level_forecast


class DeliveryDefaultsTests(unittest.TestCase):
    def test_five_minute_contract_uses_voice_calibrated_baseline(self):
        contract = make_length_contract(5, base_cpm=445, speed=1.0)
        self.assertEqual(contract["target_seconds"], 300)
        self.assertEqual(contract["target_chars"], 2225)

    def test_default_voice_delivery_matches_reference_breaths(self):
        self.assertEqual(runtime_config.value("tts_speed"), 1.0)
        self.assertEqual(runtime_config.value("tts_sentence_pause_ms"), 350)
        self.assertEqual(runtime_config.value("tts_paragraph_pause_ms"), 400)
        self.assertEqual(runtime_config.value("tts_thought_group_pause_ms"), 1100)
        characters = [
            {"text": "A", "start": 0.0, "end": 0.1},
            {"text": ".", "start": 0.1, "end": 0.2},
            {"text": "B", "start": 0.2, "end": 0.3},
        ]
        # No native boundary/whitespace: do not cut through connected speech.
        self.assertEqual(TtsWorker._sentence_pause_points(characters), [])

    def test_default_images_are_pro_2k_with_a_mascot(self):
        self.assertEqual(runtime_config.value("image_quality_tier"), "pro")

    def test_broad_market_outlook_does_not_require_an_exact_news_headline(self):
        self.assertTrue(_is_market_level_forecast(["미국 주식 하반기 전망"]))
        self.assertFalse(_is_market_level_forecast(["삼성전자 반도체 실적"]))


if __name__ == "__main__":
    unittest.main()

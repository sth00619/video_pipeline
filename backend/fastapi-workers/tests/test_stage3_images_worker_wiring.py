import unittest
from unittest.mock import MagicMock, patch
from app.workers.images_worker import ImagesWorker


class TestImagesWorkerStage3Wiring(unittest.TestCase):

    @patch.object(ImagesWorker, "_call_llm", return_value="A physical ticker board displaying USD/KRW Rate dropping to 10M low notch.")
    def test_build_prompt_from_narration_with_entities(self, mock_llm):
        worker = ImagesWorker()
        prompt = worker._build_prompt_from_narration(
            narration="원달러 환율이 10개월 만에 최저치",
            scene_type="comparison",
            title="Scene_6",
            core_entities=["원달러 환율"],
            core_figures=[{"raw": "10개월", "kind": "period"}],
            fictionalized_labels={"원달러 환율": "USD/KRW CORP"},
            visual_mode="article_evidence",
        )
        self.assertIn("CRITICAL ENTITY GROUNDING INSTRUCTIONS", mock_llm.call_args[0][1][0]["content"])
        self.assertIn("USD/KRW CORP", mock_llm.call_args[0][1][0]["content"])
        self.assertIn("10개월", mock_llm.call_args[0][1][0]["content"])


if __name__ == "__main__":
    unittest.main()

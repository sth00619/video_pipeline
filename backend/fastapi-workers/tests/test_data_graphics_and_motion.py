import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.services.bubble_overlay import render_speech_bubble_overlay
from app.services.kling_prompt_builder import build_kling_motion_prompt
from app.utils.intro_motion import select_intro_motion_scene_indices
from app.utils.market_charts import render_market_chart
from app.workers.images_worker import ImagesWorker, _scene_metadata_contract
from app.workers.longform_worker import (
    _apply_speech_bubble_overlay,
    _cap_intro_motion_for_short_video,
    _can_reuse_scene_clip,
    _cleanup_scene_clips,
    _has_manual_kling_selection,
    _minimum_motion_delivery,
    _requires_verified_index_card,
    _scene_clip_fingerprint,
)


class DataGraphicsAndMotionTests(unittest.TestCase):
    def test_image_metadata_contract_reports_future_field_passthrough(self):
        source = [{"index": 0, "future_overlay": {"required": True}, "market_chart": {"verified": True}}]
        output = [{**source[0], "image_path": "/tmp/scene.png"}]
        audit = _scene_metadata_contract(source, output)
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["missing_keys"], [])
        self.assertEqual(audit["market_chart_count"], 1)

    def test_image_stage_normalizes_without_baking_factual_graphics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scene.png"
            Image.new("RGB", (1024, 1024), (45, 55, 65)).save(path, "PNG")

            ImagesWorker()._apply_image_overlays({"section": "data"}, str(path))

            with Image.open(path) as result:
                self.assertEqual(result.size, (1920, 1080))
                self.assertEqual(result.format, "PNG")

    def test_speech_bubble_is_a_transparent_final_frame_overlay(self):
        overlay = render_speech_bubble_overlay("검증된 수치입니다", character_side="left")
        self.assertEqual(overlay.mode, "RGBA")
        self.assertEqual(overlay.size, (1920, 1080))
        self.assertIsNotNone(overlay.getchannel("A").getbbox())

    def test_motion_selection_uses_the_configured_clip_duration(self):
        scenes = [{"duration": 5.0} for _ in range(4)]
        indices, target, actual = select_intro_motion_scene_indices(
            scenes,
            total_duration=20,
            short_seconds=12,
            long_seconds=12,
            short_threshold=30,
            max_clips=4,
            clip_seconds=3,
        )
        self.assertEqual(indices, {0, 1, 2, 3})
        self.assertEqual(target, 12)
        self.assertEqual(actual, 12)

    def test_motion_templates_forbid_camera_motion(self):
        for motion_type in ("chart_shock", "pointing_explain", "thinking_desk", "walking_intro", "celebration"):
            prompt = build_kling_motion_prompt(motion_type)["prompt"].lower()
            self.assertNotIn("zoom", prompt)
            self.assertIn("camera: locked, no movement", prompt)

    def test_static_retry_cache_cannot_bypass_requested_kling_motion(self):
        self.assertFalse(
            _can_reuse_scene_clip(
                "an-existing-static-clip.mp4",
                5.0,
                motion_requested=True,
            )
        )

    def test_clip_cache_requires_matching_source_and_input_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            clip = Path(directory) / "clip.mp4"
            clip.write_bytes(b"placeholder")
            Path(f"{clip}.meta.json").write_text(
                json.dumps({"source_type": "static", "input_fingerprint": "old"}),
                encoding="utf-8",
            )
            with patch("app.workers.longform_worker._verify_video", return_value=True), patch(
                "app.workers.longform_worker._probe_duration", return_value=5.0
            ):
                self.assertFalse(_can_reuse_scene_clip(
                    str(clip), 5.0, motion_requested=True,
                    expected_source_type="kling", expected_fingerprint="new",
                ))
                Path(f"{clip}.meta.json").write_text(
                    json.dumps({"source_type": "kling", "input_fingerprint": "new"}),
                    encoding="utf-8",
                )
                self.assertTrue(_can_reuse_scene_clip(
                    str(clip), 5.0, motion_requested=True,
                    expected_source_type="kling", expected_fingerprint="new",
                ))

    def test_scene_clip_fingerprint_changes_with_verified_chart(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "scene.png"
            image.write_bytes(b"image")
            first = _scene_clip_fingerprint(
                {"market_chart": {"latest": 100}}, str(image), 5.0, "kling"
            )
            second = _scene_clip_fingerprint(
                {"market_chart": {"latest": 101}}, str(image), 5.0, "kling"
            )
            self.assertNotEqual(first, second)

    def test_motion_delivery_gate_requires_three_quarters_of_plan(self):
        self.assertEqual(_minimum_motion_delivery(0), 0)
        self.assertEqual(_minimum_motion_delivery(1), 1)
        self.assertEqual(_minimum_motion_delivery(8), 6)

    def test_nullable_dto_field_does_not_disable_automatic_kling_plan(self):
        self.assertFalse(_has_manual_kling_selection([{"use_kling": None}, {}]))
        self.assertTrue(_has_manual_kling_selection([{"use_kling": False}, {}]))
        self.assertTrue(_has_manual_kling_selection([{"use_kling": True}, {}]))

    def test_floating_text_overlays_are_disabled(self):
        self.assertFalse(_requires_verified_index_card({
            "index_data": {"verified": True, "name": "KOSPI"}
        }))
        self.assertTrue(_apply_speech_bubble_overlay(
            {"bubble_text": "remove me"}, "unused.mp4", Path("."), 0, 5.0, 1
        ))

    def test_one_minute_fal_proof_is_capped_to_four_opening_scenes(self):
        self.assertEqual(_cap_intro_motion_for_short_video(60, 12), 4)
        self.assertEqual(_cap_intro_motion_for_short_video(90, 6), 4)
        self.assertEqual(_cap_intro_motion_for_short_video(91, 6), 6)

    def test_successful_cleanup_preserves_billed_kling_clips(self):
        with tempfile.TemporaryDirectory() as directory:
            kling = Path(directory) / "kling.mp4"
            static = Path(directory) / "static.mp4"
            kling.write_bytes(b"kling")
            static.write_bytes(b"static")
            _cleanup_scene_clips([str(kling), str(static)], {0: "kling", 1: "static"})
            self.assertTrue(kling.exists())
            self.assertFalse(static.exists())

    def test_verified_chart_is_opaque_over_generated_panel_marks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart.png"
            chart = {
                "verified": True,
                "label": "KOSPI",
                "latest": 6747.95,
                "change_pct": 3.56,
                "source_date": "2026-07-21",
                "visual_theme": "factory_panel",
                "render_surface": {"width": 720, "height": 390},
                "points": [
                    {"date": f"2026-07-{day:02d}", "close": value}
                    for day, value in ((13, 6806), (14, 6856), (15, 7284), (20, 6516), (21, 6747))
                ],
            }
            self.assertTrue(render_market_chart(chart, str(path)))
            with Image.open(path).convert("RGBA") as rendered:
                self.assertEqual(rendered.getpixel((0, 0))[3], 255)


if __name__ == "__main__":
    unittest.main()

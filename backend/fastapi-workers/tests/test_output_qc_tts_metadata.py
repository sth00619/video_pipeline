from unittest.mock import patch

from app.utils.output_qc import build_output_qc_report


def test_tts_opening_falls_back_to_persisted_chunks_when_java_dto_was_lossy():
    tts_meta = {
        "voice_id": "dlKJ5VptCbYxal4doUO5",
        "chunks": [{"text": "어제까지만 해도 벼랑 끝이었습니다."}],
    }
    probe = {
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"},
            {"codec_type": "audio", "sample_rate": "44100", "channels": 2},
        ]
    }
    with patch("app.utils.output_qc._ffprobe", return_value=probe), patch(
        "app.utils.output_qc._leading_silence_seconds", return_value=0.2
    ), patch("app.utils.output_qc._intro_frame_difference", return_value=0.01), patch(
        "app.utils.output_qc.Path.exists", return_value=True
    ), patch("app.utils.output_qc.Path.rglob", return_value=[]):
        report = build_output_qc_report(
            job_id=999,
            output_path="final.mp4",
            audio_path="full.mp3",
            tts_meta=tts_meta,
            scenes=[{"style_profile": "editorial_comic_2d"}],
            expected_data_cards=0,
            rendered_data_cards=0,
            expected_market_charts=0,
            rendered_market_charts=0,
            planned_kling=1,
            actual_kling=1,
            fal_failures={},
        )

    opening = report["checks"]["tts_opening"]
    assert opening["passed"] is True
    assert opening["first_sentence_sent"].startswith("어제까지만")
    assert opening["metadata_provenance"] == "persisted_tts_chunks"


def test_motion_qc_samples_delivered_fal_window_instead_of_static_first_scene():
    probe = {
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"},
            {"codec_type": "audio", "sample_rate": "44100", "channels": 2},
        ],
        "format": {"duration": "57.0"},
    }
    motion_plan = {
        "video_duration_seconds": 57.0,
        "selected_scene_seconds": 14.5,
        "delivered_scene_indices": [3, 4, 7],
        "scene_windows": [
            {"index": 0, "start_seconds": 0.0, "end_seconds": 4.3},
            {"index": 3, "start_seconds": 14.2, "end_seconds": 18.8},
            {"index": 4, "start_seconds": 18.8, "end_seconds": 24.1},
            {"index": 7, "start_seconds": 34.4, "end_seconds": 38.8},
        ],
    }
    with patch("app.utils.output_qc._ffprobe", return_value=probe), patch(
        "app.utils.output_qc._leading_silence_seconds", return_value=0.2
    ), patch("app.utils.output_qc._frame_difference", return_value=0.01), patch(
        "app.utils.output_qc._intro_frame_difference", return_value=0.0
    ), patch("app.utils.output_qc.Path.exists", return_value=True), patch(
        "app.utils.output_qc.Path.rglob", return_value=[]
    ):
        report = build_output_qc_report(
            job_id=999,
            output_path="final.mp4",
            audio_path="full.mp3",
            tts_meta={"voice_id": "voice", "chunks": [{"text": "첫 문장"}]},
            scenes=[{"style_profile": "editorial_comic_2d"}],
            expected_data_cards=0,
            rendered_data_cards=0,
            expected_market_charts=0,
            rendered_market_charts=0,
            planned_kling=3,
            actual_kling=3,
            fal_failures={},
            kling_motion_plan=motion_plan,
        )

    assert report["checks"]["intro_motion_frame_diff"]["passed"] is True
    assert report["checks"]["intro_motion_frame_diff"]["delivered_scene_differences"][0]["index"] == 3
    assert report["checks"]["intro_motion_timing"]["passed"] is True
    assert report["checks"]["intro_motion_timing"]["motion_ratio"] == 0.2544

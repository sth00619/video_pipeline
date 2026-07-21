from unittest.mock import Mock, patch

from app.providers.real.video import KlingProvider


def test_fal_v26_image_to_video_uses_exact_schema(tmp_path):
    response = Mock(status_code=400, text="schema probe")
    response.json.return_value = {}
    with patch("app.providers.real.video.requests.post", return_value=response) as post:
        success, request_id = KlingProvider()._generate_fal_api(
            "subtle character gesture",
            str(tmp_path / "clip.mp4"),
            7,
            "not-a-real-key",
            "https://example.test/start.png?signature=secret",
        )

    assert not success
    assert request_id is None
    url = post.call_args.args[0]
    payload = post.call_args.kwargs["json"]
    assert url.endswith("fal-ai/kling-video/v2.6/pro/image-to-video")
    assert payload["start_image_url"].startswith("https://example.test/start.png")
    assert payload["duration"] == "5"
    assert payload["generate_audio"] is False
    assert "aspect_ratio" not in payload

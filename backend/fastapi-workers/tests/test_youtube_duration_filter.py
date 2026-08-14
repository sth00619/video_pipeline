import logging

import pytest

from app.providers.real import trending


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _QuotaRedis:
    def __init__(self, used: int) -> None:
        self.used = used

    def incr(self, key: str) -> int:  # noqa: ARG002
        self.used += 1
        return self.used

    def decr(self, key: str) -> int:  # noqa: ARG002
        self.used -= 1
        return self.used

    def expire(self, key: str, seconds: int) -> bool:  # noqa: ARG002
        return True


def _analyzer() -> trending.YouTubeTrendingAnalyzer:
    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer.base_url = "https://www.googleapis.com/youtube/v3"
    analyzer._redis = None
    return analyzer


def _video_item(video_id: str, duration: str) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": video_id,
            "channelTitle": "테스트 채널",
            "channelId": "channel-1",
            "publishedAt": "2026-08-14T00:00:00Z",
            "liveBroadcastContent": "none",
        },
        "statistics": {
            "viewCount": "10000",
            "likeCount": "100",
            "commentCount": "10",
        },
        "contentDetails": {"duration": duration},
    }


def _collect_duration_results(monkeypatch) -> list:
    video_durations = {
        "seconds-59": "PT59S",
        "seconds-239": "PT3M59S",
        "seconds-240": "PT4M",
        "seconds-300": "PT5M",
    }

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            return _Response(
                {"items": [{"id": {"videoId": video_id}} for video_id in video_durations]}
            )
        if url.endswith("/videos"):
            return _Response(
                {"items": [_video_item(video_id, duration) for video_id, duration in video_durations.items()]}
            )
        if url.endswith("/channels"):
            return _Response(
                {
                    "items": [
                        {
                            "id": "channel-1",
                            "statistics": {
                                "subscriberCount": "1000",
                                "viewCount": "100000",
                                "videoCount": "10",
                            },
                        }
                    ]
                }
            )
        raise AssertionError(f"예상하지 못한 YouTube API URL: {url}")

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    monkeypatch.setattr(trending, "_score_video", lambda video: (0.5, "A"))
    monkeypatch.setattr(trending, "_is_eligible_evidence_source", lambda video: True)
    monkeypatch.setattr(trending.YouTubeTrendingAnalyzer, "_attach_top_comments", lambda self, videos: None)

    return _analyzer()._collect_keyword_search(
        "KOSPI",
        "반도체",
        limit=10,
        recent_hours=168,
    )


def test_search_list_includes_video_duration_long(monkeypatch):
    captured_params: dict = {}

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        captured_params.update(params)
        return _Response({"items": []})

    monkeypatch.setattr(trending.requests, "get", _fake_get)

    result = _analyzer()._collect_keyword_search(
        "KOSPI",
        "반도체",
        limit=5,
        recent_hours=168,
    )

    assert result == []
    assert captured_params.get("videoDuration") == "long"


def test_results_under_four_minutes_are_dropped(monkeypatch):
    result = _collect_duration_results(monkeypatch)

    assert sorted(video.duration_seconds for video in result) == [240.0, 300.0]
    assert all(video.duration_seconds >= 240 for video in result)


def test_result_at_four_minutes_boundary_is_kept(monkeypatch):
    result = _collect_duration_results(monkeypatch)

    assert any(video.duration_seconds == 240 for video in result)


def test_search_quota_log_shows_actual_used_count(caplog, monkeypatch):
    monkeypatch.setattr(trending, "_quota_day_key", lambda: "2026-08-14")
    redis = _QuotaRedis(used=100)

    with caplog.at_level(logging.ERROR, logger=trending.__name__):
        result = trending._consume_search_quota(redis)

    assert result is False
    assert redis.used == 100
    assert "100/100 calls today — blocking." in caplog.text

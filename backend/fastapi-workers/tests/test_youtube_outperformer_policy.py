import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.providers.base import TrendingVideo
from app.providers.real import trending


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeRedis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.setex_calls: list[tuple[str, int, str]] = []

    def get(self, key: str):  # noqa: ANN201
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self.values[key] = value
        self.setex_calls.append((key, ttl, value))
        return True


@pytest.fixture(autouse=True)
def _fixed_policy(monkeypatch):
    monkeypatch.setattr(trending.config, "KEYWORD_MIN_SOURCE_VIEWS", 500)
    monkeypatch.setattr(trending.config, "KEYWORD_OUTPERFORMER_RECENT_MULTIPLE", 1.5)
    monkeypatch.setattr(trending.config, "KEYWORD_OUTPERFORMER_MIN_BASELINE_COUNT", 10)
    monkeypatch.setattr(trending.config, "KEYWORD_OUTPERFORMER_BASELINE_CAP_PER_REQ", 10)


@pytest.fixture
def video_factory():
    def _factory(**overrides) -> TrendingVideo:
        values = {
            "title": "성과 영상",
            "channel_title": "테스트 채널",
            "video_id": "video-1",
            "views": 15_000,
            "subscribers": 100_000,
            "channel_avg_views": 20_000,
            "published_at": "2026-08-17T00:00:00Z",
            "hours_since_publish": 24,
            "channel_id": "channel-1",
            "duration_seconds": 300,
        }
        values.update(overrides)
        return TrendingVideo(**values)

    return _factory


def _analyzer(redis_client=None) -> trending.YouTubeTrendingAnalyzer:
    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer.base_url = "https://www.googleapis.com/youtube/v3"
    analyzer._redis = redis_client
    return analyzer


def _baseline_video(
    video_id: str,
    *,
    duration: str = "PT5M",
    views: int = 1_000,
    live: str = "none",
    replay: bool = False,
) -> dict:
    item = {
        "id": video_id,
        "snippet": {"liveBroadcastContent": live},
        "statistics": {"viewCount": str(views)},
        "contentDetails": {"duration": duration},
    }
    if replay:
        item["liveStreamingDetails"] = {"actualStartTime": "2026-08-16T00:00:00Z"}
    return item


def _install_baseline_api(monkeypatch, video_items: list[dict]) -> list[str]:
    calls: list[str] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        calls.append(url.rsplit("/", 1)[-1])
        if url.endswith("/channels"):
            return _Response(
                {
                    "items": [
                        {
                            "contentDetails": {
                                "relatedPlaylists": {"uploads": "uploads-1"}
                            }
                        }
                    ]
                }
            )
        if url.endswith("/playlistItems"):
            return _Response(
                {
                    "items": [
                        {"contentDetails": {"videoId": item["id"]}}
                        for item in video_items
                    ]
                }
            )
        if url.endswith("/videos"):
            return _Response({"items": video_items})
        raise AssertionError(f"예상하지 못한 URL: {url}")

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    return calls


@pytest.mark.parametrize(
    ("subscribers", "expected_threshold"),
    [
        (1_000_000, 0.003),
        (999_999, 0.006),
        (300_000, 0.006),
        (299_999, 0.010),
        (50_000, 0.010),
        (49_999, 0.020),
    ],
)
def test_viewer_ratio_threshold_boundaries(subscribers, expected_threshold):
    assert trending._viewer_ratio_threshold(subscribers) == expected_threshold


def test_recent_average_path_when_sample_ge_10(video_factory):
    video = video_factory(
        views=15_000,
        channel_recent_avg_views=10_000,
        channel_recent_sample_size=10,
    )

    passed, basis = trending._is_high_response_video(video)

    assert passed is True
    assert basis == "recent_average_1_5x"


def test_tiered_ratio_path_when_sample_lt_10(video_factory):
    video = video_factory(
        views=1_000,
        subscribers=100_000,
        channel_recent_avg_views=10_000,
        channel_recent_sample_size=9,
    )

    passed, basis = trending._is_high_response_video(video)

    assert passed is True
    assert basis == "tiered_ratio"


def test_recent_average_boundary_pass_and_fail(video_factory):
    baseline = {
        "channel_recent_avg_views": 10_000,
        "channel_recent_sample_size": 10,
        "subscribers": 1_000_000,
    }

    assert trending._is_high_response_video(video_factory(views=14_999, **baseline))[0] is False
    assert trending._is_high_response_video(video_factory(views=15_000, **baseline))[0] is True


def test_minimum_views_blocks_regardless_of_path(video_factory):
    video = video_factory(
        views=499,
        subscribers=1_000,
        channel_recent_avg_views=100,
        channel_recent_sample_size=10,
    )

    passed, basis = trending._is_high_response_video(video)

    assert passed is False
    assert basis == "minimum_views"


def test_evidence_window_includes_168_hours_and_excludes_older(video_factory):
    baseline = {
        "views": 15_000,
        "channel_recent_avg_views": 10_000,
        "channel_recent_sample_size": 10,
    }

    assert trending._is_eligible_evidence_source(
        video_factory(hours_since_publish=168, **baseline)
    ) is True
    assert trending._is_eligible_evidence_source(
        video_factory(hours_since_publish=168.01, **baseline)
    ) is False


def test_live_and_replay_videos_are_excluded_from_baseline(monkeypatch):
    items = [
        _baseline_video("live", views=10_000, live="live"),
        _baseline_video("upcoming", views=20_000, live="upcoming"),
        _baseline_video("replay", views=30_000, replay=True),
        _baseline_video("normal", views=4_000),
    ]
    _install_baseline_api(monkeypatch, items)
    monkeypatch.setattr(trending, "_consume_quota", lambda redis, units, operation: True)

    average, sample_size = trending._fetch_channel_baseline(_analyzer(), "channel-1")

    assert (average, sample_size) == (4_000, 1)


def test_duration_boundary_in_baseline_calculation(monkeypatch):
    items = [
        _baseline_video("seconds-239", duration="PT3M59S", views=2_390),
        _baseline_video("seconds-240", duration="PT4M", views=2_400),
    ]
    _install_baseline_api(monkeypatch, items)
    monkeypatch.setattr(trending, "_consume_quota", lambda redis, units, operation: True)

    average, sample_size = trending._fetch_channel_baseline(_analyzer(), "channel-1")

    assert (average, sample_size) == (2_400, 1)


def test_large_channel_ranking_bypasses_performance_filter(monkeypatch):
    published_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace(
        "+00:00", "Z"
    )

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            items = [{"id": {"videoId": "large-1"}}] if params["videoDuration"] == "long" else []
            return _Response({"items": items})
        if url.endswith("/videos"):
            return _Response(
                {
                    "items": [
                        {
                            "id": "large-1",
                            "snippet": {
                                "title": "최근 포맷",
                                "channelTitle": "대형 채널",
                                "channelId": "channel-large",
                                "publishedAt": published_at,
                                "liveBroadcastContent": "none",
                            },
                            "statistics": {"viewCount": "100"},
                            "contentDetails": {"duration": "PT5M"},
                        }
                    ]
                }
            )
        if url.endswith("/channels"):
            return _Response(
                {
                    "items": [
                        {
                            "id": "channel-large",
                            "statistics": {
                                "subscriberCount": "100000",
                                "viewCount": "1000000",
                                "videoCount": "100",
                            },
                        }
                    ]
                }
            )
        raise AssertionError(f"예상하지 못한 URL: {url}")

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    monkeypatch.setattr(
        trending,
        "_fetch_channel_baseline",
        lambda analyzer, channel_id: pytest.fail("large_channel은 baseline을 조회하면 안 됩니다."),
    )
    monkeypatch.setattr(
        trending,
        "_is_high_response_video",
        lambda video: pytest.fail("large_channel은 성과 판정을 호출하면 안 됩니다."),
    )

    result = _analyzer()._collect_keyword_search(
        "KOSPI",
        "반도체",
        limit=5,
        recent_hours=168,
        ranking="large_channel",
        min_subscribers=50_000,
    )

    assert [video.video_id for video in result] == ["large-1"]


def test_baseline_cache_hit_skips_api_calls(monkeypatch):
    redis = _FakeRedis(
        {
            "youtube:channel-baseline:v1:channel-1": json.dumps(
                {"average_views": 12_345, "sample_size": 20}
            )
        }
    )
    monkeypatch.setattr(
        trending.requests,
        "get",
        lambda *args, **kwargs: pytest.fail("캐시 적중 시 API를 호출하면 안 됩니다."),
    )

    result = trending._fetch_channel_baseline(_analyzer(redis), "channel-1")

    assert result == (12_345, 20)
    assert redis.setex_calls == []


def test_baseline_cache_miss_records_three_shared_units(monkeypatch, caplog):
    redis = _FakeRedis()
    calls = _install_baseline_api(monkeypatch, [_baseline_video("normal", views=5_000)])
    quota_operations: list[tuple[int, str]] = []

    def _record_quota(redis_client, units: int, operation: str):  # noqa: ARG001
        quota_operations.append((units, operation))
        return True

    monkeypatch.setattr(trending, "_consume_quota", _record_quota)

    with caplog.at_level(logging.INFO, logger=trending.__name__):
        result = trending._fetch_channel_baseline(_analyzer(redis), "channel-1")

    assert result == (5_000, 1)
    assert calls == ["channels", "playlistItems", "videos"]
    assert quota_operations == [
        (1, "channels.list"),
        (1, "playlistItems.list"),
        (1, "videos.list"),
    ]
    assert "source=api" in caplog.text
    assert "shared_units=3" in caplog.text
    assert redis.setex_calls[0][1] == 21_600


def test_baseline_cache_hit_log_shows_zero_shared_units(caplog):
    redis = _FakeRedis(
        {
            "youtube:channel-baseline:v1:channel-1": json.dumps(
                {"average_views": 7_000, "sample_size": 12}
            )
        }
    )

    with caplog.at_level(logging.INFO, logger=trending.__name__):
        trending._fetch_channel_baseline(_analyzer(redis), "channel-1")

    assert "source=cache" in caplog.text
    assert "playlist_calls=0 videos_calls=0 shared_units=0" in caplog.text

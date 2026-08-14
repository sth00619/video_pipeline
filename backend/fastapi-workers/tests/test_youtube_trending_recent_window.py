from datetime import datetime, timezone

import pytest

from app.providers.real import trending


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (None, 168),
        (2, 2),
        (-5, 1),
        (0, 1),
        (168, 168),
        (999, 168),
    ],
)
def test_normalize_recent_hours_contract(requested, expected):
    assert trending._normalize_recent_hours(requested) == expected


class _RecordingRedis:
    def __init__(self):
        self.read_keys = []
        self.write_keys = []

    def get(self, key):
        self.read_keys.append(key)
        return None

    def setex(self, key, ttl, value):
        self.write_keys.append(key)


def test_collect_normalizes_default_before_search_and_cache(monkeypatch):
    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer._redis = _RecordingRedis()
    captured = {}

    def _fake_search(category, seed, limit, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(analyzer, "_collect_keyword_search", _fake_search)

    assert analyzer.collect(category="KOSPI", seed="반도체 전망", recent_hours=None) == []
    assert captured["recent_hours"] == 168
    assert analyzer._redis.read_keys
    assert analyzer._redis.write_keys
    assert all("recent=168" in key for key in analyzer._redis.read_keys + analyzer._redis.write_keys)


class _SearchResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"items": []}


def test_keyword_search_builds_a_seven_day_published_after(monkeypatch):
    captured = {}

    def _fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _SearchResponse()

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer.base_url = "https://www.googleapis.com/youtube/v3"
    analyzer._redis = None

    before = datetime.now(timezone.utc)
    assert analyzer._collect_keyword_search("KOSPI", "반도체 전망", 10, recent_hours=168) == []
    after = datetime.now(timezone.utc)

    published_after = datetime.fromisoformat(captured["params"]["publishedAfter"].replace("Z", "+00:00"))
    assert 168 * 3600 <= (after - published_after).total_seconds() <= 168 * 3600 + 2
    assert 168 * 3600 - 2 <= (before - published_after).total_seconds() <= 168 * 3600
    assert captured["params"]["q"] == "반도체 전망"
    assert captured["url"].endswith("/search")

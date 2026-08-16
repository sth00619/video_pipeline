import inspect
import json
import logging

import pytest

from app.providers.real import trending


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.writes: list[tuple[str, int, str]] = []

    def get(self, key: str):  # noqa: ANN201
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.writes.append((key, ttl, value))


def _analyzer(redis_client=None) -> trending.YouTubeTrendingAnalyzer:  # noqa: ANN001
    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer.base_url = "https://www.googleapis.com/youtube/v3"
    analyzer._redis = redis_client
    return analyzer


def _channel_item(channel_id: str, *, hidden: bool = False) -> dict:
    statistics = {
        "hiddenSubscriberCount": hidden,
        "viewCount": "200000",
        "videoCount": "120",
    }
    if not hidden:
        statistics["subscriberCount"] = "15000"
    return {
        "id": channel_id,
        "snippet": {"title": f"채널 {channel_id}"},
        "statistics": statistics,
        "contentDetails": {"relatedPlaylists": {}},
    }


def test_static_benchmark_fallback_and_rejected_ids_are_absent():
    source = inspect.getsource(trending)

    assert not hasattr(trending.YouTubeTrendingAnalyzer, "BENCHMARK_CHANNELS")
    assert "UC86s17Zc-V7vP7zL6Z-Yd4g" not in source
    assert "UCpAyogfL8-YzmKf3-wTfEBg" not in source


def test_empty_channel_ids_return_without_youtube_request(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(trending.requests, "get", lambda *args, **kwargs: requested.append(args[0]))

    assert _analyzer().get_channel_benchmarks([]) == []
    assert _analyzer().get_channel_benchmarks(None) == []
    assert requested == []


def test_missing_channel_returns_channel_not_found_row(monkeypatch):
    monkeypatch.setattr(trending.requests, "get", lambda *args, **kwargs: _Response({"items": []}))

    result = _analyzer().get_channel_benchmarks(["UCmissing"])

    assert [row["channel_id"] for row in result] == ["UCmissing"]
    assert result[0]["status"] == "error"
    assert result[0]["error_code"] == "channel_not_found"
    assert result[0]["subscriber_count"] is None
    assert result[0]["subscriber_count_available"] is False


@pytest.mark.parametrize("status_code", [403, 500])
def test_channel_http_error_returns_youtube_api_error_row(monkeypatch, status_code):
    monkeypatch.setattr(
        trending.requests,
        "get",
        lambda *args, **kwargs: _Response({"error": "blocked"}, status_code),
    )

    result = _analyzer().get_channel_benchmarks(["UCfailure"])

    assert result[0]["error_code"] == "youtube_api_error"
    assert result[0]["subscriber_count"] is None
    assert str(status_code) in result[0]["error_message"]


def test_network_exception_returns_sanitized_fetch_failed_row(monkeypatch, caplog):
    def _fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise ConnectionError("https://youtube.invalid?key=private-api-key")

    monkeypatch.setattr(trending.requests, "get", _fail)

    with caplog.at_level(logging.WARNING):
        result = _analyzer().get_channel_benchmarks(["UCnetwork"])

    assert result[0]["error_code"] == "fetch_failed"
    assert result[0]["subscriber_count"] is None
    assert "private-api-key" not in result[0]["error_message"]
    assert "private-api-key" not in caplog.text


def test_failure_rows_preserve_deduplicated_input_order(monkeypatch):
    monkeypatch.setattr(trending.requests, "get", lambda *args, **kwargs: _Response({"items": []}))

    result = _analyzer().get_channel_benchmarks([" UCsecond ", "UCfirst", "UCsecond", ""])

    assert [row["channel_id"] for row in result] == ["UCsecond", "UCfirst"]
    assert all(row["error_code"] == "channel_not_found" for row in result)


def test_hidden_subscriber_count_is_never_rendered_as_zero(monkeypatch):
    monkeypatch.setattr(
        trending.requests,
        "get",
        lambda *args, **kwargs: _Response({"items": [_channel_item("UChidden", hidden=True)]}),
    )

    row = _analyzer().get_channel_benchmarks(["UChidden"])[0]

    assert row["status"] == "ok"
    assert row["subscriber_count"] is None
    assert row["subscriber_count_available"] is False
    assert row["hidden_subscriber_count"] is True


def test_success_row_exposes_explicit_integrity_fields(monkeypatch):
    monkeypatch.setattr(
        trending.requests,
        "get",
        lambda *args, **kwargs: _Response({"items": [_channel_item("UCvalid")]}),
    )

    row = _analyzer().get_channel_benchmarks(["UCvalid"])[0]

    assert row["status"] == "ok"
    assert row["error_code"] is None
    assert row["subscriber_count"] == 15000
    assert row["subscriber_count_available"] is True
    assert row["hidden_subscriber_count"] is False


def test_v2_cache_key_preserves_order_without_raw_ids_or_api_key():
    first = trending._benchmark_cache_key(["UCfirst", "UCsecond"])
    reversed_order = trending._benchmark_cache_key(["UCsecond", "UCfirst"])

    assert first.startswith("youtube:benchmark:v2:")
    assert first != reversed_order
    assert "UCfirst" not in first
    assert "test-key" not in first


def test_channel_not_found_uses_short_negative_cache(monkeypatch):
    redis_client = _Redis()
    monkeypatch.setattr(trending.requests, "get", lambda *args, **kwargs: _Response({"items": []}))

    result = _analyzer(redis_client).get_channel_benchmarks(["UCmissing"])

    assert result[0]["error_code"] == "channel_not_found"
    assert len(redis_client.writes) == 1
    key, ttl, payload = redis_client.writes[0]
    assert key.startswith("youtube:benchmark:v2:")
    assert ttl == 10 * 60
    assert json.loads(payload)[0]["subscriber_count"] is None

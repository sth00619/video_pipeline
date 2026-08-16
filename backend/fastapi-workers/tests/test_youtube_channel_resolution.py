import logging

import pytest

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


def _analyzer() -> trending.YouTubeTrendingAnalyzer:
    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer.base_url = "https://www.googleapis.com/youtube/v3"
    analyzer._redis = None
    return analyzer


def _resolved_item(channel_id: str = "UChlv4GSd7OQl3js-jkLOnFA") -> dict:
    return {
        "id": channel_id,
        "snippet": {
            "title": "삼프로TV 3PROTV",
            "customUrl": "@3protv",
            "description": "경제 콘텐츠",
            "thumbnails": {"high": {"url": "https://img.example/3pro.jpg"}},
        },
        "statistics": {
            "subscriberCount": "2900000",
            "viewCount": "1000000000",
            "videoCount": "20845",
            "hiddenSubscriberCount": False,
        },
    }


def test_channel_id_uses_channels_list_id_filter(monkeypatch):
    captured: list[dict] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        captured.append(params)
        return _Response({"items": [_resolved_item("UCdirect")]})

    monkeypatch.setattr(trending.requests, "get", _fake_get)

    result = _analyzer().resolve_channel("UCdirect")

    assert result["channel_id"] == "UCdirect"
    assert captured[0]["id"] == "UCdirect"
    assert "forHandle" not in captured[0]


def test_handle_uses_channels_list_for_handle_filter(monkeypatch):
    captured: list[dict] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        captured.append(params)
        return _Response({"items": [_resolved_item()]})

    monkeypatch.setattr(trending.requests, "get", _fake_get)

    result = _analyzer().resolve_channel("@3protv")

    assert result["channel_id"] == "UChlv4GSd7OQl3js-jkLOnFA"
    assert captured[0]["forHandle"] == "@3protv"
    assert "id" not in captured[0]


@pytest.mark.parametrize(
    ("channel_ref", "expected"),
    [
        ("https://www.youtube.com/@3protv", {"forHandle": "@3protv"}),
        ("youtube.com/channel/UCdirect", {"id": "UCdirect"}),
    ],
)
def test_full_youtube_channel_urls_are_normalized(channel_ref, expected):
    assert trending._channel_lookup_params(channel_ref) == expected


def test_id_and_handle_resolution_never_uses_search_bucket(monkeypatch):
    shared_operations: list[str] = []

    def _shared(redis_client, units: int, operation: str):  # noqa: ANN001, ARG001
        shared_operations.append(operation)
        return True

    monkeypatch.setattr(trending, "_consume_quota", _shared)
    monkeypatch.setattr(
        trending,
        "_consume_search_quota",
        lambda redis_client: (_ for _ in ()).throw(AssertionError("검색 버킷 사용 금지")),
    )
    monkeypatch.setattr(
        trending.requests,
        "get",
        lambda *args, **kwargs: _Response({"items": [_resolved_item()]}),
    )

    assert _analyzer().resolve_channel("@3protv") is not None
    assert shared_operations == ["channels.list"]


def test_name_search_uses_dedicated_bucket_and_channel_search_contract(monkeypatch):
    search_calls: list[object] = []
    captured: list[dict] = []
    resolved_ids: list[str] = []
    analyzer = _analyzer()

    monkeypatch.setattr(trending, "_consume_search_quota", lambda redis_client: search_calls.append(redis_client) or True)

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        captured.append(params)
        return _Response({"items": [{"id": {"channelId": "UCcandidate"}}]})

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    monkeypatch.setattr(
        analyzer,
        "resolve_channel_ids",
        lambda channel_ids: resolved_ids.extend(channel_ids) or [{"channel_id": channel_ids[0]}],
    )

    result = analyzer.search_channel_candidates("삼프로TV", limit=10)

    assert search_calls == [analyzer._redis]
    assert captured[0]["type"] == "channel"
    assert captured[0]["maxResults"] == 3
    assert captured[0]["regionCode"] == "KR"
    assert captured[0]["relevanceLanguage"] == "ko"
    assert resolved_ids == ["UCcandidate"]
    assert result == [{"channel_id": "UCcandidate"}]


def test_search_candidates_are_enriched_with_channels_list(monkeypatch):
    requested_urls: list[str] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        requested_urls.append(url)
        if url.endswith("/search"):
            return _Response({"items": [{"id": {"channelId": "UChlv4GSd7OQl3js-jkLOnFA"}}]})
        return _Response({"items": [_resolved_item()]})

    monkeypatch.setattr(trending.requests, "get", _fake_get)

    result = _analyzer().search_channel_candidates("삼프로TV")

    assert requested_urls == [
        "https://www.googleapis.com/youtube/v3/search",
        "https://www.googleapis.com/youtube/v3/channels",
    ]
    assert result[0]["channel_id"] == "UChlv4GSd7OQl3js-jkLOnFA"
    assert result[0]["title"] == "삼프로TV 3PROTV"
    assert result[0]["subscriber_count"] == 2900000


def test_search_quota_exhaustion_stops_before_http(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(trending, "_consume_search_quota", lambda redis_client: False)
    monkeypatch.setattr(trending.requests, "get", lambda url, **kwargs: requested.append(url))

    with pytest.raises(RuntimeError, match="검색 한도"):
        _analyzer().search_channel_candidates("삼프로TV")

    assert requested == []


def test_search_failure_does_not_expose_api_key(monkeypatch, caplog):
    def _fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("request failed: key=test-key")

    monkeypatch.setattr(trending.requests, "get", _fail)

    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError) as exc_info:
        _analyzer().search_channel_candidates("삼프로TV")

    assert "test-key" not in str(exc_info.value)
    assert "test-key" not in caplog.text


def test_invalid_non_youtube_reference_is_rejected():
    with pytest.raises(ValueError, match="채널 ID 또는 @handle"):
        trending._channel_lookup_params("삼프로TV")

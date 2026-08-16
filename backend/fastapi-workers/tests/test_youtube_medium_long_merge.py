from app.providers.real import trending


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _analyzer() -> trending.YouTubeTrendingAnalyzer:
    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer.base_url = "https://www.googleapis.com/youtube/v3"
    analyzer._redis = None
    return analyzer


def _search_items(*video_ids: str) -> _Response:
    return _Response({"items": [{"id": {"videoId": video_id}} for video_id in video_ids]})


def _video_item(video_id: str, duration: str = "PT5M") -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": video_id,
            "channelTitle": "테스트 채널",
            "channelId": "channel-1",
            "publishedAt": "2026-08-14T00:00:00Z",
            "liveBroadcastContent": "none",
        },
        "statistics": {"viewCount": "10000", "likeCount": "100", "commentCount": "10"},
        "contentDetails": {"duration": duration},
    }


def _channel_response() -> _Response:
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


def _allow_results(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(trending, "_score_video", lambda video: (0.5, "A"))
    monkeypatch.setattr(trending, "_is_eligible_evidence_source", lambda video: True)
    monkeypatch.setattr(
        trending.YouTubeTrendingAnalyzer,
        "_attach_top_comments",
        lambda self, videos: None,
    )


def test_both_medium_and_long_calls_are_made(monkeypatch):
    captured_durations: list[str] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            captured_durations.append(params.get("videoDuration", ""))
        return _Response({"items": []})

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    monkeypatch.setattr(trending, "_consume_search_quota", lambda redis_client: True)

    result = _analyzer()._collect_keyword_search("KOSPI", "반도체", limit=5, recent_hours=168)

    assert result == []
    assert captured_durations == ["long", "medium"]


def test_duplicate_video_ids_are_deduped(monkeypatch):
    captured_video_ids: list[str] = []
    durations = {"vid_A": "PT25M", "vid_L": "PT30M", "vid_M": "PT10M"}

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            if params.get("videoDuration") == "long":
                return _search_items("vid_A", "vid_L")
            return _search_items("vid_A", "vid_M")
        if url.endswith("/videos"):
            captured_video_ids.extend(params["id"].split(","))
            return _Response(
                {"items": [_video_item(video_id, durations[video_id]) for video_id in captured_video_ids]}
            )
        if url.endswith("/channels"):
            return _channel_response()
        raise AssertionError(f"예상하지 못한 YouTube API URL: {url}")

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    _allow_results(monkeypatch)

    result = _analyzer()._collect_keyword_search("KOSPI", "반도체", limit=5, recent_hours=168)

    assert captured_video_ids == ["vid_A", "vid_L", "vid_M"]
    assert captured_video_ids.count("vid_A") == 1
    assert [video.video_id for video in result] == ["vid_A", "vid_L", "vid_M"]


def test_medium_search_failure_returns_long_only(monkeypatch):
    captured_durations: list[str] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            duration = params.get("videoDuration", "")
            captured_durations.append(duration)
            if duration == "medium":
                raise ConnectionError("medium call failed")
            return _search_items("vid_long")
        if url.endswith("/videos"):
            return _Response({"items": [_video_item("vid_long", "PT25M")]})
        if url.endswith("/channels"):
            return _channel_response()
        raise AssertionError(f"예상하지 못한 YouTube API URL: {url}")

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    _allow_results(monkeypatch)

    result = _analyzer()._collect_keyword_search("KOSPI", "반도체", limit=5, recent_hours=168)

    assert captured_durations == ["long", "medium"]
    assert [video.video_id for video in result] == ["vid_long"]


def test_medium_quota_exhausted_returns_long_only(monkeypatch):
    quota_results = iter([True, False])
    captured_durations: list[str] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            captured_durations.append(params.get("videoDuration", ""))
            return _search_items("vid_long")
        if url.endswith("/videos"):
            return _Response({"items": [_video_item("vid_long", "PT25M")]})
        if url.endswith("/channels"):
            return _channel_response()
        raise AssertionError(f"예상하지 못한 YouTube API URL: {url}")

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    monkeypatch.setattr(trending, "_consume_search_quota", lambda redis_client: next(quota_results))
    _allow_results(monkeypatch)

    result = _analyzer()._collect_keyword_search("KOSPI", "반도체", limit=5, recent_hours=168)

    assert captured_durations == ["long"]
    assert [video.video_id for video in result] == ["vid_long"]


def test_240s_filter_is_applied_after_merge(monkeypatch):
    durations = {"vid_long_short": "PT3M", "vid_medium_short": "PT3M20S"}

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            video_id = "vid_long_short" if params.get("videoDuration") == "long" else "vid_medium_short"
            return _search_items(video_id)
        if url.endswith("/videos"):
            ids = params["id"].split(",")
            return _Response({"items": [_video_item(video_id, durations[video_id]) for video_id in ids]})
        if url.endswith("/channels"):
            return _channel_response()
        raise AssertionError(f"예상하지 못한 YouTube API URL: {url}")

    monkeypatch.setattr(trending.requests, "get", _fake_get)
    _allow_results(monkeypatch)

    result = _analyzer()._collect_keyword_search("KOSPI", "반도체", limit=5, recent_hours=168)

    assert result == []


def test_long_call_still_uses_video_duration_long(monkeypatch):
    captured_durations: list[str] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            captured_durations.append(params.get("videoDuration", ""))
        return _Response({"items": []})

    monkeypatch.setattr(trending.requests, "get", _fake_get)

    _analyzer()._collect_keyword_search("KOSPI", "반도체", limit=5, recent_hours=168)

    assert "long" in captured_durations

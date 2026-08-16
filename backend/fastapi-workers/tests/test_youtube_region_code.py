from app.providers.real import trending


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"items": []}


def _analyzer() -> trending.YouTubeTrendingAnalyzer:
    analyzer = trending.YouTubeTrendingAnalyzer.__new__(trending.YouTubeTrendingAnalyzer)
    analyzer.api_key = "test-key"
    analyzer.base_url = "https://www.googleapis.com/youtube/v3"
    analyzer._redis = None
    return analyzer


def test_region_code_kr_is_applied_to_both_long_and_medium_calls(monkeypatch):
    captured: list[tuple[str | None, str | None, str | None]] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            captured.append(
                (
                    params.get("videoDuration"),
                    params.get("regionCode"),
                    params.get("relevanceLanguage"),
                )
            )
        return _Response()

    monkeypatch.setattr(trending.requests, "get", _fake_get)

    result = _analyzer()._collect_keyword_search("KOSPI", "삼성전자", limit=5, recent_hours=168)

    assert result == []
    assert captured == [("long", "KR", "ko"), ("medium", "KR", "ko")]


def test_us_stock_region_contract_is_preserved_for_both_calls(monkeypatch):
    captured: list[tuple[str | None, str | None, str | None]] = []

    def _fake_get(url: str, params: dict, timeout: int):  # noqa: ARG001
        if url.endswith("/search"):
            captured.append(
                (
                    params.get("videoDuration"),
                    params.get("regionCode"),
                    params.get("relevanceLanguage"),
                )
            )
        return _Response()

    monkeypatch.setattr(trending.requests, "get", _fake_get)

    result = _analyzer()._collect_keyword_search(
        "US_STOCKS",
        "Nvidia earnings",
        limit=5,
        recent_hours=168,
    )

    assert result == []
    assert captured == [("long", "US", "en"), ("medium", "US", "en")]

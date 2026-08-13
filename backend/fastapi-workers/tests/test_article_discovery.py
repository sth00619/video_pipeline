import pytest

from app.services.article_discovery import ArticleDiscoveryService, ArticleDiscoveryUnavailable


def test_discovery_falls_back_to_google_rss_when_naver_is_not_configured(monkeypatch):
    """P3 정책: NAVER 미구성은 Google RSS fallback 진입 조건이다. 예외가 아니다.
    근거: bf9b814 — _discover_google_rss fallback 추가.
    """
    monkeypatch.setattr("app.services.article_discovery.naver_api_hub_configured", lambda: False)

    rss_called_with: list[str] = []

    def _fake_rss(self, query: str, terms, limit: int):  # noqa: ANN001
        rss_called_with.append(query)
        return []

    monkeypatch.setattr(ArticleDiscoveryService, "_discover_google_rss", _fake_rss)

    result = ArticleDiscoveryService().discover("반도체 관세", ["반도체", "관세"])

    assert rss_called_with, "NAVER 미구성 시 _discover_google_rss가 호출되어야 한다"
    assert rss_called_with[0] == "반도체 관세"
    assert isinstance(result, list)


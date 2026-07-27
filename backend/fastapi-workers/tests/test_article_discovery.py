import pytest

from app.services.article_discovery import ArticleDiscoveryService, ArticleDiscoveryUnavailable


def test_discovery_requires_configured_public_search_provider(monkeypatch):
    monkeypatch.setattr("app.services.article_discovery.naver_api_hub_configured", lambda: False)
    with pytest.raises(ArticleDiscoveryUnavailable):
        ArticleDiscoveryService().discover("반도체 관세", ["반도체", "관세"])


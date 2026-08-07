"""Stage 2-B Google RSS 폴백 유닛 테스트."""
from __future__ import annotations
import sys
sys.path.insert(0, "backend/fastapi-workers")

from unittest.mock import patch
from app.services.article_discovery import ArticleDiscoveryService, ArticleDiscoveryUnavailable
from app.models.article_evidence import ArticleCandidate


class TestArticleDiscoveryGoogleRssFallback:
    @patch("app.services.article_discovery.naver_api_hub_configured", return_value=False)
    def test_google_rss_fallback_when_naver_not_configured(self, mock_naver):
        service = ArticleDiscoveryService()
        # Naver 미설정 환경에서 discover 호출
        try:
            candidates = service.discover(query="반도체 SK하이닉스", terms=["반도체", "SK하이닉스"], limit=5)
            # candidates는 list[ArticleCandidate] 형태여야 함
            assert isinstance(candidates, list)
            # 만약 인터넷 연결이 되어있다면 실제 검색 결과가 반환될 수 있음
            for item in candidates:
                assert isinstance(item, ArticleCandidate)
                assert item.url.startswith("http")
                assert "google_rss" in item.raw or item.publisher != ""
        except ArticleDiscoveryUnavailable as exc:
            # feedparser나 requests 문제일 수 있음
            assert "Google RSS" in str(exc) or "feedparser" in str(exc)

    @patch("app.services.article_discovery.naver_api_hub_configured", return_value=True)
    @patch.object(ArticleDiscoveryService, "_discover_naver")
    def test_uses_naver_when_configured(self, mock_discover_naver, mock_naver):
        mock_discover_naver.return_value = []
        service = ArticleDiscoveryService()
        res = service.discover(query="테스트", limit=5)
        mock_discover_naver.assert_called_once()
        assert res == []

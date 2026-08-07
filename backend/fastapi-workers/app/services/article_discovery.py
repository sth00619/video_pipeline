"""Search public news candidates without scraping or bypassing access controls."""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime
from typing import Iterable

from app.models.article_evidence import ArticleCandidate
from app import runtime_config
from app.services.naver_api_hub import (
    NaverApiHubClient,
    NaverApiHubUnavailable,
    naver_api_hub_configured,
)
from app.services.article.source_policy import publisher_for_url

logger = logging.getLogger(__name__)


class ArticleDiscoveryUnavailable(RuntimeError):
    """Raised when no configured public-news search provider is available."""


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


class ArticleDiscoveryService:
    """NAVER API HUB 및 Google RSS 뉴스 검색 결과를 기사 후보로 변환한다."""

    def discover(self, query: str, terms: Iterable[str] = (), limit: int = 10) -> list[ArticleCandidate]:
        query = _clean(query)
        if not query:
            return []
        limit = max(1, min(int(limit), 30))
        
        if naver_api_hub_configured():
            results = self._discover_naver(query, terms, limit)
        else:
            results = self._discover_google_rss(query, terms, limit)
            
        return sorted(results, key=lambda item: (-item.score, item.title))

    def _discover_naver(self, query: str, terms: Iterable[str], limit: int) -> list[ArticleCandidate]:
        try:
            payload = NaverApiHubClient().search_news(query, display=limit, sort="date")
        except NaverApiHubUnavailable as exc:
            raise ArticleDiscoveryUnavailable(str(exc)) from exc
        tokens = [term.lower() for term in terms if _clean(term)] or [query.lower()]
        results: list[ArticleCandidate] = []
        for item in payload.get("items", []):
            title = _clean(item.get("title", ""))
            summary = _clean(item.get("description", ""))
            url = str(item.get("originallink") or item.get("link") or "").strip()
            if not url.startswith(("https://", "http://")):
                continue
            rule = publisher_for_url(url)
            if bool(runtime_config.value("article_allowed_publishers_only")) and rule is None:
                continue
            corpus = f"{title} {summary}".lower()
            matched = [term for term in tokens if term in corpus]
            score = round((len(matched) / max(len(tokens), 1)) * 100 + min(len(title), 80) / 100, 3)
            published = item.get("pubDate")
            try:
                published = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %z").date().isoformat()
            except (TypeError, ValueError):
                published = None
            results.append(ArticleCandidate(
                title=title,
                url=url,
                publisher=rule.name if rule else "",
                published_at=published,
                summary=summary,
                score=score,
                matched_terms=matched,
                raw={"naver_link": item.get("link", "")},
            ))
        return results

    def _discover_google_rss(self, query: str, terms: Iterable[str], limit: int) -> list[ArticleCandidate]:
        """Google News RSS 폴백. feedparser는 lazy import (Naver 환경에서 미설치 허용)."""
        from urllib.parse import quote
        try:
            import feedparser  # type: ignore[import]
        except ImportError as exc:
            raise ArticleDiscoveryUnavailable(
                f"Google RSS 폴백에 feedparser 패키지가 없습니다: {exc}"
            ) from exc
        rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(rss_url)
        tokens = [term.lower() for term in terms if _clean(term)] or [query.lower()]
        results: list[ArticleCandidate] = []
        for entry in feed.entries[:limit]:
            title = _clean(entry.get("title", ""))
            url = str(entry.get("link", "") or "").strip()
            source_info = getattr(entry, "source", {}) or {}
            source_url = str(source_info.get("href", "") or "").strip()
            if not url.startswith(("https://", "http://")):
                continue

            rule = publisher_for_url(source_url) if source_url else None
            if not rule:
                rule = publisher_for_url(url)

            if bool(runtime_config.value("article_allowed_publishers_only")) and rule is None:
                continue

            corpus = f"{title} {summary}".lower() if 'summary' in locals() else title.lower()
            summary = _clean(entry.get("summary", ""))
            corpus = f"{title} {summary}".lower()
            matched = [term for term in tokens if term in corpus]
            score = round((len(matched) / max(len(tokens), 1)) * 100 + min(len(title), 80) / 100, 3)

            # pubDate 파싱
            published = None
            pub_parsed = getattr(entry, "published_parsed", None)
            if pub_parsed:
                try:
                    published = datetime(*pub_parsed[:3]).date().isoformat()
                except Exception:
                    published = None

            results.append(ArticleCandidate(
                title=title,
                url=url,
                publisher=rule.name if rule else str(source_info.get("title", "") or ""),
                published_at=published,
                summary=summary,
                score=score,
                matched_terms=matched,
                raw={"google_rss": True, "google_link": url, "source_href": source_url},
            ))
        return results

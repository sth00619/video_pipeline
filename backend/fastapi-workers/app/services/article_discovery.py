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
    """NAVER API HUB 뉴스 검색 결과를 기사 후보로 변환한다."""

    def discover(self, query: str, terms: Iterable[str] = (), limit: int = 10) -> list[ArticleCandidate]:
        if not naver_api_hub_configured():
            raise ArticleDiscoveryUnavailable("NAVER API HUB 뉴스 검색이 설정되지 않았습니다")
        query = _clean(query)
        if not query:
            return []
        limit = max(1, min(int(limit), 30))
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
            # Search result links may point to a portal redirect.  In Phase 1
            # do not guess a Korean publisher from it; evidence simply stays
            # unavailable until a reviewed original URL is found.
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
        return sorted(results, key=lambda item: (-item.score, item.title))

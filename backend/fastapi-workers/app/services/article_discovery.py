"""Search public news candidates without scraping or bypassing access controls."""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime
from typing import Iterable

import httpx

from app.config import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
from app.models.article_evidence import ArticleCandidate
from app import runtime_config
from app.services.article.source_policy import publisher_for_url

logger = logging.getLogger(__name__)


class ArticleDiscoveryUnavailable(RuntimeError):
    """Raised when no configured public-news search provider is available."""


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


class ArticleDiscoveryService:
    """Naver News API adapter; credentials remain entirely environment-owned."""

    endpoint = "https://openapi.naver.com/v1/search/news.json"

    def discover(self, query: str, terms: Iterable[str] = (), limit: int = 10) -> list[ArticleCandidate]:
        if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
            raise ArticleDiscoveryUnavailable("NAVER_CLIENT_ID/NAVER_CLIENT_SECRET are not configured")
        query = _clean(query)
        if not query:
            return []
        limit = max(1, min(int(limit), 30))
        response = httpx.get(
            self.endpoint,
            params={"query": query, "display": limit, "sort": "date"},
            headers={"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET},
            timeout=12,
            follow_redirects=False,
        )
        response.raise_for_status()
        tokens = [term.lower() for term in terms if _clean(term)] or [query.lower()]
        results: list[ArticleCandidate] = []
        for item in response.json().get("items", []):
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

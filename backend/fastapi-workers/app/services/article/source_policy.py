"""Phase-1 source guard: attributable Korean articles from reviewed domains."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app import runtime_config
from app.models.article_evidence import ArticleSource, EvidenceCaptureRequest

HANGUL = re.compile(r"[가-힣]")


class NonKoreanArticleError(ValueError):
    code = "NON_KOREAN_ARTICLE"


class PublisherNotAllowedError(ValueError):
    code = "PUBLISHER_NOT_ALLOWED"


@dataclass(frozen=True)
class PublisherRule:
    key: str
    name: str
    containers: tuple[str, ...]
    excludes: tuple[str, ...]
    ko_mirror_from: str | None = None
    ko_mirror_to: str | None = None


# Parsed at import time on purpose: this is a small, reviewed policy surface.
# PyYAML is intentionally not a runtime dependency for this worker.
PUBLISHERS: dict[str, PublisherRule] = {
    "yna.co.kr": PublisherRule("yna.co.kr", "연합뉴스", ("article.story-news", "div#articleWrap", "article"), ("header", "nav", "aside", ".share", ".related", ".ad", "footer", ".comment"), "en.yna.co.kr", "www.yna.co.kr"),
    "mk.co.kr": PublisherRule("mk.co.kr", "매일경제", ("div.news_cnt_detail_wrap", "article"), ("header", "nav", ".sns_area", ".ad_boundary", "aside", "footer")),
    "yonhapnewstv.co.kr": PublisherRule("yonhapnewstv.co.kr", "연합뉴스TV", ("article", ".article-content"), ("header", "nav", "aside", ".ad", "footer")),
}


def publisher_for_url(url: str) -> PublisherRule | None:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for domain, rule in PUBLISHERS.items():
        if host == domain or host.endswith("." + domain):
            return rule
    return None


def korean_mirror_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for rule in PUBLISHERS.values():
        if rule.ko_mirror_from and host == rule.ko_mirror_from:
            return url.replace(rule.ko_mirror_from, rule.ko_mirror_to or rule.ko_mirror_from, 1)
    return url


def assert_korean(html: str, title: str, body_sample: str) -> None:
    lang_match = re.search(r"<html[^>]+lang=[\"']([^\"']+)", html or "", flags=re.I)
    lang = (lang_match.group(1) if lang_match else "").lower()
    sample = f"{title} {body_sample}"
    hangul_ratio = len(HANGUL.findall(sample)) / max(len(sample), 1)
    if not (lang.startswith("ko") or hangul_ratio >= .30):
        raise NonKoreanArticleError(f"NON_KOREAN_ARTICLE: lang={lang or 'none'}, hangul_ratio={hangul_ratio:.2f}")


def assert_article_source(request: EvidenceCaptureRequest, *, html: str = "", title: str = "", body_sample: str = "") -> PublisherRule | None:
    """Validate request metadata and, when supplied, rendered page language."""
    source: ArticleSource | None = request.source
    url = source.url if source else request.source_url
    rule = publisher_for_url(url)
    if bool(runtime_config.value("article_allowed_publishers_only")) and rule is None:
        raise PublisherNotAllowedError(f"PUBLISHER_NOT_ALLOWED: {urlparse(url).hostname or 'unknown'}")
    if source and source.language != "ko":
        raise NonKoreanArticleError("NON_KOREAN_ARTICLE: source.language must be ko")
    if html or title or body_sample:
        assert_korean(html, title, body_sample)
    return rule

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
    "hankyung.com": PublisherRule("hankyung.com", "한국경제", ("article", "#articletxt", "div.article-body"), ("header", "nav", "aside", ".ad", "footer")),
    "sedaily.com": PublisherRule("sedaily.com", "서울경제", ("article", "div.v_news_detail"), ("header", "nav", "aside", ".ad", "footer")),
    "edaily.co.kr": PublisherRule("edaily.co.kr", "이데일리", ("article", "div.news_body"), ("header", "nav", "aside", ".ad", "footer")),
    "mt.co.kr": PublisherRule("mt.co.kr", "머니투데이", ("article", "div#textBody"), ("header", "nav", "aside", ".ad", "footer")),
    "fnnews.com": PublisherRule("fnnews.com", "파이낸셜뉴스", ("article", "div#article_content"), ("header", "nav", "aside", ".ad", "footer")),
    "heraldcorp.com": PublisherRule("heraldcorp.com", "헤럴드경제", ("article", "div#articleText"), ("header", "nav", "aside", ".ad", "footer")),
    "chosun.com": PublisherRule("chosun.com", "조선일보", ("article", "section.article-body"), ("header", "nav", "aside", ".ad", "footer")),
    "joongang.co.kr": PublisherRule("joongang.co.kr", "중앙일보", ("article", "div#article_body"), ("header", "nav", "aside", ".ad", "footer")),
    "donga.com": PublisherRule("donga.com", "동아일보", ("article", "div.article_txt"), ("header", "nav", "aside", ".ad", "footer")),
    "ytn.co.kr": PublisherRule("ytn.co.kr", "YTN", ("article", "div.article_text"), ("header", "nav", "aside", ".ad", "footer")),
    "kbs.co.kr": PublisherRule("kbs.co.kr", "KBS뉴스", ("article", "div#cont_newstxt"), ("header", "nav", "aside", ".ad", "footer")),
    "sbs.co.kr": PublisherRule("sbs.co.kr", "SBS뉴스", ("article", "div.main_text"), ("header", "nav", "aside", ".ad", "footer")),
    "imbc.com": PublisherRule("imbc.com", "MBC뉴스", ("article", "div.news_txt"), ("header", "nav", "aside", ".ad", "footer")),
    "news1.kr": PublisherRule("news1.kr", "뉴스1", ("article", "div#articles_detail"), ("header", "nav", "aside", ".ad", "footer")),
    "newsis.com": PublisherRule("newsis.com", "뉴시스", ("article", "div.article_body"), ("header", "nav", "aside", ".ad", "footer")),
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

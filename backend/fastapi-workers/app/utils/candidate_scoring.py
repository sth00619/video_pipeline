"""Evidence-grounded keyword candidate scoring.

No score is inferred from an LLM.  Every numeric contribution is derived from
news lookups, the collected market snapshot, or public YouTube metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from app.utils.topic_evidence import is_market_level_forecast, specific_terms
from app.workers.news_keyword_extractor import NewsKeywordExtractor


def _parse_published_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _article_matches(article: dict, terms: list[str]) -> bool:
    if not terms:
        return False
    text = " ".join(str(article.get(key, "")) for key in ("title", "summary", "description")).casefold()
    required = 1 if len(terms) == 1 else min(2, len(terms))
    return sum(term.casefold() in text for term in terms) >= required


def _grounded_numbers(news_keywords: list[dict], articles: list[dict], market_data: dict) -> set[float]:
    values: set[float] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                collect(nested)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            values.add(round(float(value), 1))
        elif isinstance(value, str):
            for number in re.findall(r"\d+(?:\.\d+)?", value):
                values.add(round(float(number), 1))

    for item in news_keywords:
        collect(item.get("keyword"))
        collect(item.get("sample_headline"))
    for article in articles:
        collect(article.get("title"))
        collect(article.get("summary"))
    collect(market_data or {})
    return values


def _candidate_has_numeric_claim(candidate: dict) -> tuple[bool, bool]:
    text = f"{candidate.get('keyword', '')} {candidate.get('reason', '')}"
    values = [round(float(value), 1) for value in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]
    return bool(values), False if values else True


def _market_metrics_for_category(market_data: dict, category: str, candidate: dict) -> list[str]:
    if not isinstance(market_data, dict):
        return []
    category = (category or "").upper()
    text = f"{candidate.get('keyword', '')} {candidate.get('reason', '')}".casefold()
    metrics: list[str] = []
    kr = market_data.get("kr") or {}
    us = market_data.get("us") or {}
    associated = market_data.get("associated_data") or {}

    if category in {"KOSPI", "KOSDAQ", "INDIVIDUAL_STOCK"}:
        index_name = "kosdaq" if category == "KOSDAQ" else "kospi"
        if ((kr.get("index") or {}).get(index_name)):
            metrics.append(f"kr.index.{index_name}")
        if (kr.get("market_indicators") or {}).get("usd_krw") is not None:
            metrics.append("kr.market_indicators.usd_krw")
    elif category in {"US_STOCKS", "GLOBAL_MACRO"}:
        for index_name in ("sp500", "nasdaq"):
            if ((us.get("index") or {}).get(index_name)):
                metrics.append(f"us.index.{index_name}")
        for name in ("fed_rate", "cpi", "unemployment", "us_10yr_yield"):
            if (us.get("macro") or {}).get(name) is not None:
                metrics.append(f"us.macro.{name}")
    if associated.get("associated_stocks"):
        metrics.append("associated_data.associated_stocks")

    # A clearly mismatched market must not receive a full category score.
    if category == "US_STOCKS" and any(token in text for token in ("코스피", "코스닥")):
        return []
    if category in {"KOSPI", "KOSDAQ"} and any(token in text for token in ("s&p", "nasdaq", "dow jones")):
        return []
    return metrics


def _category_score(market_data: dict, category: str, candidate: dict) -> int:
    metrics = _market_metrics_for_category(market_data, category, candidate)
    if metrics:
        return 20
    if market_data:
        return 10
    return 5


def _youtube_score(candidate: dict) -> int | None:
    videos = candidate.get("source_videos") or []
    if not candidate.get("metrics_available") and not videos:
        return None
    engagement = float(candidate.get("engagement_ratio") or 0)
    outperformance = float(candidate.get("outperformance_index") or 0)
    return round(min(engagement, 5) / 5 * 7 + min(outperformance, 4) / 4 * 8)


def score_candidates(candidates: list[dict], news_keywords: list[dict], market_data: dict,
                     category: str, seed: str, extractor: NewsKeywordExtractor | None = None) -> list[dict]:
    """Attach an auditable 0–100 score and raw evidence to each candidate."""
    extractor = extractor or NewsKeywordExtractor()
    scored: list[dict] = []
    for source_candidate in candidates:
        candidate = dict(source_candidate)
        keyword = str(candidate.get("keyword") or "").strip()
        # Direct-news scoring is anchored to the editorial brief's distinctive
        # terms, so a generic category headline cannot masquerade as evidence.
        terms = specific_terms(seed) or specific_terms(keyword)
        lookup_failed = False
        try:
            recent_news = extractor.search_recent_news(keyword or seed, max_age_hours=72, limit=6)
        except Exception:
            recent_news = []
            lookup_failed = True
        direct_news = [article for article in recent_news if _article_matches(article, terms)]
        latest = max((_parse_published_at(article.get("publishedAt")) for article in direct_news), default=None)
        count_score = min(len(direct_news), 4) / 4 * 24
        freshness_score = 0
        if latest:
            age_hours = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
            freshness_score = 16 if age_hours <= 24 else 10 if age_hours <= 72 else 5 if age_hours <= 24 * 7 else 0
        news_score = round(count_score + freshness_score)

        market_outlook = is_market_level_forecast([keyword or seed])
        claims_numbers = [round(float(value), 1) for value in re.findall(
            r"(\d+(?:\.\d+)?)\s*%", f"{candidate.get('keyword', '')} {candidate.get('reason', '')}"
        )]
        grounded = _grounded_numbers(news_keywords, direct_news, market_data)
        if claims_numbers:
            numeric_claims_verified: bool | None = all(
                any(abs(number - evidence) <= 0.1 for evidence in grounded) for number in claims_numbers
            )
            numeric_points = 15 if numeric_claims_verified else 0
        else:
            numeric_claims_verified = None
            numeric_points = 7
        market_metrics = _market_metrics_for_category(market_data, category, candidate)
        # A broad market outlook can be evidenced by the live index snapshot
        # itself.  Give it enough auditable weight to reach the normal 55-point
        # automatic-confirmation threshold without pretending it has a direct
        # company-news match.
        market_data_score = numeric_points + (20 if market_outlook and market_metrics else 10 if market_metrics else 0)
        category_score = _category_score(market_data, category, candidate)
        youtube_score = _youtube_score(candidate)
        raw_score = news_score + market_data_score + category_score
        total_score = raw_score + youtube_score if youtube_score is not None else raw_score * 100 / 85
        candidate.update({
            "score": round(total_score),
            "news_score": news_score,
            "market_data_score": market_data_score,
            "category_score": category_score,
            "youtube_score": youtube_score,
            "metrics_available": youtube_score is not None,
            "evidence": {
                "news_count": len(direct_news),
                "latest_news_at": latest.isoformat() if latest else None,
                "news_sources": sorted({str(article.get("source") or "Google News") for article in direct_news}),
                "numeric_claims_verified": numeric_claims_verified,
                "market_metrics": market_metrics,
                "youtube_data_available": youtube_score is not None,
                "evidence_video_ids": candidate.get("evidence_video_ids") or [
                    video.get("video_id") for video in (candidate.get("source_videos") or []) if video.get("video_id")
                ],
                "news_lookup_failed": lookup_failed,
            },
        })
        candidate["auto_confirm_eligible"] = bool(
            candidate["score"] >= 55 and (len(direct_news) >= 1 or (market_outlook and bool(market_data)))
        )
        scored.append(candidate)
    return scored

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.candidate_scoring import score_candidates
from app.workers.script_worker import _script_audit_fields


class _NewsExtractor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def search_recent_news(self, *_args, **_kwargs) -> list[dict]:
        return list(self.rows)


def _article(index: int, *, with_url: bool = True) -> dict:
    return {
        "title": f"삼성전자 실적 검증 기사 {index}",
        "url": f"https://news.example/{index}" if with_url else "",
        "source": "한국경제",
        "outlet": "한국경제",
        "publishedAt": datetime.now(timezone.utc).isoformat(),
        "hoursSincePublish": 1,
    }


def test_candidate_scoring_saves_news_article_urls():
    scored = score_candidates(
        [{"keyword": "삼성전자 실적", "reason": ""}],
        [],
        {},
        "INDIVIDUAL_STOCK",
        "삼성전자 실적",
        extractor=_NewsExtractor([_article(1), _article(2), _article(3)]),
    )[0]

    assert len(scored["news_articles"]) == 3
    assert scored["news_articles"][0] == {
        "title": "삼성전자 실적 검증 기사 1",
        "link": "https://news.example/1",
        "outlet": "한국경제",
        "pubDate": scored["news_articles"][0]["pubDate"],
    }


def test_articles_without_url_are_excluded():
    scored = score_candidates(
        [{"keyword": "삼성전자 실적", "reason": ""}],
        [],
        {},
        "INDIVIDUAL_STOCK",
        "삼성전자 실적",
        extractor=_NewsExtractor([_article(1), _article(2, with_url=False)]),
    )[0]

    assert [article["link"] for article in scored["news_articles"]] == [
        "https://news.example/1"
    ]


def test_script_response_audit_includes_at_most_five_source_videos():
    facts = [
        {"fact": "검증 사실", "source_ref": ["한국경제", "DART"]},
        {"fact": "추가 사실", "source_ref": ["DART", "연합뉴스"]},
    ]
    videos = [
        {
            "video_id": f"video-{index}",
            "title": f"영상 {index}",
            "channel_title": f"채널 {index}",
        }
        for index in range(1, 8)
    ]

    audit = _script_audit_fields(facts, videos)

    assert audit["source_ref"] == ["한국경제", "DART", "연합뉴스"]
    assert len(audit["source_videos"]) == 5
    assert audit["source_videos"][0] == {
        "video_id": "video-1",
        "title": "영상 1",
        "channel": "채널 1",
    }

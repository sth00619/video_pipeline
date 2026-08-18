from datetime import datetime, timezone

from app.utils.candidate_scoring import score_candidates
from app.workers import script_worker


class _RecordingOutletExtractor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls: list[dict] = []

    def search_recent_news(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        if kwargs.get("outlet_filter"):
            return [row for row in self.rows if row.get("outlet")]
        return list(self.rows)


def _articles():
    published_at = datetime.now(timezone.utc).isoformat()
    return [
        {
            "title": "반도체 실적 전망을 다룬 금융 기사",
            "source": "한국경제",
            "outlet": "한국경제",
            "url": "https://www.hankyung.com/article/approved",
            "publishedAt": published_at,
            "hoursSincePublish": 1,
        },
        {
            "title": "반도체 실적 전망을 다룬 KPI뉴스 기사",
            "source": "KPI뉴스",
            "outlet": "",
            "url": "https://www.kpinews.kr/article/rejected",
            "publishedAt": published_at,
            "hoursSincePublish": 1,
        },
    ]


def test_candidate_scoring_uses_outlet_filter_and_excludes_kpi_news():
    extractor = _RecordingOutletExtractor(_articles())

    result = score_candidates(
        [{"keyword": "반도체 실적 전망", "reason": ""}],
        [],
        {},
        "INDIVIDUAL_STOCK",
        "반도체 실적 전망",
        extractor=extractor,
    )[0]

    assert extractor.calls == [{
        "query": "반도체 실적 전망",
        "max_age_hours": 24 * 7,
        "limit": 12,
        "outlet_filter": True,
    }]
    assert result["evidence"]["news_count"] == 1
    assert result["evidence"]["news_sources"] == ["한국경제"]


def test_script_and_candidate_use_same_outlet_filter(monkeypatch):
    extractor = _RecordingOutletExtractor(_articles())
    monkeypatch.setattr(script_worker, "NewsKeywordExtractor", lambda: extractor)

    score_candidates(
        [{"keyword": "반도체", "reason": ""}],
        [],
        {},
        "INDIVIDUAL_STOCK",
        "반도체",
        extractor=extractor,
    )
    script_worker._collect_keyword_news(["반도체"])

    assert len(extractor.calls) == 2
    assert all(call["outlet_filter"] is True for call in extractor.calls)

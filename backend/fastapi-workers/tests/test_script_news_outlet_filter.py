import logging

from app.utils.candidate_scoring import score_candidates
from app.workers import script_worker


class _RecordingNewsExtractor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    def search_recent_news(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        if kwargs.get("outlet_filter"):
            return [row for row in self.rows if row.get("outlet")]
        return list(self.rows)


def test_script_news_collection_uses_outlet_filter(monkeypatch):
    extractor = _RecordingNewsExtractor()
    monkeypatch.setattr(script_worker, "NewsKeywordExtractor", lambda: extractor)

    script_worker._collect_keyword_news(["반도체"])

    assert extractor.calls == [{
        "query": "반도체",
        "max_age_hours": 24 * 7,
        "limit": 6,
        "outlet_filter": True,
    }]


def test_candidate_scoring_news_uses_same_outlet_filter_as_script():
    extractor = _RecordingNewsExtractor()

    score_candidates(
        [{"keyword": "반도체", "reason": ""}],
        [],
        {},
        "KOSPI",
        "반도체",
        extractor=extractor,
    )

    assert extractor.calls
    assert extractor.calls[0]["outlet_filter"] is True


def test_zero_news_articles_logs_warning_not_raises(monkeypatch, caplog):
    extractor = _RecordingNewsExtractor()
    monkeypatch.setattr(script_worker, "NewsKeywordExtractor", lambda: extractor)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        script_worker,
        "plan_narrative",
        lambda *_args, **_kwargs: {"plan_id": "test_plan", "story_beats": []},
    )
    monkeypatch.setattr(
        script_worker,
        "review_flow",
        lambda *_args, **_kwargs: {"passed": True, "method": "test", "transition_issues": []},
    )
    worker = script_worker.ScriptWorker()
    monkeypatch.setattr(worker, "_multi_round_fact_check", lambda *_args, **_kwargs: ([], []))

    def _fake_generate(*_args, **_kwargs):
        full_script, sections = worker._mock_script("반도체 HBM", "개별 종목", 1)
        return full_script, sections, "테스트 제목", "테스트 썸네일", "테스트 설명", "테스트 쇼츠"

    monkeypatch.setattr(worker, "_generate_with_verified_facts", _fake_generate)

    with caplog.at_level(logging.WARNING):
        result = worker.generate(
            keyword="반도체 HBM",
            category="INDIVIDUAL_STOCK",
            target_minutes=1,
            market_data={"source": "test"},
            job_id=999,
        )

    assert result["news_cross_check_status"] == "no_finance_outlet_articles"
    assert "23개 금융 언론사 기사 0건" in caplog.text
    assert "뉴스 검증 없이 진행" in caplog.text


def test_non_finance_articles_excluded_from_script_cross_check(monkeypatch):
    extractor = _RecordingNewsExtractor([
        {
            "title": "반도체 투자 확대",
            "url": "https://www.hankyung.com/article/1",
            "outlet": "한국경제",
        },
        {
            "title": "반도체 선수 인터뷰",
            "url": "https://sports.example.test/article/2",
            "outlet": "",
        },
    ])
    monkeypatch.setattr(script_worker, "NewsKeywordExtractor", lambda: extractor)

    articles = script_worker._collect_keyword_news(["반도체"])

    assert len(articles) == 1
    assert articles[0]["outlet"] == "한국경제"
    assert articles[0]["matched_keyword"] == "반도체"

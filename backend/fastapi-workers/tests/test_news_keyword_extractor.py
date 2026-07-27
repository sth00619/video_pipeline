from datetime import datetime, timezone

from app.workers.news_keyword_extractor import NewsKeywordExtractor


def test_recent_news_prefers_naver_api_hub_when_configured(monkeypatch):
    published = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    class FakeNaverApiHubClient:
        def search_news(self, *args, **kwargs):
            return {
                "items": [{
                    "title": "<b>반도체</b> 신규 투자",
                    "originallink": "https://example.com/news",
                    "pubDate": published,
                }]
            }

    monkeypatch.setattr("app.workers.news_keyword_extractor.naver_api_hub_configured", lambda: True)
    monkeypatch.setattr("app.workers.news_keyword_extractor.NaverApiHubClient", FakeNaverApiHubClient)

    rows = NewsKeywordExtractor().search_recent_news("반도체", limit=1)

    assert rows[0]["source"] == "NAVER 뉴스"
    assert rows[0]["title"] == "반도체 신규 투자"


def test_trend_is_attached_as_relative_source_data_without_changing_score(monkeypatch):
    class FakeNaverApiHubClient:
        def search_trend(self, **kwargs):
            return {
                "startDate": kwargs["start_date"],
                "endDate": kwargs["end_date"],
                "timeUnit": kwargs["time_unit"],
                "results": [{
                    "title": "반도체",
                    "data": [{"period": kwargs["start_date"], "ratio": 100}],
                }],
            }

    rows = [{"keyword": "반도체", "score": 0.84}]
    monkeypatch.setattr("app.workers.news_keyword_extractor.naver_api_hub_configured", lambda: True)
    monkeypatch.setattr("app.workers.news_keyword_extractor.NaverApiHubClient", FakeNaverApiHubClient)

    NewsKeywordExtractor()._attach_naver_trends(rows)

    assert rows[0]["score"] == 0.84
    assert rows[0]["naver_search_trend"]["data"] == [{"period": rows[0]["naver_search_trend"]["start_date"], "ratio": 100}]
    assert "상대" in rows[0]["naver_search_trend"]["ratio_note"]

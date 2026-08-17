from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.workers import news_keyword_extractor as news_module
from app.workers.news_keyword_extractor import (
    KOREAN_FINANCE_NEWS_OUTLETS,
    NewsKeywordExtractor,
    _is_finance_outlet,
)


client = TestClient(app)


def _published_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def _install_naver(monkeypatch, items: list[dict]) -> None:
    class _FakeNaverApiHubClient:
        def search_news(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return {"items": items}

    monkeypatch.setattr(news_module, "naver_api_hub_configured", lambda: True)
    monkeypatch.setattr(news_module, "NaverApiHubClient", _FakeNaverApiHubClient)


def test_finance_outlet_list_contains_exactly_twenty_three_sources():
    assert len(KOREAN_FINANCE_NEWS_OUTLETS) == 23


def test_finance_outlet_match_returns_name():
    assert _is_finance_outlet("https://www.hankyung.com/article/12345") == (True, "한국경제")


def test_chosun_biz_is_checked_before_chosun_daily():
    assert _is_finance_outlet("https://biz.chosun.com/stock/12345") == (True, "조선비즈")


def test_non_finance_and_spoofed_domains_return_false():
    assert _is_finance_outlet("https://sports.chosun.com/article/12345") == (False, "")
    assert _is_finance_outlet("https://hankyung.com.example.com/article/12345") == (False, "")


def test_empty_url_returns_false():
    assert _is_finance_outlet("") == (False, "")


def test_four_new_finance_outlets_are_included():
    cases = {
        "https://www.etnews.com/20260817_001": "전자신문",
        "https://www.newspim.com/news/view/1": "뉴스핌",
        "https://www.thebell.co.kr/free/content/1": "더벨",
        "https://www.fntimes.com/html/view.php?ud=1": "한국금융신문",
    }
    assert {_is_finance_outlet(url)[1] for url in cases} == set(cases.values())


def test_outlet_filter_true_keeps_only_finance_news(monkeypatch):
    _install_naver(monkeypatch, [
        {
            "title": "<b>반도체</b> 투자 확대",
            "description": "금융 기사 요약",
            "originallink": "https://www.hankyung.com/article/12345",
            "pubDate": _published_now(),
        },
        {
            "title": "스포츠 소식",
            "originallink": "https://sports.chosun.com/article/67890",
            "pubDate": _published_now(),
        },
    ])

    result = NewsKeywordExtractor().search_recent_news(
        "반도체", max_age_hours=3, limit=1, outlet_filter=True
    )

    assert len(result) == 1
    assert result[0]["outlet"] == "한국경제"
    assert result[0]["description"] == "금융 기사 요약"


def test_outlet_filter_returns_empty_without_raw_fallback(monkeypatch):
    _install_naver(monkeypatch, [{
        "title": "스포츠 소식",
        "originallink": "https://sports.chosun.com/article/67890",
        "pubDate": _published_now(),
    }])
    monkeypatch.setattr(news_module.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))

    result = NewsKeywordExtractor().search_recent_news(
        "반도체", max_age_hours=3, outlet_filter=True
    )

    assert result == []


def test_default_search_keeps_existing_unfiltered_candidate_scoring_contract(monkeypatch):
    _install_naver(monkeypatch, [{
        "title": "일반 공개 기사",
        "originallink": "https://example.com/article/1",
        "pubDate": _published_now(),
    }])

    result = NewsKeywordExtractor().search_recent_news("반도체", max_age_hours=24 * 7, limit=1)

    assert len(result) == 1
    assert result[0]["outlet"] == ""


def test_hours_parameter_and_outlet_filter_are_passed_to_preview(monkeypatch):
    captured = {}

    class _Analyzer:
        def collect(self, **kwargs):  # noqa: ANN003
            captured["video_hours"] = kwargs["recent_hours"]
            return []

    def _fake_search(self, query, max_age_hours=2, limit=6, outlet_filter=False):  # noqa: ANN001
        captured["news_hours"] = max_age_hours
        captured["outlet_filter"] = outlet_filter
        return [{
            "title": "반도체 기사",
            "url": "https://www.hankyung.com/article/1",
            "outlet": "한국경제",
        }]

    monkeypatch.setattr("app.providers.factory.get_trending_video_analyzer", lambda: _Analyzer())
    monkeypatch.setattr(NewsKeywordExtractor, "search_recent_news", _fake_search)

    response = client.get("/workers/keyword-news-preview?keyword=반도체&hours=1")

    assert response.status_code == 200
    assert captured == {"video_hours": 1, "news_hours": 1, "outlet_filter": True}
    assert response.json()["recentNews"][0]["outlet"] == "한국경제"
    assert response.json()["outletFilter"] is True


def test_existing_manual_context_post_uses_selected_hours(monkeypatch):
    captured = {}

    class _Analyzer:
        def collect(self, **kwargs):  # noqa: ANN003
            return []

    def _fake_search(self, query, max_age_hours=2, limit=6, outlet_filter=False):  # noqa: ANN001
        captured["hours"] = max_age_hours
        captured["outlet_filter"] = outlet_filter
        return []

    monkeypatch.setattr("app.providers.factory.get_trending_video_analyzer", lambda: _Analyzer())
    monkeypatch.setattr(NewsKeywordExtractor, "search_recent_news", _fake_search)

    response = client.post("/workers/keyword/manual-context", json={
        "keyword": "반도체",
        "recent_hours": 24,
        "category": "KOSPI",
    })

    assert response.status_code == 200
    assert captured == {"hours": 24, "outlet_filter": True}
    assert response.json()["windowHours"] == 24


def test_invalid_hours_returns_400():
    response = client.get("/workers/keyword-news-preview?keyword=반도체&hours=4")

    assert response.status_code == 400

    post_response = client.post("/workers/keyword/manual-context", json={
        "keyword": "반도체",
        "recent_hours": 4,
    })
    assert post_response.status_code == 400


def test_us_market_news_returns_empty_without_finnhub_key(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setattr(news_module, "FINNHUB_API_KEY", "")

    assert NewsKeywordExtractor().search_recent_news_us_market("nvidia", max_age_hours=24) == []


def test_us_category_combines_finnhub_news(monkeypatch):
    class _Analyzer:
        def collect(self, **kwargs):  # noqa: ANN003
            return []

    monkeypatch.setattr("app.providers.factory.get_trending_video_analyzer", lambda: _Analyzer())
    monkeypatch.setattr(NewsKeywordExtractor, "search_recent_news", lambda *args, **kwargs: [])
    monkeypatch.setattr(NewsKeywordExtractor, "search_recent_news_us_market", lambda *args, **kwargs: [{
        "title": "Nvidia earnings",
        "url": "https://example.com/nvidia",
        "outlet": "Reuters",
    }])

    response = client.get(
        "/workers/keyword-news-preview?keyword=nvidia&hours=24&category=US_STOCKS"
    )

    assert response.status_code == 200
    assert response.json()["category"] == "US_STOCKS"
    assert response.json()["recentNews"][0]["outlet"] == "Reuters"

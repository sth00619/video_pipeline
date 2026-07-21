from datetime import datetime, timedelta, timezone

from app.utils.candidate_scoring import score_candidates


class FakeExtractor:
    def __init__(self, rows):
        self.rows = rows

    def search_recent_news(self, query, max_age_hours=72, limit=6):
        return self.rows[:limit]


def market_snapshot():
    return {
        "us": {
            "index": {"sp500": {"close": 5000.0, "change_pct": 2.0}, "nasdaq": {"close": 17000.0, "change_pct": 1.0}},
            "macro": {"fed_rate": 4.5, "cpi": 3.0},
        }
    }


def recent_articles(count=4):
    now = datetime.now(timezone.utc)
    return [
        {
            "title": f"Nvidia earnings latest news {index} 2%",
            "source": f"Source {index}",
            "publishedAt": (now - timedelta(hours=index)).isoformat(),
        }
        for index in range(count)
    ]


def test_four_recent_direct_articles_receive_full_news_score():
    result = score_candidates(
        [{"keyword": "Nvidia earnings", "reason": ""}], [], market_snapshot(), "US_STOCKS", "Nvidia earnings",
        FakeExtractor(recent_articles()),
    )[0]
    assert result["news_score"] == 40
    assert result["evidence"]["news_count"] == 4


def test_youtube_absence_renormalizes_the_available_85_points_to_100():
    result = score_candidates(
        [{"keyword": "Nvidia earnings 2%", "reason": ""}], [], market_snapshot(), "US_STOCKS", "Nvidia earnings",
        FakeExtractor(recent_articles()),
    )[0]
    assert result["youtube_score"] is None
    assert result["score"] == 100


def test_candidate_without_numeric_claim_uses_neutral_seven_points():
    result = score_candidates(
        [{"keyword": "Nvidia earnings", "reason": ""}], [], market_snapshot(), "US_STOCKS", "Nvidia earnings",
        FakeExtractor(recent_articles()),
    )[0]
    assert result["evidence"]["numeric_claims_verified"] is None
    assert result["market_data_score"] == 17


def test_ungrounded_percent_claim_receives_no_numeric_points():
    result = score_candidates(
        [{"keyword": "Nvidia earnings 99%", "reason": ""}], [], market_snapshot(), "US_STOCKS", "Nvidia earnings",
        FakeExtractor(recent_articles()),
    )[0]
    assert result["evidence"]["numeric_claims_verified"] is False
    assert result["market_data_score"] == 10


def test_candidate_without_direct_evidence_is_not_auto_confirmable():
    result = score_candidates(
        [{"keyword": "nonexistent compound subject", "reason": ""}], [], {}, "US_STOCKS", "nonexistent compound subject",
        FakeExtractor([]),
    )[0]
    assert result["auto_confirm_eligible"] is False


def test_market_level_outlook_can_use_live_market_snapshot_without_direct_article_match():
    result = score_candidates(
        [{"keyword": "US stock market outlook", "reason": ""}], [], market_snapshot(), "US_STOCKS", "US stock market outlook",
        FakeExtractor([]),
    )[0]
    assert result["news_score"] == 0
    assert result["market_data_score"] == 27
    assert result["score"] == 55
    assert result["auto_confirm_eligible"] is True

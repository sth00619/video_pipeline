from app.providers.base import TrendingVideo
from app.utils.candidate_scoring import score_candidates
from app.workers.keyword_worker import KeywordWorker, _seed_candidate


class _NoNewsExtractor:
    def extract_kr_keywords(self, category: str, seed: str, top_n: int = 15):
        return []

    def search_recent_news(
        self,
        query: str,
        max_age_hours: int = 72,
        limit: int = 6,
        outlet_filter: bool = False,
    ):
        _ = outlet_filter
        return []


class _OneVideoAnalyzer:
    def __init__(self, video: TrendingVideo):
        self.video = video

    def collect(self, category: str, seed: str, limit: int = 30):
        return [self.video]


class _EmptyMarketCollector:
    def collect_for_category(self, category: str, seed: str):
        return {}


def _video(
    *,
    title: str = "삼성전자 3분기 실적 발표",
    views: int = 20_000,
    subscribers: int = 100_000,
    channel_avg_views: int = 5_000,
    channel_recent_avg_views: int | None = 10_000,
    channel_recent_sample_size: int = 10,
) -> TrendingVideo:
    return TrendingVideo(
        title=title,
        channel_title="테스트 채널",
        video_id="video-1",
        views=views,
        subscribers=subscribers,
        channel_avg_views=channel_avg_views,
        published_at="2026-08-17T00:00:00Z",
        hours_since_publish=10.0,
        channel_recent_avg_views=channel_recent_avg_views,
        channel_recent_sample_size=channel_recent_sample_size,
        outperformer_basis="recent_average",
    )


def _worker() -> KeywordWorker:
    return KeywordWorker.__new__(KeywordWorker)


def test_seed_candidate_starts_without_youtube_evidence():
    candidate = _seed_candidate("삼성전자 실적", "입력 주제", "실적 확인")

    assert candidate["metrics_available"] is False
    assert candidate["source_videos"] == []
    assert candidate["channel_recent_avg_views"] is None
    assert candidate["channel_recent_sample_size"] == 0
    assert candidate["outperformer_basis"] == "tiered_ratio"


def test_fuzzy_seed_match_connects_rephrased_youtube_candidate():
    worker = _worker()
    candidates = worker._filter_candidates_by_seed([], "삼성전자 실적", 5)
    youtube_candidates = worker._score_yt_videos([_video()])

    attached = worker._attach_youtube_metrics(candidates, youtube_candidates)
    primary = attached[0]

    assert primary["keyword"] == "삼성전자 실적"
    assert primary["metrics_available"] is True
    assert primary["source_videos"][0]["video_id"] == "video-1"
    assert primary["evidence_video_ids"] == ["video-1"]


def test_original_youtube_title_matches_when_clean_keyword_removed_bracketed_stock_name():
    worker = _worker()
    candidate = _seed_candidate("삼성전자", "입력 주제", "종목 확인")
    youtube_candidates = worker._score_yt_videos([
        _video(title="[삼성전자 주가전망] 긴급 호재 발표")
    ])

    attached = worker._attach_youtube_metrics([candidate], youtube_candidates)[0]

    assert youtube_candidates[0]["keyword"] == "호재 발표"
    assert attached["metrics_available"] is True
    assert attached["evidence_video_ids"] == ["video-1"]


def test_original_title_does_not_weaken_multi_term_relevance_requirement():
    worker = _worker()
    candidate = _seed_candidate("삼성전자 반도체 실적", "입력 주제", "실적 확인")
    youtube_candidates = worker._score_yt_videos([
        _video(title="[삼성전자 주가전망] 긴급 호재 발표")
    ])

    attached = worker._attach_youtube_metrics([candidate], youtube_candidates)[0]

    assert attached["metrics_available"] is False
    assert attached["source_videos"] == []


def test_recent_average_is_used_when_sample_has_ten_videos():
    scored = _worker()._score_yt_videos([_video()])[0]

    assert scored["outperformance_index"] == 2.0
    assert scored["channel_recent_avg_views"] == 10_000
    assert scored["channel_recent_sample_size"] == 10
    assert scored["outperformer_basis"] == "recent_average"
    assert scored["source_videos"][0]["outperformer_basis"] == "recent_average"


def test_existing_b4_recent_average_basis_is_preserved():
    video = _video()
    video.outperformer_basis = "recent_average_1_5x"

    scored = _worker()._score_yt_videos([video])[0]

    assert scored["outperformer_basis"] == "recent_average_1_5x"


def test_legacy_channel_average_is_fallback_for_small_recent_sample():
    scored = _worker()._score_yt_videos([
        _video(channel_recent_avg_views=10_000, channel_recent_sample_size=9)
    ])[0]

    assert scored["outperformance_index"] == 4.0
    assert scored["outperformer_basis"] == "channel_avg_fallback"


def test_youtube_score_stays_none_without_source_video_evidence():
    candidate = _seed_candidate("삼성전자 실적", "입력 주제", "실적 확인")
    candidate["metrics_available"] = True

    scored = score_candidates(
        [candidate], [], {}, "KOSPI", "삼성전자 실적", _NoNewsExtractor()
    )[0]

    assert scored["youtube_score"] is None
    assert scored["metrics_available"] is False


def test_real_youtube_evidence_breaks_equal_no_data_score():
    worker = _worker()
    no_data = _seed_candidate("삼성전자 실적", "입력 주제", "실적 확인")
    with_data = _seed_candidate("삼성전자 실적", "입력 주제", "실적 확인")
    youtube_candidates = worker._score_yt_videos([_video(
        views=100_000,
        subscribers=20_000,
        channel_avg_views=25_000,
        channel_recent_avg_views=25_000,
    )])
    worker._attach_youtube_metrics([with_data], youtube_candidates)
    market_data = {
        "kr": {
            "index": {"kospi": {"close": 2_700, "change_pct": -4.7}},
            "market_indicators": {"usd_krw": 1_400},
        }
    }

    scored_no_data, scored_with_data = score_candidates(
        [no_data, with_data], [], market_data, "KOSPI", "삼성전자 실적", _NoNewsExtractor()
    )

    assert scored_no_data["youtube_score"] is None
    assert scored_no_data["score"] == 49
    assert scored_with_data["youtube_score"] is not None
    assert scored_with_data["score"] > scored_no_data["score"]
    assert scored_with_data["score"] != 49


def test_b4_fields_are_copied_from_best_matching_youtube_candidate():
    worker = _worker()
    candidate = _seed_candidate("삼성전자 실적", "입력 주제", "실적 확인")
    youtube_candidates = worker._score_yt_videos([_video()])

    attached = worker._attach_youtube_metrics([candidate], youtube_candidates)[0]

    assert attached["channel_recent_avg_views"] == 10_000
    assert attached["channel_recent_sample_size"] == 10
    assert attached["outperformer_basis"] == "recent_average"


def test_search_reconnects_youtube_evidence_after_seed_filter(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    worker = _worker()
    worker.analyzer = _OneVideoAnalyzer(_video())
    worker.extractor = _NoNewsExtractor()
    worker.collector = _EmptyMarketCollector()

    result = worker.search("KOSPI", "삼성전자 실적", limit=3)
    primary = next(
        candidate
        for candidate in result["candidates"]
        if candidate["keyword"] == "삼성전자 실적"
    )

    assert result["yt_candidate_count"] == 1
    assert primary["youtube_score"] is not None
    assert primary["metrics_available"] is True
    assert primary["evidence"]["evidence_video_ids"] == ["video-1"]

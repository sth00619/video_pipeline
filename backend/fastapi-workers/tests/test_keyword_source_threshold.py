import unittest
from unittest.mock import patch

from app.providers.base import TrendingVideo
from app.providers.real.trending import _is_eligible_evidence_source
from app.workers.keyword_planning import build_mindmap


class KeywordSourceThresholdTests(unittest.TestCase):
    def test_small_channel_is_not_eligible_even_with_a_high_multiple(self):
        video = TrendingVideo(
            title="small channel spike", channel_title="small", video_id="small",
            views=4_000, subscribers=200, channel_avg_views=100,
            published_at="2026-07-20T00:00:00Z", hours_since_publish=8,
        )
        self.assertFalse(_is_eligible_evidence_source(video))

    def test_3k_subscriber_and_view_boundary_is_eligible_within_seven_days(self):
        video = TrendingVideo(
            title="qualified", channel_title="qualified", video_id="qualified",
            views=3_000, subscribers=3_000, channel_avg_views=1_000,
            published_at="2026-07-20T00:00:00Z", hours_since_publish=24,
        )
        self.assertTrue(_is_eligible_evidence_source(video))

    def test_high_subscriber_channel_still_needs_3k_views_and_minimum_multiple(self):
        video = TrendingVideo(
            title="too few views", channel_title="large", video_id="few-views",
            views=2_999, subscribers=20_000, channel_avg_views=1_000,
            published_at="2026-07-20T00:00:00Z", hours_since_publish=24,
        )
        self.assertFalse(_is_eligible_evidence_source(video))

        low_multiple = TrendingVideo(
            title="low response", channel_title="large", video_id="low-multiple",
            views=3_000, subscribers=20_000, channel_avg_views=1_000,
            published_at="2026-07-20T00:00:00Z", hours_since_publish=24,
        )
        self.assertFalse(_is_eligible_evidence_source(low_multiple))

    def test_live_stream_is_never_eligible_evidence(self):
        video = TrendingVideo(
            title="live", channel_title="channel", video_id="live",
            views=100_000, subscribers=10_000, channel_avg_views=1_000,
            published_at="2026-07-20T00:00:00Z", hours_since_publish=2,
            is_live=True,
        )
        self.assertFalse(_is_eligible_evidence_source(video))

    def test_mindmap_drops_untrusted_browser_rows(self):
        videos = [
            {"videoId": "small", "title": "small", "channelTitle": "small", "views": 4_000, "subscribers": 200, "hoursSincePublish": 4, "tags": ["제외태그"]},
            {"videoId": "live", "title": "live", "channelTitle": "live", "views": 60_000, "subscribers": 20_000, "hoursSincePublish": 4, "isLive": True, "tags": ["제외태그"]},
            {"videoId": "trusted", "title": "trusted", "channelTitle": "trusted", "views": 60_000, "subscribers": 20_000, "hoursSincePublish": 4, "tags": ["반도체"]},
        ]
        with patch("app.workers.keyword_planning._redis", return_value=None), patch(
            "app.workers.keyword_planning._claude_json", return_value={"normalized": [], "expansions": []}
        ):
            result = build_mindmap("주식", videos)
        self.assertEqual([item["keyword"] for item in result["primary"]], ["반도체"])


if __name__ == "__main__":
    unittest.main()

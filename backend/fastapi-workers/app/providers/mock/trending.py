"""
Mock 트렌딩 영상 분석기.
시드 기반 재현성 — 같은 (category, seed) 입력 → 같은 영상 풀.
"""
import hashlib
import random
from datetime import datetime, timedelta
from app.providers.base import TrendingVideoAnalyzer, TrendingVideo
from app.domain.stock_keywords import get_category_data


class MockTrendingVideoAnalyzer(TrendingVideoAnalyzer):

    def collect(self, category: str, seed: str, limit: int = 30) -> list[TrendingVideo]:
        cat_data = get_category_data(category)
        patterns = cat_data["title_patterns"]
        channels = cat_data["common_channels"]
        default_seeds = cat_data["default_seeds"]

        # 시드 기반 난수 (재현성)
        key = f"{category}:{seed}"
        seed_hash = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed_hash)

        videos = []
        for i in range(limit):
            title_template = rng.choice(patterns)
            actual_seed = seed.strip() if seed and seed.strip() else (
                rng.choice(default_seeds) if default_seeds else "주식"
            )
            title = title_template.format(seed=actual_seed)

            channel_title = rng.choice(channels)
            subscribers = rng.randint(5_000, 500_000)

            # 시간당 조회수 = 채널 영향력 × 영상 매력도 × 노출도
            hours_since = rng.uniform(2.0, 168.0)  # 2시간 ~ 1주일
            video_attractiveness = rng.uniform(0.3, 8.0)
            views_per_hour = (subscribers / 1000) * video_attractiveness
            views = max(100, int(views_per_hour * hours_since))

            # 채널 평균 조회수 (현재 영상의 0.3 ~ 2배)
            channel_avg = max(50, int(views * rng.uniform(0.3, 2.0)))

            videos.append(TrendingVideo(
                title=title,
                channel_title=channel_title,
                video_id=f"mock_{category[:3].lower()}_{i:03d}",
                views=views,
                subscribers=subscribers,
                channel_avg_views=channel_avg,
                published_at=(datetime.utcnow() - timedelta(hours=hours_since)).isoformat(),
                hours_since_publish=round(hours_since, 1),
            ))

        return videos

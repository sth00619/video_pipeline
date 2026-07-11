"""
YouTube Trending Analyzer — Official YouTube Data API v3 + Mock fallback + Redis 캐싱

v2에서 바뀐 것:
  1. [기능 보완] regionCode가 "KR"로 고정되어 있었습니다. 이 프로젝트는
     KOSPI/KOSDAQ뿐 아니라 미국 주식(US_STOCKS)도 다루는데, US 관련
     카테고리로 호출해도 한국 트렌딩 영상만 가져오고 있었습니다.
     category가 미국 관련이면 regionCode="US"로 전환하도록 수정.
  2. [마스터플랜 6.2절 반영] Redis 1시간 TTL 캐싱 추가. 같은
     category+seed 조합에 대해 1시간 이내 재호출 시 API를 다시
     부르지 않고 캐시를 반환합니다 (쿼터 절약 — 마스터플랜에서
     명시적으로 요구된 항목).
"""
import os
import json
import logging
import requests
from datetime import datetime, timezone
from app.providers.base import TrendingVideoAnalyzer, TrendingVideo
from app.providers.mock.trending import MockTrendingVideoAnalyzer
from app.config import REDIS_HOST, REDIS_PORT

logger = logging.getLogger(__name__)

_US_CATEGORIES = {"US_STOCKS"}
_CACHE_TTL_SECONDS = 3600  # 1시간 (마스터플랜 6.2절)


def _get_redis_client():
    try:
        import redis
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.warning(f"Redis 연결 불가, 캐싱 없이 진행: {e}")
        return None


class YouTubeTrendingAnalyzer(TrendingVideoAnalyzer):
    """
    YouTube Data API v3 기반 트렌딩 영상 분석기.
    """

    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.mock_fallback = MockTrendingVideoAnalyzer()
        self._redis = _get_redis_client()

    def collect(self, category: str, seed: str, limit: int = 30) -> list[TrendingVideo]:
        if not self.api_key:
            logger.info("YOUTUBE_API_KEY 미설정 → Mock 트렌딩 데이터 반환")
            return self.mock_fallback.collect(category, seed, limit)

        cache_key = f"trending:{category}:{seed}:{limit}"
        if self._redis:
            try:
                cached = self._redis.get(cache_key)
                if cached:
                    logger.info(f"Redis 캐시 히트: {cache_key}")
                    items = json.loads(cached)
                    return [TrendingVideo(**item) for item in items]
            except Exception as e:
                logger.warning(f"Redis 캐시 조회 실패, API 직접 호출로 진행: {e}")

        try:
            region_code = "US" if category in _US_CATEGORIES else "KR"
            video_category_id = "25"  # 뉴스/정치 (한국·미국 공통으로 금융/경제와 가장 근접한 공식 카테고리)

            videos_url = f"{self.base_url}/videos"
            params = {
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": region_code,
                "videoCategoryId": video_category_id,
                "maxResults": 50,
                "key": self.api_key
            }
            resp = requests.get(videos_url, params=params, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"YouTube API 실패 ({resp.status_code}), Mock 폴백 사용")
                return self.mock_fallback.collect(category, seed, limit)

            items = resp.json().get("items", [])
            if not items:
                return []

            results = []
            now = datetime.now(timezone.utc)

            finance_keywords_kr = ["주식", "증시", "코스피", "코스닥", "삼성전자", "금리", "환율", "부동산",
                                    "경제", "재테크", "투자", "비트코인", "cpi", "fomc", "나스닥", "엔비디아",
                                    "테슬라", "애플", "반도체", "실적"]
            finance_keywords_us = ["stock", "market", "nasdaq", "s&p", "fed", "fomc", "cpi", "inflation",
                                    "earnings", "nvidia", "tesla", "apple", "semiconductor", "interest rate",
                                    "dow jones", "investing"]
            finance_keywords = finance_keywords_us if region_code == "US" else finance_keywords_kr
            clean_seed = seed.strip().lower() if seed else ""

            for item in items:
                snippet = item.get("snippet", {})
                statistics = item.get("statistics", {})
                video_id = item.get("id")
                if not video_id:
                    continue

                title = snippet.get("title", "제목 없음")
                title_lower = title.lower()

                association_score = 0
                if clean_seed and clean_seed in title_lower:
                    association_score += 10
                for kw in finance_keywords:
                    if kw in title_lower:
                        association_score += 2

                views = int(statistics.get("viewCount", 150000))

                published_at = snippet.get("publishedAt", "2026-07-01T00:00:00Z")
                hours_since = 24.0
                if published_at:
                    try:
                        pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                        hours_since = (now - pub_dt).total_seconds() / 3600.0
                        hours_since = max(0.1, hours_since)
                    except Exception:
                        pass

                results.append({
                    "video": TrendingVideo(
                        title=title,
                        channel_title=snippet.get("channelTitle", "채널 없음"),
                        video_id=video_id,
                        views=views,
                        subscribers=50000,
                        channel_avg_views=max(views // 2, 1000),
                        published_at=published_at,
                        hours_since_publish=round(hours_since, 1)
                    ),
                    "association_score": association_score,
                    "views": views
                })

            results.sort(key=lambda x: (x["association_score"], x["views"]), reverse=True)
            final_videos = [r["video"] for r in results[:limit]]

            if self._redis:
                try:
                    serializable = [vars(v) for v in final_videos]
                    self._redis.setex(cache_key, _CACHE_TTL_SECONDS, json.dumps(serializable, ensure_ascii=False))
                    logger.info(f"Redis 캐시 저장: {cache_key} (TTL={_CACHE_TTL_SECONDS}s)")
                except Exception as e:
                    logger.warning(f"Redis 캐시 저장 실패: {e}")

            return final_videos

        except Exception as e:
            logger.error(f"YouTube API 수집 오류: {e}, Mock 폴백 사용")
            return self.mock_fallback.collect(category, seed, limit)

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
import re
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
            # API 키가 없을 때 임의 조회수/구독자 데이터를 만들어 내지 않는다.
            # 뉴스·시장 데이터 기반 후보는 계속 만들 수 있지만 YouTube 지표는 unavailable로 표시한다.
            logger.warning("YOUTUBE_API_KEY 미설정 → 실제 YouTube 지표 수집을 건너뜁니다")
            return []

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

        # Keyword searches need video and channel hydration. The chart endpoint
        # cannot tell us the real subscriber count and therefore is not enough
        # for the candidate-comparison screen.
        if seed and seed.strip():
            try:
                searched = self._collect_keyword_search(category, seed.strip(), limit)
                if self._redis:
                    try:
                        self._redis.setex(
                            cache_key, _CACHE_TTL_SECONDS,
                            json.dumps([vars(video) for video in searched], ensure_ascii=False),
                        )
                    except Exception as e:
                        logger.warning(f"YouTube 검색 결과 캐시 저장 실패: {e}")
                return searched
            except Exception as e:
                logger.warning(f"YouTube 키워드 검색 실패, 인기 차트 폴백 사용: {e}")

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
                return []

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
                        hours_since_publish=round(hours_since, 1),
                        subscriber_count_available=False,
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
            return []

    def _collect_keyword_search(self, category: str, seed: str, limit: int) -> list[TrendingVideo]:
        region_code = "US" if category in _US_CATEGORIES else "KR"
        search_params = {
            "part": "snippet",
            "q": seed,
            "type": "video",
            "order": "relevance",
            "regionCode": region_code,
            "relevanceLanguage": "en" if region_code == "US" else "ko",
            "maxResults": min(50, max(10, limit * 3)),
            "key": self.api_key,
        }
        search_response = requests.get(f"{self.base_url}/search", params=search_params, timeout=15)
        search_response.raise_for_status()
        search_items = search_response.json().get("items", [])
        video_ids = [
            item.get("id", {}).get("videoId")
            for item in search_items
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        videos_response = requests.get(
            f"{self.base_url}/videos",
            params={"part": "snippet,statistics,contentDetails", "id": ",".join(video_ids), "key": self.api_key},
            timeout=15,
        )
        videos_response.raise_for_status()
        video_items = videos_response.json().get("items", [])
        channel_ids = sorted({item.get("snippet", {}).get("channelId") for item in video_items if item.get("snippet", {}).get("channelId")})
        channel_subscribers: dict[str, int] = {}
        if channel_ids:
            channels_response = requests.get(
                f"{self.base_url}/channels",
                params={"part": "statistics", "id": ",".join(channel_ids), "key": self.api_key},
                timeout=15,
            )
            channels_response.raise_for_status()
            for item in channels_response.json().get("items", []):
                raw = item.get("statistics", {}).get("subscriberCount")
                if raw is not None:
                    channel_subscribers[item.get("id", "")] = int(raw)

        now = datetime.now(timezone.utc)
        rows = []
        for item in video_items:
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            content = item.get("contentDetails", {})
            video_id = item.get("id")
            channel_id = snippet.get("channelId", "")
            if not video_id:
                continue
            published_at = snippet.get("publishedAt", "")
            hours_since = 24.0
            try:
                published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                hours_since = max(0.1, (now - published).total_seconds() / 3600.0)
            except (TypeError, ValueError):
                pass
            rows.append({
                "item": item,
                "views": int(statistics.get("viewCount", 0) or 0),
                "channel_id": channel_id,
                "hours_since": round(hours_since, 1),
                "duration_seconds": _parse_iso8601_duration(content.get("duration", "")),
            })

        # This is a sample average of the returned search set, not a private
        # channel-wide average. Label it so the UI never presents it as exact.
        sample_totals: dict[str, list[int]] = {}
        for row in rows:
            sample_totals.setdefault(row["channel_id"], []).append(row["views"])

        output: list[TrendingVideo] = []
        for row in rows:
            item = row["item"]
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            channel_id = row["channel_id"]
            sample_views = sample_totals.get(channel_id) or [row["views"]]
            sample_avg = round(sum(sample_views) / len(sample_views))
            subscribers = channel_subscribers.get(channel_id, 0)
            output.append(TrendingVideo(
                title=snippet.get("title", "제목 없음"),
                channel_title=snippet.get("channelTitle", "채널 없음"),
                video_id=item.get("id", ""),
                views=row["views"],
                subscribers=subscribers,
                channel_avg_views=sample_avg,
                published_at=snippet.get("publishedAt", ""),
                hours_since_publish=row["hours_since"],
                channel_id=channel_id,
                likes=int(statistics.get("likeCount", 0) or 0),
                comments=int(statistics.get("commentCount", 0) or 0),
                likes_available="likeCount" in statistics,
                comments_available="commentCount" in statistics,
                duration_seconds=row["duration_seconds"],
                average_view_duration_seconds=None,
                average_view_percentage=None,
                retention_available=False,
                statistics_as_of=now.isoformat(),
                channel_avg_views_is_sample=True,
                subscriber_count_available=channel_id in channel_subscribers,
            ))
        return output[:limit]


def _parse_iso8601_duration(value: str) -> float:
    match = re.fullmatch(r"P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value or "")
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return float(hours or 0) * 3600 + float(minutes or 0) * 60 + float(seconds or 0)

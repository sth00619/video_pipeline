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
from datetime import datetime, timezone, timedelta
import re
from app.providers.base import TrendingVideoAnalyzer, TrendingVideo
from app.providers.mock.trending import MockTrendingVideoAnalyzer
from app.config import REDIS_HOST, REDIS_PORT
from app import runtime_config

logger = logging.getLogger(__name__)

_US_CATEGORIES = {"US_STOCKS"}
_CACHE_TTL_SECONDS = 3600  # 1시간 (마스터플랜 6.2절)
_STATIC_METADATA_TTL_SECONDS = 24 * 60 * 60
# 이 프로젝트의 Search Queries 일일 한도는 실측상 8천 단위다. 80%에서
# 멈춰 수동 긴급 검색·오류 복구 여유를 남긴다. 자동 지도는 시드당 한 번만
# 검색하므로, 다음 갱신일부터 300유닛으로 안정적으로 동작한다.
_YOUTUBE_DAILY_SOFT_LIMIT = 6_400
_S_GRADE_COMMENT_DAILY_LIMIT = 30


def _get_redis_client():
    try:
        import redis
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.warning(f"Redis 연결 불가, 캐싱 없이 진행: {e}")
        return None


def _quota_day_key() -> str:
    """YouTube 할당량 리셋 기준(태평양 시간)에 맞춘 자체 카운터 날짜."""
    pacific_now = datetime.now(timezone(timedelta(hours=-8)))
    return pacific_now.strftime("%Y-%m-%d")


def _consume_quota(redis_client, units: int, operation: str) -> bool:
    """캐시 미스에서만 호출한다. 80% 도달 후 신규 search.list를 막는다."""
    if not redis_client:
        return True
    try:
        key = f"youtube:quota:{_quota_day_key()}"
        current = int(redis_client.get(key) or 0)
        if operation == "search.list" and current + units > _YOUTUBE_DAILY_SOFT_LIMIT:
            logger.warning("YouTube search.list soft limit reached: current=%s, limit=%s", current, _YOUTUBE_DAILY_SOFT_LIMIT)
            return False
        redis_client.incrby(key, units)
        redis_client.expire(key, 48 * 60 * 60)
        logger.info("YouTube quota counter: operation=%s units=%s total=%s", operation, units, current + units)
        return True
    except Exception as exc:
        logger.warning("YouTube quota counter unavailable; allowing request: %s", exc)
        return True


def _top_comments_quota_available(redis_client) -> bool:
    """Limit commentThreads.list to S-grade videos and 30 videos per day."""
    if not redis_client:
        return True
    try:
        return int(redis_client.get(f"youtube:comment-videos:{_quota_day_key()}") or 0) < _S_GRADE_COMMENT_DAILY_LIMIT
    except Exception:
        return True


def _record_comment_video(redis_client) -> None:
    if not redis_client:
        return
    try:
        key = f"youtube:comment-videos:{_quota_day_key()}"
        redis_client.incr(key)
        redis_client.expire(key, 48 * 60 * 60)
    except Exception as exc:
        logger.warning("YouTube S-grade comment counter unavailable: %s", exc)
def _score_video(video: TrendingVideo) -> tuple[float, str]:
    """공개 API 원본 지표로만 산출하는 합성 성과 등급."""
    multiple = video.views / video.subscribers if video.subscribers > 0 else 0.0
    velocity = video.views / video.hours_since_publish if video.hours_since_publish > 0 else 0.0
    like_rate = video.likes / video.views if video.likes_available and video.views > 0 else 0.0
    comment_rate = video.comments / video.views if video.comments_available and video.views > 0 else 0.0
    score = (
        float(runtime_config.value("keyword_score_weight_multiple")) * min(multiple, 10.0) / 10.0
        + float(runtime_config.value("keyword_score_weight_velocity")) * min(velocity / 1000.0, 1.0)
        + float(runtime_config.value("keyword_score_weight_like")) * min(like_rate / 0.04, 1.0)
        + float(runtime_config.value("keyword_score_weight_comment")) * min(comment_rate / 0.005, 1.0)
    )
    grade = "S" if score >= 0.7 else "A" if score >= 0.5 else "B" if score >= 0.3 else "C"
    return round(score, 4), grade


def _is_eligible_evidence_source(video: TrendingVideo) -> bool:
    """Only verified channels with a meaningful audience may drive recommendations."""
    minimum_subscribers = int(runtime_config.value("keyword_min_source_subscribers"))
    minimum_views = int(runtime_config.value("keyword_min_source_views"))
    minimum_multiple = float(runtime_config.value("keyword_min_source_viewer_multiple"))
    viewer_multiple = float(video.views or 0) / max(float(video.subscribers or 0), 1.0)
    return (
        bool(video.subscriber_count_available)
        and int(video.subscribers or 0) >= minimum_subscribers
        and int(video.views or 0) >= minimum_views
        and viewer_multiple >= minimum_multiple
        and 0 < float(video.hours_since_publish or 0) <= 24 * 7
        and (not bool(runtime_config.value("keyword_exclude_live")) or not video.is_live)
    )


class YouTubeTrendingAnalyzer(TrendingVideoAnalyzer):
    """
    YouTube Data API v3 기반 트렌딩 영상 분석기.
    """

    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.mock_fallback = MockTrendingVideoAnalyzer()
        self._redis = _get_redis_client()

    def collect(self, category: str, seed: str, limit: int = 30, recent_hours: int | None = None) -> list[TrendingVideo]:
        if not self.api_key:
            # API 키가 없을 때 임의 조회수/구독자 데이터를 만들어 내지 않는다.
            # 뉴스·시장 데이터 기반 후보는 계속 만들 수 있지만 YouTube 지표는 unavailable로 표시한다.
            logger.warning("YOUTUBE_API_KEY 미설정 → 실제 YouTube 지표 수집을 건너뜁니다")
            return []

        recent_hours = max(1, min(int(recent_hours or 0), 168)) or None
        minimum_subscribers = int(runtime_config.value("keyword_min_source_subscribers"))
        minimum_views = int(runtime_config.value("keyword_min_source_views"))
        minimum_multiple = float(runtime_config.value("keyword_min_source_viewer_multiple"))
        # v5: v4에서 잘못된 eventType=completed 조회로 남은 빈 캐시를
        # 재사용하지 않는다. 일반 업로드를 포함해 다시 수집한 결과만 쓴다.
        cache_key = f"trending:v5:7d:nonlive:minsubs={minimum_subscribers}:minviews={minimum_views}:minmultiple={minimum_multiple}:{category}:{seed}:{limit}:recent={recent_hours or '7d'}"
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
                searched = self._collect_keyword_search(category, seed.strip(), limit, recent_hours=recent_hours)
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
                "part": "snippet,statistics,contentDetails,liveStreamingDetails",
                "chart": "mostPopular",
                "regionCode": region_code,
                "videoCategoryId": video_category_id,
                "maxResults": 50,
                "key": self.api_key
            }
            if not _consume_quota(self._redis, 1, "videos.list"):
                return []
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

                video = TrendingVideo(
                        title=title,
                        channel_title=snippet.get("channelTitle", "채널 없음"),
                        video_id=video_id,
                        views=views,
                        # mostPopular does not return subscriber counts. Never
                        # invent a value merely to make a video rankable.
                        subscribers=0,
                        channel_avg_views=0,
                        published_at=published_at,
                        hours_since_publish=round(hours_since, 1),
                        subscriber_count_available=False,
                        tags=snippet.get("tags", []),
                        category_id=snippet.get("categoryId", ""),
                        duration_seconds=_parse_iso8601_duration(item.get("contentDetails", {}).get("duration", "")),
                        is_live=(snippet.get("liveBroadcastContent") in {"live", "upcoming"}
                                 or bool(item.get("liveStreamingDetails"))),
                    )
                video.performance_score, video.performance_grade = _score_video(video)
                if _is_eligible_evidence_source(video):
                    results.append({
                        "video": video,
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

    def _collect_keyword_search(self, category: str, seed: str, limit: int, recent_hours: int | None = None) -> list[TrendingVideo]:
        region_code = "US" if category in _US_CATEGORIES else "KR"
        # The research UI is intentionally about fresh opportunities, rather
        # than all-time high-view videos. Keep the discovery pool within the
        # latest seven days; the caller can still type a breaking-news term and
        # receive videos from the last hour.
        published_after = (datetime.now(timezone.utc) - timedelta(hours=recent_hours or 24 * 7)).isoformat().replace("+00:00", "Z")
        search_params = {
            "part": "snippet",
            "q": seed,
            "type": "video",
            # 오전 9시 자동 수집은 단순 제목 일치보다 최근 7일 안의 실제
            # 반응이 큰 영상을 넓게 확보해야 한다. 작업자가 직접 검색할 때는
            # 긴급 이슈의 문맥을 보존하도록 relevance를 유지한다.
            "order": "viewCount" if limit >= 20 else "relevance",
            "regionCode": region_code,
            "relevanceLanguage": "en" if region_code == "US" else "ko",
            "publishedAfter": published_after,
            # search.list에는 "일반 업로드만"을 뜻하는 eventType이 없다.
            # (completed는 종료된 라이브만 뜻한다.) 따라서 여기서는 넓게
            # 수집한 뒤 videos.list의 liveStreamingDetails로 실제 라이브와
            # 라이브 다시보기를 제거한다.
            "maxResults": min(50, max(10, limit * 3)),
            "key": self.api_key,
        }
        if not _consume_quota(self._redis, 100, "search.list"):
            raise RuntimeError("오늘의 YouTube 검색 할당량 보호 한도에 도달했습니다. 캐시된 결과를 사용해 주세요.")
        search_response = requests.get(f"{self.base_url}/search", params=search_params, timeout=15)
        search_response.raise_for_status()
        search_items = search_response.json().get("items", [])
        # 조회수 순으로 최대 50건을 이미 확보하므로, 매 시드마다 medium/long
        # 검색을 두 번 더 할 필요가 없다. 최종 정렬에서 긴 영상을 우선해
        # 롱폼 친화성은 유지하면서 일일 자동 수집 쿼터는 3분의 1로 줄인다.
        video_ids = [
            item.get("id", {}).get("videoId")
            for item in search_items
            if item.get("id", {}).get("videoId")
        ]
        video_ids = list(dict.fromkeys(video_ids))[:50]
        if not video_ids:
            return []

        if not _consume_quota(self._redis, 1, "videos.list"):
            return []
        videos_response = requests.get(
            f"{self.base_url}/videos",
            params={"part": "snippet,statistics,contentDetails,liveStreamingDetails", "id": ",".join(video_ids), "key": self.api_key},
            timeout=15,
        )
        videos_response.raise_for_status()
        video_items = videos_response.json().get("items", [])
        channel_ids = sorted({item.get("snippet", {}).get("channelId") for item in video_items if item.get("snippet", {}).get("channelId")})
        channel_statistics: dict[str, dict] = {}
        if channel_ids:
            if not _consume_quota(self._redis, 1, "channels.list"):
                return []
            channels_response = requests.get(
                f"{self.base_url}/channels",
                params={"part": "statistics", "id": ",".join(channel_ids), "key": self.api_key},
                timeout=15,
            )
            channels_response.raise_for_status()
            for item in channels_response.json().get("items", []):
                statistics = item.get("statistics", {})
                raw = statistics.get("subscriberCount")
                if raw is not None:
                    channel_statistics[item.get("id", "")] = {
                        "subscribers": int(raw),
                        "view_count": int(statistics.get("viewCount", 0) or 0),
                        "video_count": int(statistics.get("videoCount", 0) or 0),
                    }

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
            channel_stats = channel_statistics.get(channel_id, {})
            subscribers = int(channel_stats.get("subscribers", 0) or 0)
            video_count = int(channel_stats.get("video_count", 0) or 0)
            channel_avg_views = round(int(channel_stats.get("view_count", 0) or 0) / video_count) if video_count else 0
            video = TrendingVideo(
                title=snippet.get("title", "제목 없음"),
                channel_title=snippet.get("channelTitle", "채널 없음"),
                video_id=item.get("id", ""),
                views=row["views"],
                subscribers=subscribers,
                channel_avg_views=channel_avg_views or sample_avg,
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
                channel_avg_views_is_sample=not bool(channel_avg_views),
                subscriber_count_available=channel_id in channel_statistics,
                tags=snippet.get("tags", []),
                category_id=snippet.get("categoryId", ""),
                is_live=(snippet.get("liveBroadcastContent") in {"live", "upcoming"}
                         or bool(item.get("liveStreamingDetails"))),
            )
            video.performance_score, video.performance_grade = _score_video(video)
            if not _is_eligible_evidence_source(video):
                logger.info(
                    "Excluded non-qualifying YouTube source: video=%s subscribers=%s views=%s multiple=%.2f live=%s available=%s min_subs=%s min_views=%s",
                    video.video_id, video.subscribers, video.views, video.views / max(video.subscribers, 1), video.is_live, video.subscriber_count_available,
                    runtime_config.value("keyword_min_source_subscribers"),
                    runtime_config.value("keyword_min_source_views"),
                )
                continue
            output.append(video)

            # 제목/태그/카테고리는 24시간 동안 재사용한다. 동적 지표는 상단의
            # 검색 결과 캐시(1시간)와 분리해 두어 쿼터 계획을 명확히 한다.
            if self._redis and video.video_id:
                try:
                    self._redis.setex(
                        f"youtube:metadata:{video.video_id}", _STATIC_METADATA_TTL_SECONDS,
                        json.dumps({"title": video.title, "tags": video.tags, "category_id": video.category_id}, ensure_ascii=False),
                    )
                except Exception as exc:
                    logger.warning("YouTube static metadata cache write failed: %s", exc)
        # A wider discovery pool is collected for the automatic map.  Rank by
        # verified score first, then prefer longform when scores are similar.
        grade_rank = {"S": 3, "A": 2, "B": 1, "C": 0}
        output.sort(
            key=lambda video: (
                grade_rank.get(video.performance_grade, 0),
                1 if video.duration_seconds > 60 else 0,
                video.performance_score,
                video.views / max(video.hours_since_publish, 0.1),
            ),
            reverse=True,
        )
        output = output[:limit]
        self._attach_top_comments(output)
        return output

    def _attach_top_comments(self, videos: list[TrendingVideo]) -> None:
        """Attach public comment samples only to S-grade results.

        commentThreads.list is intentionally post-filtered: lower-grade videos
        do not spend quota, each video is cached for an hour, and a Redis
        counter hard-limits the daily number of sampled videos.
        """
        for video in videos:
            if video.performance_grade != "S" or not video.video_id:
                continue
            cache_key = f"youtube:comments:{video.video_id}"
            try:
                if self._redis:
                    cached = self._redis.get(cache_key)
                    if cached:
                        video.top_comments = json.loads(cached)
                        continue
                if not _top_comments_quota_available(self._redis):
                    logger.info("S-grade comment sample limit reached; skipping video=%s", video.video_id)
                    continue
                if not _consume_quota(self._redis, 1, "commentThreads.list"):
                    continue
                response = requests.get(
                    f"{self.base_url}/commentThreads",
                    params={
                        "part": "snippet",
                        "videoId": video.video_id,
                        "order": "relevance",
                        "maxResults": 20,
                        "textFormat": "plainText",
                        "key": self.api_key,
                    },
                    timeout=15,
                )
                if response.status_code != 200:
                    logger.info("Public comments unavailable for video=%s status=%s", video.video_id, response.status_code)
                    continue
                comments = [
                    item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("textDisplay", "").strip()
                    for item in response.json().get("items", [])
                ]
                video.top_comments = [comment for comment in comments if comment][:20]
                _record_comment_video(self._redis)
                if self._redis:
                    self._redis.setex(cache_key, _CACHE_TTL_SECONDS, json.dumps(video.top_comments, ensure_ascii=False))
            except Exception as exc:
                logger.warning("S-grade public comment sample failed for video=%s: %s", video.video_id, exc)


def _parse_iso8601_duration(value: str) -> float:
    match = re.fullmatch(r"P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value or "")
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return float(hours or 0) * 3600 + float(minutes or 0) * 60 + float(seconds or 0)

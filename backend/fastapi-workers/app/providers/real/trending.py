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
import hashlib
import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
import re
from urllib.parse import urlparse
from app.providers.base import TrendingVideoAnalyzer, TrendingVideo
from app.providers.mock.trending import MockTrendingVideoAnalyzer
from app.config import REDIS_HOST, REDIS_PORT
from app import config, runtime_config

logger = logging.getLogger(__name__)

_US_CATEGORIES = {"US_STOCKS"}
_CACHE_TTL_SECONDS = 3600  # 1시간 (마스터플랜 6.2절)
_STATIC_METADATA_TTL_SECONDS = 24 * 60 * 60
# Search Queries 전용 버킷은 공유 쿼터와 분리해 일일 호출 횟수로 관리한다.
_SEARCH_QUOTA_DAILY_LIMIT = 100
_SEARCH_QUOTA_WARNING_AT = 80  # 일일 한도의 80%부터 운영 경고
_S_GRADE_COMMENT_DAILY_LIMIT = 30
_BENCHMARK_CACHE_TTL_SECONDS = 6 * 60 * 60
_BENCHMARK_NOT_FOUND_TTL_SECONDS = 10 * 60


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


def _normalize_recent_hours(recent_hours: int | None) -> int:
    """기본 수집 기간은 7일이며 명시값은 1~168시간으로 제한한다."""
    if recent_hours is None:
        return 24 * 7
    return max(1, min(int(recent_hours), 24 * 7))


def _benchmark_error(channel_id: str, code: str, message: str) -> dict:
    """채널 조회 실패를 0명 통계가 아닌 명시적 오류 행으로 표현한다."""
    return {
        "channel_id": channel_id,
        "status": "error",
        "error_code": code,
        "error_message": message,
        "title": None,
        "subscriber_count": None,
        "subscriber_count_available": False,
        "hidden_subscriber_count": None,
        "total_view_count": None,
        "video_count": None,
        "avg_views_recent_10": None,
        "upload_gap_days": None,
        "recent_videos": [],
    }


def _benchmark_cache_key(channel_ids: list[str]) -> str:
    """입력 순서를 보존하면서 채널 ID와 API 키를 노출하지 않는 v2 캐시 키."""
    ordered = "|".join(channel_ids)
    digest = hashlib.sha256(ordered.encode("utf-8")).hexdigest()[:20]
    return f"youtube:benchmark:v2:{digest}"


def _channel_lookup_params(channel_ref: str) -> dict[str, str]:
    """채널 ID, @handle, YouTube 채널 URL을 channels.list 필터로 변환한다."""
    value = (channel_ref or "").strip()
    if not value:
        raise ValueError("채널 ID 또는 @handle 형식이 필요합니다.")

    candidate_url = value
    if value.startswith(("youtube.com/", "www.youtube.com/", "m.youtube.com/")):
        candidate_url = f"https://{value}"
    if candidate_url.startswith(("http://", "https://")):
        parsed = urlparse(candidate_url)
        host = (parsed.hostname or "").lower()
        if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            raise ValueError("지원하는 YouTube 채널 URL이 아닙니다.")
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0].startswith("@"):
            return {"forHandle": parts[0]}
        if len(parts) >= 2 and parts[0] == "channel" and parts[1].startswith("UC"):
            return {"id": parts[1]}
        raise ValueError("youtube.com/@handle 또는 youtube.com/channel/UC... 형식이 필요합니다.")

    if value.startswith("UC"):
        return {"id": value}
    if value.startswith("@") and len(value) > 1:
        return {"forHandle": value}
    raise ValueError("채널 ID 또는 @handle 형식이 필요합니다.")


def _resolved_channel(item: dict) -> dict:
    """channels.list 원본을 저장 전 사람 확인용 공개 필드로 정규화한다."""
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    hidden = bool(stats.get("hiddenSubscriberCount", False))
    subscriber_count = None if hidden or "subscriberCount" not in stats else int(stats["subscriberCount"])
    thumbnails = snippet.get("thumbnails", {})
    thumbnail = (
        thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url")
    )
    return {
        "channel_id": item.get("id"),
        "title": snippet.get("title", ""),
        "handle": snippet.get("customUrl"),
        "description": snippet.get("description", ""),
        "thumbnail_url": thumbnail,
        "subscriber_count": subscriber_count,
        "subscriber_count_available": subscriber_count is not None,
        "hidden_subscriber_count": hidden,
        "total_view_count": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
    }


def _consume_quota(redis_client, units: int, operation: str) -> bool:
    """search.list를 제외한 YouTube Data API 공유 쿼터를 기록한다."""
    if not redis_client:
        return True
    try:
        key = f"youtube:quota:{_quota_day_key()}"
        current = int(redis_client.get(key) or 0)
        redis_client.incrby(key, units)
        redis_client.expire(key, 48 * 60 * 60)
        logger.info("YouTube quota counter: operation=%s units=%s total=%s", operation, units, current + units)
        return True
    except Exception as exc:
        logger.warning("YouTube quota counter unavailable; allowing request: %s", exc)
        return True


def _consume_search_quota(redis_client) -> bool:
    """search.list 전용 일일 호출 버킷을 원자적으로 차감한다.

    Redis 키는 공유 풀과 별개인 ``youtube:quota:search:{YYYY-MM-DD}``이며,
    100회까지 허용하고 101번째 시도는 차감을 취소한 뒤 차단한다.
    """
    if redis_client is None:
        return True
    try:
        key = f"youtube:quota:search:{_quota_day_key()}"
        used = int(redis_client.incr(key))
        redis_client.expire(key, 24 * 60 * 60)

        if used > _SEARCH_QUOTA_DAILY_LIMIT:
            redis_client.decr(key)
            logger.error(
                "YouTube search quota exhausted: %d/%d calls today — blocking.",
                used - 1,
                _SEARCH_QUOTA_DAILY_LIMIT,
            )
            return False

        if used >= _SEARCH_QUOTA_WARNING_AT:
            logger.warning(
                "YouTube search quota warning: used=%d/%d calls today",
                used,
                _SEARCH_QUOTA_DAILY_LIMIT,
            )
        logger.info(
            "YouTube search quota: used=%d/%d calls today (Search Queries bucket)",
            used,
            _SEARCH_QUOTA_DAILY_LIMIT,
        )
        return True
    except Exception as exc:
        logger.warning("YouTube search quota counter unavailable; allowing request: %s", exc)
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
    metadata_eligible = (
        bool(video.subscriber_count_available)
        and int(video.subscribers or 0) >= minimum_subscribers
        and int(video.views or 0) >= minimum_views
        and 0 < float(video.hours_since_publish or 0) <= 24 * 7
        and (not bool(runtime_config.value("keyword_exclude_live")) or not video.is_live)
    )
    return metadata_eligible and _is_high_response_video(video)[0]


def _viewer_ratio_threshold(subscriber_count: int) -> float:
    """자기평균 표본이 부족할 때 적용할 구독자 규모별 최소 조회율."""
    if subscriber_count >= 1_000_000:
        return 0.003
    if subscriber_count >= 300_000:
        return 0.006
    if subscriber_count >= 50_000:
        return 0.010
    return 0.020


def _fetch_channel_baseline(
    analyzer: "YouTubeTrendingAnalyzer",
    channel_id: str,
) -> tuple[int, int]:
    """채널 최근 일반영상의 평균 조회수와 표본 수를 반환한다."""
    cache_key = f"youtube:channel-baseline:v1:{channel_id}"
    if analyzer._redis:
        try:
            cached = analyzer._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                average_views = int(data.get("average_views", 0) or 0)
                sample_size = int(data.get("sample_size", 0) or 0)
                logger.info(
                    "YouTube recent baseline: channel_id=%s source=cache "
                    "sample_size=%d playlist_calls=0 videos_calls=0 shared_units=0",
                    channel_id,
                    sample_size,
                )
                return average_views, sample_size
        except Exception as exc:
            logger.warning("Baseline cache read failed for %s: %s", channel_id, exc)

    if not _consume_quota(analyzer._redis, 1, "channels.list"):
        return 0, 0
    channel_response = requests.get(
        f"{analyzer.base_url}/channels",
        params={"part": "contentDetails", "id": channel_id, "key": analyzer.api_key},
        timeout=15,
    )
    if getattr(channel_response, "status_code", 200) != 200:
        return 0, 0
    channel_items = channel_response.json().get("items", [])
    if not channel_items:
        return 0, 0
    uploads_id = (
        channel_items[0]
        .get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )
    if not uploads_id:
        return 0, 0

    if not _consume_quota(analyzer._redis, 1, "playlistItems.list"):
        return 0, 0
    playlist_response = requests.get(
        f"{analyzer.base_url}/playlistItems",
        params={
            "part": "contentDetails",
            "playlistId": uploads_id,
            "maxResults": 50,
            "key": analyzer.api_key,
        },
        timeout=15,
    )
    if getattr(playlist_response, "status_code", 200) != 200:
        return 0, 0
    video_ids = [
        item.get("contentDetails", {}).get("videoId")
        for item in playlist_response.json().get("items", [])
        if item.get("contentDetails", {}).get("videoId")
    ]
    if not video_ids:
        return 0, 0

    if not _consume_quota(analyzer._redis, 1, "videos.list"):
        return 0, 0
    videos_response = requests.get(
        f"{analyzer.base_url}/videos",
        params={
            "part": "snippet,statistics,contentDetails,liveStreamingDetails",
            "id": ",".join(video_ids[:50]),
            "key": analyzer.api_key,
        },
        timeout=15,
    )
    if getattr(videos_response, "status_code", 200) != 200:
        return 0, 0

    video_items_by_id = {
        item.get("id"): item
        for item in videos_response.json().get("items", [])
        if item.get("id")
    }
    eligible_views: list[int] = []
    # videos.list 응답 순서에 의존하지 않고 uploads 재생목록의 최신순을 보존한다.
    for video_id in video_ids:
        item = video_items_by_id.get(video_id)
        if not item:
            continue
        duration_seconds = _parse_iso8601_duration(
            item.get("contentDetails", {}).get("duration", "PT0S")
        )
        is_live = (
            item.get("snippet", {}).get("liveBroadcastContent") in {"live", "upcoming"}
            or bool(item.get("liveStreamingDetails"))
        )
        if duration_seconds < 240 or is_live:
            continue
        try:
            eligible_views.append(int(item.get("statistics", {})["viewCount"]))
        except (KeyError, TypeError, ValueError):
            continue

    sample = eligible_views[:30]
    average_views = round(sum(sample) / len(sample)) if sample else 0
    sample_size = len(sample)
    logger.info(
        "YouTube recent baseline: channel_id=%s source=api "
        "sample_size=%d playlist_calls=1 videos_calls=1 shared_units=3",
        channel_id,
        sample_size,
    )

    if analyzer._redis and sample_size > 0:
        try:
            analyzer._redis.setex(
                cache_key,
                6 * 60 * 60,
                json.dumps(
                    {
                        "channel_id": channel_id,
                        "average_views": average_views,
                        "sample_size": sample_size,
                        "criteria": "duration>=240, non-live",
                        "calculated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning("Baseline cache write failed for %s: %s", channel_id, exc)

    return average_views, sample_size


def _is_high_response_video(video: TrendingVideo) -> tuple[bool, str]:
    """최소 조회수와 자기평균 또는 규모별 조회율로 성과를 판정한다."""
    views = int(video.views or 0)
    subscribers = int(video.subscribers or 0)
    if views < int(config.KEYWORD_MIN_SOURCE_VIEWS):
        return False, "minimum_views"

    baseline_count = int(video.channel_recent_sample_size or 0)
    baseline_average = int(video.channel_recent_avg_views or 0)
    if (
        baseline_count >= int(config.KEYWORD_OUTPERFORMER_MIN_BASELINE_COUNT)
        and baseline_average > 0
    ):
        required_views = baseline_average * float(config.KEYWORD_OUTPERFORMER_RECENT_MULTIPLE)
        return views >= required_views, "recent_average_1_5x"

    threshold = _viewer_ratio_threshold(subscribers)
    return views / max(subscribers, 1) >= threshold, "tiered_ratio"


def _is_eligible_exploration_source(video: TrendingVideo, ranking: str, min_subscribers: int | None) -> bool:
    """Keep research browsing broad while excluding unreliable or live sources.

    ``evidence`` remains deliberately strict because it drives automatic
    recommendations. The dashboard's large-channel tabs serve a different
    purpose: inspecting editorial formats used by established channels, so
    their videos must not be discarded just because an upload has not yet
    reached a fixed percentage of the channel's subscriber base.
    """
    if not video.subscriber_count_available:
        return False
    if not (0 < float(video.hours_since_publish or 0) <= 24 * 7):
        return False
    if bool(runtime_config.value("keyword_exclude_live")) and video.is_live:
        return False

    if ranking == "large_channel":
        return int(video.subscribers or 0) >= max(0, int(min_subscribers or 0))

    # Avoid surfacing a one-off upload from an unestablished channel in the
    # view/subscriber comparison, while intentionally keeping this much wider
    # than the automatic-evidence threshold.
    return (
        int(video.subscribers or 0) >= 3_000
        and int(video.views or 0) >= 500
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

    def collect(
        self,
        category: str,
        seed: str,
        limit: int = 30,
        recent_hours: int | None = None,
        ranking: str = "evidence",
        min_subscribers: int | None = None,
    ) -> list[TrendingVideo]:
        if not self.api_key:
            # API 키가 없을 때 임의 조회수/구독자 데이터를 만들어 내지 않는다.
            # 뉴스·시장 데이터 기반 후보는 계속 만들 수 있지만 YouTube 지표는 unavailable로 표시한다.
            logger.warning("YOUTUBE_API_KEY 미설정 → 실제 YouTube 지표 수집을 건너뜁니다")
            return []

        requested_recent_hours = recent_hours
        recent_hours = _normalize_recent_hours(recent_hours)
        logger.info(
            "YouTube search window: requested=%s normalized=%s",
            requested_recent_hours,
            recent_hours,
        )
        minimum_subscribers = int(runtime_config.value("keyword_min_source_subscribers"))
        minimum_views = int(runtime_config.value("keyword_min_source_views"))
        recent_multiple = float(config.KEYWORD_OUTPERFORMER_RECENT_MULTIPLE)
        minimum_baseline_count = int(config.KEYWORD_OUTPERFORMER_MIN_BASELINE_COUNT)
        baseline_cap = int(config.KEYWORD_OUTPERFORMER_BASELINE_CAP_PER_REQ)
        # v5: v4에서 잘못된 eventType=completed 조회로 남은 빈 캐시를
        # 재사용하지 않는다. 일반 업로드를 포함해 다시 수집한 결과만 쓴다.
        ranking = ranking if ranking in {"evidence", "outperformer", "large_channel"} else "evidence"
        requested_min_subscribers = max(0, int(min_subscribers or 0))
        cache_key = (
            f"trending:v7:7d:{ranking}:requested-minsubs={requested_min_subscribers}:"
            f"nonlive:minsubs={minimum_subscribers}:minviews={minimum_views}:"
            f"recentmultiple={recent_multiple}:baselinecount={minimum_baseline_count}:"
            f"baselinecap={baseline_cap}:{category}:{seed}:{limit}:recent={recent_hours}"
        )
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
                searched = self._collect_keyword_search(
                    category,
                    seed.strip(),
                    limit,
                    recent_hours=recent_hours,
                    ranking=ranking,
                    min_subscribers=requested_min_subscribers,
                )
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

    def _collect_keyword_search(
        self,
        category: str,
        seed: str,
        limit: int,
        recent_hours: int | None = None,
        ranking: str = "evidence",
        min_subscribers: int | None = None,
    ) -> list[TrendingVideo]:
        region_code = "US" if category in _US_CATEGORIES else "KR"
        # The research UI is intentionally about fresh opportunities, rather
        # than all-time high-view videos. Keep the discovery pool within the
        # latest seven days; the caller can still type a breaking-news term and
        # receive videos from the last hour.
        published_after = (datetime.now(timezone.utc) - timedelta(hours=recent_hours or 24 * 7)).isoformat().replace("+00:00", "Z")
        base_search_params = {
            "part": "snippet",
            "q": seed,
            "type": "video",
            # 오전 9시 자동 수집은 단순 제목 일치보다 최근 7일 안의 실제
            # 반응이 큰 영상을 넓게 확보해야 한다. 작업자가 직접 검색할 때는
            # 긴급 이슈의 문맥을 보존하도록 relevance를 유지한다.
            # Large-channel research is about recently used editorial formats,
            # not only established hits. Outperformer/evidence searches remain
            # view-led so high-response videos are represented in the pool.
            "order": "date" if ranking == "large_channel" else ("viewCount" if ranking == "outperformer" or limit >= 20 else "relevance"),
            "regionCode": region_code,  # 한국 카테고리는 KR, 미국 주식은 US를 두 검색에 공통 적용
            "relevanceLanguage": "en" if region_code == "US" else "ko",
            "publishedAfter": published_after,
            # search.list에는 "일반 업로드만"을 뜻하는 eventType이 없다.
            # (completed는 종료된 라이브만 뜻한다.) 따라서 여기서는 넓게
            # 수집한 뒤 videos.list의 liveStreamingDetails로 실제 라이브와
            # 라이브 다시보기를 제거한다.
            "maxResults": min(50, max(10, limit * 3)),
            "key": self.api_key,
        }
        if not _consume_search_quota(self._redis):
            raise RuntimeError("오늘의 YouTube 검색 할당량 보호 한도에 도달했습니다. 캐시된 결과를 사용해 주세요.")
        long_response = requests.get(
            f"{self.base_url}/search",
            params={**base_search_params, "videoDuration": "long"},
            timeout=15,
        )
        long_response.raise_for_status()
        long_items = long_response.json().get("items", [])

        # 4~20분 영상도 연구 후보에 포함하되, 두 번째 검색은 best-effort로
        # 처리한다. medium 쿼터나 요청이 실패해도 먼저 확보한 long 결과는
        # 그대로 후속 videos.list와 점수 계산에 전달한다.
        medium_items: list[dict] = []
        if _consume_search_quota(self._redis):
            try:
                medium_response = requests.get(
                    f"{self.base_url}/search",
                    params={**base_search_params, "videoDuration": "medium"},
                    timeout=15,
                )
                medium_response.raise_for_status()
                medium_items = medium_response.json().get("items", [])
                logger.info("YouTube search window: medium call got %d items", len(medium_items))
            except Exception as exc:
                logger.warning(
                    "YouTube medium search failed — long-only results returned: %s",
                    exc,
                )
        else:
            logger.warning(
                "YouTube search quota exhausted — medium search skipped, long-only results returned"
            )

        # 같은 영상이 두 검색에 모두 포함되면 먼저 수집한 long 결과를
        # 유지한다. videos.list 이후 단계는 병합 ID에 대해 한 번만 실행한다.
        seen_ids: set[str] = set()
        merged_items: list[dict] = []
        for item in long_items + medium_items:
            video_id = item.get("id", {}).get("videoId")
            if video_id and video_id not in seen_ids:
                seen_ids.add(video_id)
                merged_items.append(item)

        logger.info(
            "YouTube search merge: long=%d medium=%d merged=%d",
            len(long_items),
            len(medium_items),
            len(merged_items),
        )
        video_ids = [
            item.get("id", {}).get("videoId")
            for item in merged_items
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
        baseline_by_channel: dict[str, tuple[int, int]] = {}
        baseline_attempts = 0
        baseline_cap = max(0, int(config.KEYWORD_OUTPERFORMER_BASELINE_CAP_PER_REQ))
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
            if video.duration_seconds < 240:
                continue

            if ranking in {"evidence", "outperformer"}:
                normalized_channel_id = (video.channel_id or "").strip()
                if normalized_channel_id and normalized_channel_id not in baseline_by_channel:
                    if baseline_attempts < baseline_cap:
                        baseline_attempts += 1
                        try:
                            baseline_by_channel[normalized_channel_id] = _fetch_channel_baseline(
                                self,
                                normalized_channel_id,
                            )
                        except Exception as exc:
                            logger.warning(
                                "YouTube recent baseline failed; tiered fallback used: "
                                "channel_id=%s error=%s",
                                normalized_channel_id,
                                type(exc).__name__,
                            )
                            baseline_by_channel[normalized_channel_id] = (0, 0)
                    else:
                        baseline_by_channel[normalized_channel_id] = (0, 0)
                average_views, sample_size = baseline_by_channel.get(normalized_channel_id, (0, 0))
                video.channel_recent_avg_views = average_views or None
                video.channel_recent_sample_size = sample_size

            if ranking == "evidence":
                is_eligible = _is_eligible_evidence_source(video)
                video.outperformer_basis = _is_high_response_video(video)[1]
            else:
                is_eligible = _is_eligible_exploration_source(video, ranking, min_subscribers)
                if ranking == "outperformer" and is_eligible:
                    is_eligible, video.outperformer_basis = _is_high_response_video(video)
            if not is_eligible:
                logger.info(
                    "Excluded non-qualifying YouTube source: video=%s subscribers=%s views=%s multiple=%.2f live=%s available=%s min_subs=%s min_views=%s basis=%s baseline_avg=%s baseline_sample=%s",
                    video.video_id, video.subscribers, video.views, video.views / max(video.subscribers, 1), video.is_live, video.subscriber_count_available,
                    min_subscribers if ranking == "large_channel" else runtime_config.value("keyword_min_source_subscribers"),
                    500 if ranking == "outperformer" else runtime_config.value("keyword_min_source_views"),
                    video.outperformer_basis,
                    video.channel_recent_avg_views,
                    video.channel_recent_sample_size,
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
        if ranking == "large_channel":
            output.sort(key=lambda video: (video.hours_since_publish, -video.views))
        elif ranking == "outperformer":
            output.sort(
                key=lambda video: (
                    video.views / max(video.subscribers, 1),
                    video.views / max(video.hours_since_publish, 0.1),
                    video.views,
                ),
                reverse=True,
            )
        else:
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
        if ranking == "evidence":
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

    def get_channel_benchmarks(self, channel_ids: list[str] | None = None) -> list[dict]:
        """
        지정 채널들의 공개 지표를 channels.list + playlistItems.list + videos.list로 조회.
        - 총 유닛 비용: 채널당 ~3 유닛
        - Redis TTL: 6시간 (21,600초)
        - 구독자 수: Google API가 1,000 단위 근사값만 반환 → UI에서 ~ 표기 필요
        """
        # 채널 목록의 단일 기준은 Spring/PostgreSQL이다. worker 내부에서
        # 과거의 잘못된 정적 채널을 fallback으로 되살리지 않는다.
        targets = list(dict.fromkeys(
            channel_id.strip()
            for channel_id in (channel_ids or [])
            if channel_id and channel_id.strip()
        ))

        if not targets:
            return []

        cache_key = _benchmark_cache_key(targets)

        if self._redis:
            try:
                cached = self._redis.get(cache_key)
                if cached:
                    logger.info(f"Redis 캐시 히트 (benchmark): {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis 캐시 조회 실패 (benchmark): {e}")

        if not self.api_key:
            logger.warning("YOUTUBE_API_KEY 미설정 → 채널 벤치마크 수집 건너뜁니다")
            return [
                _benchmark_error(
                    channel_id,
                    "fetch_failed",
                    "YouTube 채널 통계를 사용할 수 없습니다.",
                )
                for channel_id in targets
            ]

        results = []
        for channel_id in targets:
            try:
                if not _consume_quota(self._redis, 1, "channels.list"):
                    logger.warning("YouTube quota limit reached for channels.list")
                    results.append(_benchmark_error(
                        channel_id,
                        "fetch_failed",
                        "채널 통계를 일시적으로 불러오지 못했습니다.",
                    ))
                    continue

                ch_resp = requests.get(
                    f"{self.base_url}/channels",
                    params={
                        "part": "snippet,statistics,contentDetails",
                        "id": channel_id,
                        "key": self.api_key,
                    },
                    timeout=15,
                )
                if ch_resp.status_code != 200:
                    results.append(_benchmark_error(
                        channel_id,
                        "youtube_api_error",
                        f"YouTube 채널 조회 실패({ch_resp.status_code})",
                    ))
                    continue
                ch_json = ch_resp.json()
                if not ch_json.get("items"):
                    results.append(_benchmark_error(
                        channel_id,
                        "channel_not_found",
                        "존재하지 않거나 사용할 수 없는 채널 ID입니다.",
                    ))
                    continue

                ch = ch_json["items"][0]
                snippet = ch.get("snippet", {})
                stats = ch.get("statistics", {})
                hidden_subscriber_count = bool(stats.get("hiddenSubscriberCount", False))
                subscriber_count = (
                    None
                    if hidden_subscriber_count or "subscriberCount" not in stats
                    else int(stats["subscriberCount"])
                )
                uploads_id = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

                recent_videos: list[dict] = []
                if uploads_id:
                    if _consume_quota(self._redis, 1, "playlistItems.list"):
                        pl_resp = requests.get(
                            f"{self.base_url}/playlistItems",
                            params={
                                "part": "contentDetails",
                                "playlistId": uploads_id,
                                "maxResults": 10,
                                "key": self.api_key,
                            },
                            timeout=15,
                        )
                        if pl_resp.status_code == 200:
                            pl_json = pl_resp.json()
                            video_ids = [
                                item["contentDetails"]["videoId"]
                                for item in pl_json.get("items", [])
                                if "contentDetails" in item and "videoId" in item["contentDetails"]
                            ]

                            if video_ids and _consume_quota(self._redis, 1, "videos.list"):
                                v_resp = requests.get(
                                    f"{self.base_url}/videos",
                                    params={
                                        "part": "snippet,statistics,contentDetails",
                                        "id": ",".join(video_ids),
                                        "key": self.api_key,
                                    },
                                    timeout=15,
                                )
                                if v_resp.status_code == 200:
                                    v_json = v_resp.json()
                                    for v in v_json.get("items", []):
                                        recent_videos.append({
                                            "title": v["snippet"].get("title", ""),
                                            "published_at": v["snippet"].get("publishedAt", ""),
                                            "duration": v["contentDetails"].get("duration", ""),
                                            "view_count": int(v["statistics"].get("viewCount", 0)),
                                            "like_count": int(v["statistics"].get("likeCount", 0)),
                                        })

                upload_gap_days: float | None = None
                if len(recent_videos) >= 2:
                    from datetime import datetime
                    dates = sorted(
                        [datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
                         for v in recent_videos if v["published_at"]],
                        reverse=True,
                    )
                    if len(dates) >= 2:
                        gaps = [(dates[i] - dates[i + 1]).days for i in range(len(dates) - 1)]
                        upload_gap_days = round(sum(gaps) / len(gaps), 1)

                avg_views = (
                    round(sum(v["view_count"] for v in recent_videos) / len(recent_videos))
                    if recent_videos else 0
                )

                results.append({
                    "channel_id": channel_id,
                    "status": "ok",
                    "error_code": None,
                    "error_message": None,
                    "title": snippet.get("title", ""),
                    "subscriber_count": subscriber_count,
                    "subscriber_count_available": subscriber_count is not None,
                    "hidden_subscriber_count": hidden_subscriber_count,
                    "total_view_count": int(stats.get("viewCount", 0)),
                    "video_count": int(stats.get("videoCount", 0)),
                    "avg_views_recent_10": avg_views,
                    "upload_gap_days": upload_gap_days,
                    "recent_videos": recent_videos,
                })
            except Exception as exc:
                logger.warning(
                    "[BenchmarkError] channel_id=%s code=fetch_failed exception_type=%s",
                    channel_id,
                    type(exc).__name__,
                )
                results.append(_benchmark_error(
                    channel_id,
                    "fetch_failed",
                    "채널 통계를 일시적으로 불러오지 못했습니다.",
                ))

        if self._redis and results:
            try:
                cacheable = all(
                    row.get("status") == "ok" or row.get("error_code") == "channel_not_found"
                    for row in results
                )
                if cacheable:
                    ttl = (
                        _BENCHMARK_NOT_FOUND_TTL_SECONDS
                        if any(row.get("error_code") == "channel_not_found" for row in results)
                        else _BENCHMARK_CACHE_TTL_SECONDS
                    )
                    self._redis.setex(cache_key, ttl, json.dumps(results, ensure_ascii=False))
            except Exception as exc:
                logger.warning("Redis 캐시 저장 실패 (benchmark): %s", exc)

        return results

    def resolve_channel(self, channel_ref: str) -> dict | None:
        """채널 ID·handle·URL을 search.list 없이 channels.list로 검증한다."""
        if not self.api_key:
            return None
        lookup_params = _channel_lookup_params(channel_ref)
        if not _consume_quota(self._redis, 1, "channels.list"):
            return None
        try:
            response = requests.get(
                f"{self.base_url}/channels",
                params={
                    "part": "snippet,statistics",
                    **lookup_params,
                    "key": self.api_key,
                },
                timeout=15,
            )
            if response.status_code != 200:
                return None
            items = response.json().get("items", [])
            return _resolved_channel(items[0]) if items else None
        except Exception:
            logger.warning("YouTube 채널 검증 요청에 실패했습니다.")
            return None

    def resolve_channel_ids(self, channel_ids: list[str]) -> list[dict]:
        """검색 후보 ID를 실제 공개 통계로 보강하며 입력 순서를 유지한다."""
        resolved: list[dict] = []
        for channel_id in dict.fromkeys(channel_ids):
            candidate = self.resolve_channel(channel_id)
            if candidate is not None:
                resolved.append(candidate)
        return resolved

    def search_channel_candidates(self, query: str, limit: int = 3) -> list[dict]:
        """일반 이름은 전용 검색 버킷으로 후보만 찾고 자동 확정하지 않는다."""
        normalized_query = (query or "").strip()
        if not normalized_query or not self.api_key:
            return []
        if not _consume_search_quota(self._redis):
            raise RuntimeError("오늘의 YouTube 채널 검색 한도에 도달했습니다.")

        try:
            response = requests.get(
                f"{self.base_url}/search",
                params={
                    "part": "snippet",
                    "q": normalized_query,
                    "type": "channel",
                    "maxResults": min(max(int(limit), 1), 3),
                    "regionCode": "KR",
                    "relevanceLanguage": "ko",
                    "key": self.api_key,
                },
                timeout=15,
            )
            response.raise_for_status()
            channel_ids = [
                item.get("id", {}).get("channelId")
                for item in response.json().get("items", [])
                if item.get("id", {}).get("channelId")
            ]
        except Exception:
            logger.warning("YouTube 채널 후보 검색에 실패했습니다.")
            raise RuntimeError("YouTube 채널 후보 검색에 실패했습니다.") from None

        return self.resolve_channel_ids(channel_ids)


def _parse_iso8601_duration(value: str) -> float:
    match = re.fullmatch(r"P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value or "")
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return float(hours or 0) * 3600 + float(minutes or 0) * 60 + float(seconds or 0)

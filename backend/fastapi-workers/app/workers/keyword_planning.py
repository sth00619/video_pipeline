"""공개 YouTube 데이터 기반 키워드 마인드맵·다중 키워드 기획.

LLM은 키워드 조합과 문장 표현에만 사용한다. 조회수·비율·시간당 조회는
요청으로 전달받은 원본 값을 그대로 표시하거나 서버가 조합하며, 새 수치를 만들지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from typing import Any

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_PROMPT_CACHE_ENABLED, ANTHROPIC_PROMPT_CACHE_TTL, CLAUDE_MODEL, REDIS_HOST, REDIS_PORT
from app import runtime_config

logger = logging.getLogger(__name__)
_MINDMAP_TTL = 6 * 60 * 60
_STOPWORDS = {
    "주식", "전망", "오늘", "긴급", "속보", "분석", "이유", "정리", "진짜", "이렇게", "이번", "그리고",
    "the", "and", "for", "with", "from", "this", "that", "stock", "market", "video", "shorts",
}
_STOPWORDS.update({
    "오늘", "내일", "저는", "무조건", "이렇게", "이번", "진짜", "긴급", "속보",
    "공개", "필수", "시청", "관련", "대한", "이유", "정리", "분석", "전략",
    "live", "real", "time", "official", "news", "youtube", "short", "shorts",
    "라이브", "방송", "주식방송", "영상", "특별", "최신", "일일", "실시간",
})
_CHANNEL_SUFFIXES = ("tv", "뉴스", "채널")
_PARTICLE_SUFFIXES = tuple(sorted((
    "에서는", "으로", "에게", "부터", "까지", "처럼", "보다", "인데", "이며", "이지만",
    "이라서", "이라는", "이라고", "이란", "에서", "에는", "에는", "에게", "으로",
    "들은", "들이", "하는", "했다", "한다", "같은", "대한", "입니다", "이었다",
    "은", "는", "이", "가", "을", "를", "와", "과", "도", "만", "의", "들",
), key=len, reverse=True))


def _redis():
    try:
        import redis
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as exc:
        logger.warning("keyword planning Redis unavailable: %s", exc)
        return None


def _cache_key(keyword: str) -> str:
    # 사람이 Redis에서 찾기 쉬우면서 공백/한글도 안정적으로 쓰도록 hash suffix를 둔다.
    safe = re.sub(r"\s+", "-", keyword.strip().lower())[:48]
    # A layout/tokenization revision must not serve an old six-hour map.
    digest = hashlib.sha256(f"v10:7d:nonlive:min-subs-3000:min-views-3000:min-multiple-0.25:{keyword.strip().lower()}".encode("utf-8")).hexdigest()[:10]
    return f"mindmap:{safe}:{digest}"


def _value(video: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if video.get(name) is not None:
            return video[name]
    return default


def _multiple(video: dict[str, Any]) -> float:
    views = float(_value(video, "views", "viewCount", "view_count", default=0) or 0)
    subs = float(_value(video, "subscribers", "subscriberCount", "subscriber_count", default=0) or 0)
    return views / subs if subs > 0 else 0.0


def _comparison_key(value: str) -> str:
    """A conservative comparison key used only for grouping/filtering candidates."""
    return re.sub(r"[^a-z0-9가-힣]", "", unicodedata.normalize("NFKC", value).lower())


def _strip_korean_particle(token: str) -> str:
    """Remove only common terminal particles/endings; never invent a new word."""
    for suffix in _PARTICLE_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[:-len(suffix)]
    return token


def _normalise_token(raw: Any, center: str, channel_titles: set[str]) -> str | None:
    """Keep useful topical phrases and reject title fragments, channels and numeric claims.

    This is intentionally deterministic. Claude may consolidate the surviving
    candidates later in the *same* expansion call, but it never receives a
    channel name or a numeric value as a keyword candidate.
    """
    token = unicodedata.normalize("NFKC", str(raw)).strip()
    token = re.sub(r"^[#@]+", "", token)
    token = re.sub(r"\s+", " ", token)
    token = token.strip(" .,!?:;·|/\\\"'()[]{}")
    if len(token) < 2 or any(char.isdigit() for char in token):
        return None
    # Percentages, decimals, ticker-like symbols and punctuation-heavy title
    # fragments do not make stable topical nodes.
    if re.search(r"[%+&=]", token):
        return None
    token = _strip_korean_particle(token)
    key = _comparison_key(token)
    center_words = {_comparison_key(part) for part in re.findall(r"[A-Za-z가-힣]+", center)}
    if len(token) < 2 or not key or key in _STOPWORDS or key in center_words:
        return None
    if key in channel_titles or any(key.endswith(suffix) for suffix in _CHANNEL_SUFFIXES):
        return None
    # A complete channel title can be embedded in a tag even when a title uses
    # different punctuation, so exclude both directions for sufficiently long
    # comparison keys.
    if any(len(channel) >= 4 and (key in channel or channel in key) for channel in channel_titles):
        return None
    if not re.search(r"[A-Za-z가-힣]", token):
        return None
    return token


def _bounded_edit_distance(left: str, right: str, limit: int = 2) -> int:
    """Small, dependency-free Levenshtein check with an early exit."""
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for row, char_left in enumerate(left, start=1):
        current = [row]
        row_best = current[0]
        for column, char_right in enumerate(right, start=1):
            value = min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + (char_left != char_right))
            current.append(value)
            row_best = min(row_best, value)
        if row_best > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _similar_keyword(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) >= 3 and (left in right or right in left):
        return True
    distance = 1 if max(len(left), len(right)) <= 5 else 2
    return _bounded_edit_distance(left, right, distance) <= distance


def _channel_title_keys(videos: list[dict[str, Any]]) -> set[str]:
    return {
        key for video in videos
        for key in [_comparison_key(str(_value(video, "channelTitle", "channel_title", default="")))]
        if key
    }


def _tokens(video: dict[str, Any], center: str, channel_titles: set[str]) -> list[tuple[str, str]]:
    """Return only public YouTube tags for selectable topic candidates.

    Titles are evidence shown to the operator, not keyword material.  Mixing
    title tokens here makes accidental phrases such as presenter names or
    sentence fragments look like editorial recommendations.
    """
    tags = _value(video, "tags", default=[]) or []
    tokens: list[tuple[str, str]] = []
    for item in tags:
        token = _normalise_token(item, center, channel_titles)
        if token:
            tokens.append((str(item).strip(), token))
    return tokens


def _primary_ring(keyword: str, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frequency: Counter[str] = Counter()
    best_multiple: defaultdict[str, float] = defaultdict(float)
    canonical: dict[str, str] = {}
    raw_terms: defaultdict[str, set[str]] = defaultdict(set)
    source_video: dict[str, str] = {}
    evidence: defaultdict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    channel_titles = _channel_title_keys(videos)
    for video in videos:
        multiple = _multiple(video)
        video_id = str(_value(video, "videoId", "video_id", "id", default=""))
        for raw, token in _tokens(video, keyword, channel_titles):
            normalised = _comparison_key(token)
            merge_target = next((item for item in canonical if _similar_keyword(normalised, item)), normalised)
            frequency[merge_target] += 1
            raw_terms[merge_target].add(raw)
            if merge_target not in canonical or len(token) < len(canonical[merge_target]):
                canonical[merge_target] = token
            if multiple >= best_multiple[merge_target]:
                best_multiple[merge_target] = multiple
                source_video[merge_target] = video_id
            if video_id:
                previous_evidence = evidence[merge_target].get(video_id, {})
                evidence[merge_target][video_id] = {
                    "videoId": video_id,
                    "title": str(_value(video, "title", default="")),
                    "channelTitle": str(_value(video, "channelTitle", "channel_title", default="")),
                    "views": int(_value(video, "views", "viewCount", "view_count", default=0) or 0),
                    "subscribers": int(_value(video, "subscribers", "subscriberCount", "subscriber_count", default=0) or 0),
                    "bestMultiple": round(multiple, 2),
                    "matchedTags": sorted(set(previous_evidence.get("matchedTags", [])) | {raw}),
                }
    for key in sorted(canonical, key=lambda item: (-frequency[item], item))[:20]:
        logger.info("Mindmap keyword normalised raw=%s -> keyword=%s", sorted(raw_terms[key])[:4], canonical[key])
    ranked = sorted(frequency, key=lambda item: (frequency[item], best_multiple[item]), reverse=True)[:12]
    return [{
        "keyword": canonical[item],
        "raw": sorted(raw_terms[item]),
        "bestMultiple": round(best_multiple[item], 2),
        "sourceVideoId": source_video.get(item, ""),
        "evidence": sorted(evidence[item].values(), key=lambda row: row["bestMultiple"], reverse=True)[:3],
        "source": "api",
    } for item in ranked]


def _apply_llm_normalisation(
    primary: list[dict[str, Any]],
    rows: Any,
    center: str,
    channel_titles: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply only safe consolidation returned by the existing Claude call.

    Claude cannot add a new keyword here: every target must be a deterministic
    normalisation of a supplied candidate. That keeps the map grounded while
    allowing one existing call to combine genuinely duplicate phrasing.
    """
    aliases: dict[str, str] = {}
    known_candidates = {_comparison_key(item["keyword"]) for item in primary}
    for row in rows if isinstance(rows, list) else []:
        raw = _comparison_key(str(row.get("raw", ""))) if isinstance(row, dict) else ""
        target = _normalise_token(row.get("keyword", ""), center, channel_titles) if isinstance(row, dict) else None
        # The returned target must already exist in the grounded candidate set.
        # This makes the LLM a spelling/alias resolver, never a source of a
        # fresh topic that did not occur in the retrieved YouTube metadata.
        if raw and target and _comparison_key(target) in known_candidates:
            aliases[raw] = target
        elif raw and target:
            logger.info("Ignoring ungrounded LLM keyword normalisation: %s -> %s", raw, target)

    grouped: dict[str, dict[str, Any]] = {}
    mappings: list[dict[str, Any]] = []
    for item in primary:
        raw_key = _comparison_key(item["keyword"])
        target = aliases.get(raw_key, item["keyword"])
        target_key = _comparison_key(target)
        previous = grouped.get(target_key)
        mappings.append({"raw": item.get("raw", [item["keyword"]]), "keyword": target})
        if previous is None:
            grouped[target_key] = {**item, "keyword": target}
            continue
        previous["raw"] = sorted(set(previous.get("raw", [])) | set(item.get("raw", [])))
        merged_evidence = {entry.get("videoId"): entry for entry in previous.get("evidence", []) if entry.get("videoId")}
        for entry in item.get("evidence", []):
            video_id = entry.get("videoId")
            if not video_id:
                continue
            existing = merged_evidence.get(video_id, {})
            merged_evidence[video_id] = {
                **existing,
                **entry,
                "matchedTags": sorted(set(existing.get("matchedTags", [])) | set(entry.get("matchedTags", []))),
            }
        previous["evidence"] = sorted(merged_evidence.values(), key=lambda entry: entry.get("bestMultiple", 0), reverse=True)[:3]
        if item["bestMultiple"] > previous["bestMultiple"]:
            previous["bestMultiple"] = item["bestMultiple"]
            previous["sourceVideoId"] = item.get("sourceVideoId", "")

    cleaned = sorted(grouped.values(), key=lambda item: (item["bestMultiple"], len(item.get("raw", []))), reverse=True)[:12]
    return cleaned, mappings


def _clean_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("JSON 객체를 찾지 못했습니다.")
    return json.loads(match.group(0))


def _claude_json(system: str, prompt: str) -> dict[str, Any]:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("Anthropic API key is not configured")
    from anthropic import Anthropic
    from app.utils.anthropic_cache import cached_system, log_cache_usage

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    kwargs: dict[str, Any] = {
        "model": CLAUDE_MODEL,
        "max_tokens": 900,
        "messages": [{"role": "user", "content": prompt}],
    }
    if ANTHROPIC_PROMPT_CACHE_ENABLED:
        kwargs["system"] = cached_system(system)
    else:
        kwargs["system"] = system
    # Claude occasionally wraps an otherwise good answer in prose or emits a
    # malformed object.  One narrow retry keeps the requested JSON-only
    # contract without allowing an invalid LLM reply to block the worker.
    last_error: Exception | None = None
    for attempt in range(2):
        response = client.messages.create(**kwargs)
        log_cache_usage(response, "keyword_planning")
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        try:
            return _clean_json(text)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning("Keyword planning JSON parse failed (attempt %s/2): %s", attempt + 1, exc)
            if attempt == 0:
                kwargs["messages"] = [{
                    "role": "user",
                    "content": prompt + "\n\nReturn one syntactically valid JSON object only. Do not use markdown fences or comments.",
                }]
    raise ValueError("Claude did not return a valid JSON object after one retry") from last_error


def _fallback_expansions(primary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suffixes = ["실적", "수급", "전망", "리스크"]
    output = []
    for index, item in enumerate(primary[:6]):
        output.append({
            "parent": item["keyword"],
            "keyword": f"{item['keyword']} {suffixes[index % len(suffixes)]}",
            "reason": "공개 영상 제목·태그에서 함께 확인된 금융 탐색어",
            "bestMultiple": item["bestMultiple"],
            "source": "fallback",
        })
    return output


def build_mindmap(keyword: str, videos: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", keyword).strip())
    if not normalized:
        raise ValueError("중심 키워드를 입력해 주세요.")
    minimum_subscribers = int(runtime_config.value("keyword_min_source_subscribers"))
    minimum_views = int(runtime_config.value("keyword_min_source_views"))
    minimum_multiple = float(runtime_config.value("keyword_min_source_viewer_multiple"))
    # Browser-cached or manually supplied rows must obey the same source rule.
    videos = [
        video for video in videos
        if bool(_value(video, "subscriberCountAvailable", "subscriber_count_available", default=True))
        and float(_value(video, "subscribers", "subscriberCount", "subscriber_count", default=0) or 0) >= minimum_subscribers
        and float(_value(video, "views", "viewCount", "view_count", default=0) or 0) >= minimum_views
        and _multiple(video) >= minimum_multiple
        and 0 < float(_value(video, "hoursSincePublish", "hours_since_publish", default=0) or 0) <= 24 * 7
        and not bool(_value(video, "isLive", "is_live", default=False))
    ]
    client = _redis()
    key = _cache_key(normalized)
    if client:
        cached = client.get(key)
        if cached:
            logger.info("Keyword mindmap cache hit: %s", key)
            return json.loads(cached)

    channel_titles = _channel_title_keys(videos)
    primary = _primary_ring(normalized, videos)
    normalisation: list[dict[str, Any]] = []
    try:
        response = _claude_json(
            "당신은 한국 금융 콘텐츠의 키워드 편집자다. 숫자·시세·통계를 절대 만들지 말고 JSON만 반환한다.",
            "아래 1차 금융 키워드를 바탕으로 두 작업을 같은 JSON으로 한다. (1) normalized에는 전달된 raw 후보를 "
            "조사 없는 짧은 주제어로 통합한다. 새로운 주제어·채널명·숫자는 절대 만들지 않는다. (2) expansions에는 "
            "각 parent마다 최대 하나의 2차 확장 키워드를 만든다. 주식·금융·KOSPI·KOSDAQ·미국장 문맥만 허용한다. 출력은 "
            '{"normalized":[{"raw":"후보","keyword":"통합 후보"}],"expansions":[{"parent":"...","keyword":"...","reason":"..."}]} JSON 객체 하나뿐이어야 한다.\n'
            + json.dumps({"center": normalized, "primary": primary}, ensure_ascii=False),
        )
        primary, normalisation = _apply_llm_normalisation(primary, response.get("normalized"), normalized, channel_titles)
        primary_index = {item["keyword"]: item for item in primary}
        parent_lookup = {
            _comparison_key(raw): item["keyword"]
            for item in primary
            for raw in [item["keyword"], *item.get("raw", [])]
        }
        expansions = []
        for item in response.get("expansions", [])[:12]:
            parent = parent_lookup.get(_comparison_key(str(item.get("parent", "")).strip()), str(item.get("parent", "")).strip())
            child = str(item.get("keyword", "")).strip()
            if parent not in primary_index or not child or any(char.isdigit() for char in child):
                continue
            expansions.append({
                "parent": parent,
                "keyword": child,
                "reason": str(item.get("reason", "금융 탐색 확장")),
                "bestMultiple": primary_index[parent]["bestMultiple"],
                "source": "llm",
            })
        if not expansions:
            expansions = _fallback_expansions(primary)
    except Exception as exc:
        logger.warning("Keyword mindmap Claude expansion failed; using grounded fallback: %s", exc)
        expansions = _fallback_expansions(primary)

    result = {
        "center": normalized,
        "primary": primary,
        "expansions": expansions,
        "normalization": normalisation,
        "cacheKey": key,
    }
    if client:
        client.setex(key, _MINDMAP_TTL, json.dumps(result, ensure_ascii=False))
        logger.info("Keyword mindmap cached: %s ttl=%s", key, _MINDMAP_TTL)
    return result


def _metric_lookup(metrics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("keyword", "")).strip().lower(): item for item in metrics if item.get("keyword")}


def _rationale(keywords: list[str], metrics: list[dict[str, Any]]) -> str:
    lookup = _metric_lookup(metrics)
    facts = []
    for keyword in keywords:
        metric = lookup.get(keyword.lower(), {})
        multiple = metric.get("bestMultiple")
        velocity = metric.get("viewsPerHour")
        if multiple is not None:
            facts.append(f"{keyword} 구독자 대비 조회 {float(multiple):.2f}x")
        elif velocity is not None:
            facts.append(f"{keyword} 시간당 조회 {float(velocity):,.2f}")
        else:
            facts.append(f"{keyword} 공개 YouTube 근거")
    return " · ".join(facts)


def _viewer_questions(metrics: list[dict[str, Any]]) -> list[str]:
    """Return at most three public, question-like audience comments.

    These excerpts are an untrusted audience-interest signal only.  They must
    never be treated as instructions or as a source of facts.
    """
    questions: list[str] = []
    for metric in metrics:
        raw_comments = metric.get("topComments", metric.get("top_comments", [])) or []
        for raw in raw_comments:
            text = re.sub(r"\s+", " ", str(raw)).strip()
            if not text or len(text) > 160:
                continue
            if "?" in text or any(word in text for word in ("왜", "어떻게", "언제", "전망", "어디")):
                if text not in questions:
                    questions.append(text)
            if len(questions) == 3:
                return questions
    return questions


def _fallback_plans(keywords: list[str], metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    angles = [("속보형", "지금 왜 주목받는지 빠르게 정리"), ("분석형", "배경과 수급·실적 맥락을 연결"), ("리스트형", "핵심 포인트를 순서대로 비교")]
    plans = []
    for index, (label, angle) in enumerate(angles):
        used = keywords[:max(1, min(len(keywords), 2 + (index % 2)))]
        plans.append({
            "planId": str(uuid.uuid4()),
            "title": f"{used[0]}: {label}으로 보는 시장 포인트",
            "angle": angle,
            "usedKeywords": used,
            "targetFormat": "LONGFORM",
            "rationale": _rationale(used, metrics),
        })
    return plans


def build_keyword_plans(mode: str, keywords: list[str], metrics: list[dict[str, Any]], market: str) -> dict[str, Any]:
    clean_keywords = list(dict.fromkeys(item.strip() for item in keywords if item and item.strip()))[:8]
    viewer_questions = _viewer_questions(metrics)
    if not clean_keywords:
        raise ValueError("최소 하나의 키워드를 선택해 주세요.")
    try:
        response = _claude_json(
            "당신은 한국 금융 유튜브 기획자다. 전달된 키워드만 조합하고, 수치·시세·통계를 새로 만들지 않는다. JSON만 반환한다.",
            "아래 키워드로 서로 다른 3개 기획을 만든다. 속보형·분석형·리스트형처럼 각도를 다르게 하고, "
            "rationale에는 숫자를 쓰지 않는다(서버가 공개 API 원본 수치를 붙인다). "
            '출력: {"plans":[{"title":"...","angle":"...","usedKeywords":["..."],"targetFormat":"LONGFORM"}]}\n'
            + json.dumps({"mode": mode, "market": market, "keywords": clean_keywords, "viewer_questions": viewer_questions}, ensure_ascii=False),
        )
        plans = []
        for raw in response.get("plans", [])[:3]:
            used = [item for item in raw.get("usedKeywords", []) if item in clean_keywords]
            if not used:
                used = clean_keywords[:2]
            plans.append({
                "planId": str(uuid.uuid4()),
                "title": str(raw.get("title", "")).strip() or f"{used[0]} 시장 분석",
                "angle": str(raw.get("angle", "")).strip() or "공개 지표 기반 분석",
                "usedKeywords": used,
                "targetFormat": "LONGFORM",
                "rationale": _rationale(used, metrics),
            })
        if len(plans) != 3:
            raise ValueError("기획안 수가 3개가 아닙니다.")
        return {"plans": plans}
    except Exception as exc:
        logger.warning("Keyword plan Claude generation failed; using grounded fallback: %s", exc)
        return {"plans": _fallback_plans(clean_keywords, metrics)}

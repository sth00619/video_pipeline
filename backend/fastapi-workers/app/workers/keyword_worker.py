"""
Phase 3-1 — 키워드 탐색 워커 v2 (주식 콘텐츠 특화)

v2 변경사항:
  [신규] 실시간 경제 뉴스 RSS + 네이버 검색 API로 뉴스 기반 키워드 발굴
  [신규] pykrx + yfinance로 당일 시장 지표 수집 (market_snapshot)
  [기존] YouTube 트렌딩 분석 병행 유지
  [신규] Claude API로 뉴스 + YouTube 후보를 통합 순위화 + 콘텐츠 가능성 평가
  [신규] market_snapshot을 결과에 포함 → ScriptWorker에 재활용

v2.1 변경사항 (버그 수정):
  [버그 수정 - 중요] 이 단계에는 script_worker.py의 3-Round 팩트체크 같은
  창작 방지 가드레일이 전혀 없었습니다. 그 결과 Claude가 "SK하이닉스"라는
  실제 뉴스 키워드를 보고 "나스닥 상장 첫날 13% 급등"처럼 실제 시장 데이터에
  전혀 없는 사실/수치를 자유롭게 지어내서 후보 제목으로 내놓는 사고가
  있었습니다 (SK하이닉스는 코스피 상장 종목이며 나스닥 상장 이력 없음).

  수정 1: 프롬프트에 "제공된 데이터 밖의 사실/수치 창작 절대 금지" 규칙을
          명시적으로 추가.
  수정 2: Claude가 반환한 각 후보를 실제 입력 데이터(뉴스/YouTube 후보 원문,
          market_data 수치)에 비추어 사후 검증. 후보에 등장하는 퍼센트 수치가
          어느 원본에도 없으면 그 후보를 드롭하고 폴백으로 채웁니다.

흐름:
  1. 뉴스 RSS + 네이버 API → NLP 키워드 추출
  2. YouTube 트렌딩 → 점수 기반 후보 생성
  3. 시장 데이터 수집 (pykrx + yfinance)
  4. Claude로 통합 순위화 (시장 맥락 포함, 창작 금지 규칙 적용)
  5. 그라운딩 검증 → 근거 없는 후보 드롭 및 폴백 보충
  6. 최종 후보 반환 (market_snapshot 포함)
"""
import os
import re
import json
import logging
from typing import Optional

from app.providers.factory import get_trending_video_analyzer
from app.workers.market_data_collector import MarketDataCollector
from app.workers.news_keyword_extractor import NewsKeywordExtractor
from app.utils.anthropic_cache import cached_system, log_cache_usage
from app.utils.keyword_time_context import resolve_keyword_time_context
from app.utils.keyword_aliases import seed_match, seed_overlap

logger = logging.getLogger(__name__)

KR_CATEGORIES = {"KOSPI", "KOSDAQ", "INDIVIDUAL_STOCK", "ASSOCIATED_STOCKS"}
US_CATEGORIES = {"US_STOCKS"}

CATEGORY_LABELS = {
    "KOSPI": "코스피(한국 종합주가지수)",
    "KOSDAQ": "코스닥",
    "US_STOCKS": "미국 주식(나스닥/S&P500)",
    "INDIVIDUAL_STOCK": "개별 종목",
    "ASSOCIATED_STOCKS": "연관 종목군",
    "GLOBAL_MACRO": "글로벌 매크로 경제",
    "CRYPTO": "암호화폐",
    "CUSTOM": "주식시장 전반",
}

KEYWORD_SYSTEM = """당신은 한국 금융·주식 유튜브 채널의 키워드 편집장입니다.
입력으로 제공된 뉴스, YouTube 검색 결과, 시장 데이터만 근거로 후보를 평가합니다.
제공된 자료 밖의 종목명, 상장시장, 가격, 등락률, 거래대금, 조회수, 날짜를 절대 창작하지 않습니다.
키워드는 원문 후보를 보존하고, 여러 원문을 임의의 새로운 사실로 합성하지 않습니다.
후보는 시의성, 검색 의도, 20분 영상으로 확장 가능한 깊이, 금융 채널 적합성,
경쟁 강도, 채널 규모 대비 조회 성과를 함께 고려해야 합니다.
YouTube 통계의 의미를 혼동하지 마세요. 공개 Data API에서 확인할 수 없는
평균 시청 시간과 CTR은 추정하거나 숫자로 만들지 말고 unavailable로 표시합니다.
조회수/구독자수는 채널 규모를 보정하는 참고 지표일 뿐 절대적인 성공 보장이 아닙니다.
각 후보의 근거는 입력 데이터의 video_id와 통계에 연결되어야 하며, 근거 없는 후보는 제외합니다.
응답은 반드시 JSON 하나만 반환합니다. candidates 배열의 각 원소는 keyword, reason,
content_angle, source(news|youtube|both), estimated_interest(high|medium|low),
evidence_video_ids 배열을 포함해야 합니다."""


class KeywordWorker:

    def __init__(self):
        self.analyzer = get_trending_video_analyzer()
        self.collector = MarketDataCollector()
        self.extractor = NewsKeywordExtractor()

    def search(self, category: str, seed: str, limit: int = 5,
               outperformer_count: int = 1, job_id: int = 0) -> dict:

        time_context = resolve_keyword_time_context(seed)
        if time_context["requires_evidence"]:
            return {
                "job_id": job_id, "seed": seed, "category": category,
                "candidates": [_seed_candidate(seed, time_context["message"], "근거 확인이 필요한 시간 조건")],
                "market_snapshot": {}, "news_keyword_count": 0, "yt_candidate_count": 0,
                "time_interpretation": time_context, "topic_evidence_required": True,
            }

        logger.info(f"키워드 탐색 v2: category={category}, seed={seed}, "
                    f"limit={limit}, job_id={job_id}")

        # ── Step 1: 뉴스 기반 키워드 추출 ────────────────────────
        news_keywords = []
        try:
            if category in US_CATEGORIES:
                news_keywords = self.extractor.extract_us_keywords(top_n=15)
            else:
                news_keywords = self.extractor.extract_kr_keywords(
                    category=category, seed=seed, top_n=15
                )
            logger.info(f"뉴스 키워드 {len(news_keywords)}개 추출")
        except Exception as e:
            logger.warning(f"뉴스 키워드 추출 실패: {e}")

        # ── Step 2: YouTube 트렌딩 분석 (기존 로직 유지) ───────────
        yt_candidates = []
        try:
            videos = self.analyzer.collect(category, seed or "", limit=30)
            scored = self._score_yt_videos(videos)
            yt_candidates = scored[:limit * 2]
            logger.info(f"YouTube 후보 {len(yt_candidates)}개 생성")
        except Exception as e:
            logger.warning(f"YouTube 분석 실패: {e}")

        # ── Step 3: 시장 데이터 수집 ─────────────────────────────
        market_data = {}
        try:
            market_data = self.collector.collect_for_category(category, seed)
            logger.info(f"시장 데이터 수집 완료: kr={bool(market_data.get('kr'))}, "
                        f"us={bool(market_data.get('us'))}")
        except Exception as e:
            logger.warning(f"시장 데이터 수집 실패: {e}")

        # ── Step 4: Claude로 통합 순위화 ─────────────────────────
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        candidates = []

        if api_key and (news_keywords or yt_candidates):
            try:
                candidates = self._rank_with_claude(
                    news_keywords, yt_candidates, market_data,
                    category, seed, limit, api_key
                )
                candidates = self._attach_youtube_metrics(candidates, yt_candidates)
                logger.info(f"Claude 순위화 완료: {len(candidates)}개 후보")

                # [버그 수정] 그라운딩 검증 — 실제 데이터에 없는 수치를 지어낸
                # 후보를 걸러내고, 부족해진 자리는 폴백 후보로 채웁니다.
                candidates = self._filter_ungrounded_candidates(
                    candidates, news_keywords, yt_candidates, market_data
                )
                if len(candidates) < limit:
                    backup = self._fallback_candidates(
                        news_keywords, yt_candidates, outperformer_count, limit
                    )
                    existing_kw = {c["keyword"] for c in candidates}
                    for b in backup:
                        if len(candidates) >= limit:
                            break
                        if b["keyword"] not in existing_kw:
                            candidates.append(b)
                            existing_kw.add(b["keyword"])

            except Exception as e:
                logger.warning(f"Claude 순위화 실패, 폴백 사용: {e}")
                candidates = self._fallback_candidates(
                    news_keywords, yt_candidates, outperformer_count, limit
                )
        else:
            candidates = self._fallback_candidates(
                news_keywords, yt_candidates, outperformer_count, limit
            )

        # The operator's supplied keyword is the editorial brief, not just a
        # hint for a broad category search.  In particular, a KOSPI category
        # must never replace "삼성전자 3분기 반도체 실적" with a generic
        # "코스피" topic simply because the generic topic appeared more often
        # in today's news.  Keep only seed-related Claude/news candidates and
        # fill any gap with clearly-labelled, non-factual editorial angles.
        candidates = self._enforce_seed_priority(candidates, seed, limit)
        for candidate in candidates:
            evidence_text = " ".join(str(candidate.get(key, "")) for key in ("keyword", "reason", "content_angle"))
            candidate["seed_overlap_terms"] = seed_overlap(seed, evidence_text)
            candidate["seed_overlap_count"] = len(candidate["seed_overlap_terms"])

        logger.info(f"키워드 탐색 완료: {len(candidates)}개 최종 후보")

        return {
            "job_id": job_id,
            "seed": seed,
            "category": category,
            "candidates": candidates,
            "market_snapshot": market_data,   # ScriptWorker에 재활용
            "news_keyword_count": len(news_keywords),
            "yt_candidate_count": len(yt_candidates),
            "time_interpretation": time_context,
            "topic_evidence_required": False,
        }

    # ──────────────────────────────────────────────────────────
    # Claude 통합 순위화
    # ──────────────────────────────────────────────────────────
    def _rank_with_claude(self, news_kw: list, yt_candidates: list,
                          market_data: dict, category: str, seed: str,
                          limit: int, api_key: str) -> list:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        category_label = CATEGORY_LABELS.get(category, "주식시장")

        # 시장 요약 텍스트 생성
        market_summary = _build_market_summary(market_data)

        # 뉴스 키워드 상위 10개
        news_top = [
            f"'{kw['keyword']}' (뉴스 등장 {kw['count']}회, 점수 {kw['score']:.2f}, "
            f"예시: {kw['sample_headline'][:50]})"
            for kw in news_kw[:10]
        ]

        # YouTube 후보 상위 10개
        yt_top = [
            f"'{c['keyword']}' (종합점수 {c['composite_score']:.2f}, "
            f"조회수 {c.get('source_videos', [{}])[0].get('views', 0):,}, "
            f"구독자 대비 {c.get('engagement_ratio', 0):.3f}, "
            f"좋아요 {c.get('likes', 0):,}, 댓글 {c.get('comments', 0):,}, "
            f"영상길이 {c.get('duration_seconds', 0):.0f}초, "
            f"평균시청시간=공개불가, video_id={c.get('source_videos', [{}])[0].get('video_id', '')})"
            for c in yt_candidates[:10]
        ]

        prompt = f"""당신은 한국 주식 유튜브 채널 키워드 전문가입니다.

<market_context>
카테고리: {category_label}
검색 시드: {seed or '없음'}
{market_summary}
</market_context>

<news_keywords>
오늘 경제 뉴스에서 추출한 주요 키워드:
{chr(10).join(news_top) if news_top else "수집 없음"}
</news_keywords>

<youtube_trending>
YouTube 트렌딩 분석 기반 키워드 후보:
{chr(10).join(yt_top) if yt_top else "수집 없음"}
</youtube_trending>

위 뉴스 키워드와 YouTube 후보를 종합하여, {category_label} 분야에서 오늘 유튜브 영상 콘텐츠로 만들기 가장 좋은 키워드 {limit}개를 선정하세요.

【입력 주제 우선 규칙 — 최우선】
- 검색 시드가 비어 있지 않으면, 그것은 작업자가 확정한 편집 브리프입니다.
  카테고리는 분석의 렌즈일 뿐, 검색 시드를 일반적인 "코스피", "증시", "시장" 주제로
  대체하면 안 됩니다.
- 검색 시드가 있을 때 후보 1번 keyword는 검색 시드를 그대로 사용하세요.
- 나머지 후보도 검색 시드의 구체 명사/핵심어를 최소 두 개 이상 유지한 세부 관점만
  제안하세요. 예: "삼성전자 3분기 반도체 실적"이면 삼성전자·반도체·실적을 중심으로
  하며, 단순 "코스피 글로벌 바로미터" 같은 일반 시장 주제는 금지합니다.
- 입력 데이터가 부족하면 일반 시장 뉴스로 바꾸지 말고, 제공된 사실 범위에서
  "핵심 쟁점", "시장 영향", "확인할 지표"처럼 사실을 추가하지 않는 관점만 사용하세요.

선정 기준:
1. 오늘 실제 시장 상황과 관련성이 높은가?
2. 시청자(개인 투자자)의 관심을 끌 수 있는 주제인가?
3. 20분 분량 영상으로 충분히 다룰 수 있는 깊이가 있는가?
4. 뉴스와 YouTube 양쪽에서 주목받고 있는가?

【절대 금지사항 — 반드시 지켜야 함】
- 위 <market_context>, <news_keywords>, <youtube_trending>에 없는 회사명, 상장 여부,
  등락률(%), 순매수/순매도 규모 등 어떠한 사실이나 수치도 새로 만들어내면 안 됩니다.
- 예를 들어 어떤 종목이 실제로는 코스피 상장인데 "나스닥 상장"이라고 쓰거나,
  실제 등락률이 제공되지 않았는데 "13% 급등"처럼 구체적인 숫자를 임의로 붙이는 것은
  절대 금지입니다.
- keyword는 반드시 위에 제공된 뉴스/YouTube 후보 문구를 그대로 쓰거나, 그 범위 안에서
  자연스럽게 다듬는 정도로만 작성하세요. 후보 목록에 없는 새로운 팩트를 조합해서
  자극적인 제목을 만들어내지 마세요.
- 구체적인 수치(%, 포인트, 금액)를 keyword나 reason에 쓰려면 반드시 <market_context>에
  실제로 그 수치가 있어야 합니다. 없으면 수치 없이 정성적으로만 표현하세요
  (예: "급등" 대신 구체적 % 없이 "강세" 정도로).

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "candidates": [
    {{
      "keyword": "키워드",
      "reason": "선정 이유 (시장 맥락 포함, 2-3문장)",
      "content_angle": "영상에서 다룰 핵심 관점",
      "source": "news|youtube|both",
      "estimated_interest": "high|medium|low",
      "evidence_video_ids": ["YouTube video_id 또는 빈 배열"]
    }}
  ]
}}"""

        response = client.messages.create(
            # 버그 수정: 존재하지 않는 "claude-sonnet-5" 오타 → 프로젝트 고정 모델로 교체.
            # 이 오타 때문에 Claude 순위화 API 호출이 계속 실패하고
            # _fallback_candidates()로만 빠지고 있었을 가능성이 높습니다.
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=cached_system(KEYWORD_SYSTEM),
            messages=[{"role": "user", "content": prompt}],
        )
        log_cache_usage(response, "keyword_worker")

        raw = response.content[0].text.strip()
        # JSON 파싱
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if not json_match:
            raise ValueError("Claude 응답에서 JSON을 찾을 수 없음")

        data = json.loads(json_match.group())
        claude_candidates = data.get("candidates", [])

        # 후보 포맷 통일
        result = []
        for i, c in enumerate(claude_candidates[:limit]):
            result.append({
                "keyword": c.get("keyword", ""),
                "search_volume": 0,
                "competition": "MEDIUM",
                "reason": c.get("reason", ""),
                "content_angle": c.get("content_angle", ""),
                "source": c.get("source", "both"),
                "estimated_interest": c.get("estimated_interest", "medium"),
                "engagement_ratio": 0.0,
                "outperformance_index": 0.0,
                "velocity_vph": 0.0,
                "evidence_video_ids": c.get("evidence_video_ids", []),
                "is_outperformer": i == 0,
                "source_videos": [],
            })
        return result

    # ──────────────────────────────────────────────────────────
    # [신규] 그라운딩 검증 — Claude가 지어낸 수치가 섞인 후보를 걸러냄
    # ──────────────────────────────────────────────────────────
    def _filter_ungrounded_candidates(self, candidates: list, news_kw: list,
                                        yt_candidates: list, market_data: dict) -> list:
        """
        각 후보의 keyword/reason에 등장하는 퍼센트(%) 수치가 실제 입력 데이터
        (뉴스 헤드라인, YouTube 후보 원문, market_data 수치) 어디에도 없으면
        그 후보를 근거 없는 것으로 간주해 드롭합니다.

        완벽한 팩트체크는 아니지만("나스닥 상장" 같은 정성적 오류까지는 못 잡음),
        가장 위험한 유형인 "구체적 수치 창작"은 확실히 걸러냅니다.
        """
        # 실제 데이터에 등장하는 모든 숫자를 모음 (뉴스 원문 + market_data 수치)
        # 문자열이 아니라 float으로 모아야 "1.2%" vs "+1.20%" 같은 표기 차이로
        # 정상 후보까지 걸러지는 것을 방지할 수 있습니다.
        grounded_numbers = set()

        def _collect_numbers(text: str):
            for n in re.findall(r'\d+(?:\.\d+)?', text or ""):
                try:
                    grounded_numbers.add(round(float(n), 1))
                except ValueError:
                    pass

        for kw in news_kw:
            _collect_numbers(kw.get("sample_headline", ""))
            _collect_numbers(kw.get("keyword", ""))

        for c in yt_candidates:
            _collect_numbers(c.get("keyword", ""))
            for sv in c.get("source_videos", []):
                _collect_numbers(sv.get("title", ""))

        market_summary_text = _build_market_summary(market_data)
        _collect_numbers(market_summary_text)

        filtered = []
        for c in candidates:
            text = f"{c.get('keyword', '')} {c.get('reason', '')}"
            pct_numbers = re.findall(r'(\d+(?:\.\d+)?)\s*%', text)

            ungrounded = []
            for n in pct_numbers:
                try:
                    n_val = round(float(n), 1)
                except ValueError:
                    continue
                # 소수점 반올림 차이까지 감안해 ±0.1 오차는 허용
                if not any(abs(n_val - g) <= 0.1 for g in grounded_numbers):
                    ungrounded.append(n)

            if ungrounded:
                logger.warning(
                    f"근거 없는 수치 포함 후보 드롭: keyword='{c.get('keyword')}', "
                    f"근거 없는 수치={ungrounded} (실제 데이터에 없음)"
                )
                continue
            filtered.append(c)

        return filtered

    # ──────────────────────────────────────────────────────────
    # YouTube 점수 계산 (기존 로직 유지)
    # ──────────────────────────────────────────────────────────
    def _attach_youtube_metrics(self, candidates: list, yt_candidates: list) -> list:
        """Carry real API evidence into Claude-ranked candidates."""
        for candidate in candidates:
            name = str(candidate.get("keyword", "")).strip().lower()
            match = next(
                (item for item in yt_candidates
                 if name and (name == str(item.get("keyword", "")).strip().lower()
                              or name in str(item.get("keyword", "")).lower()
                              or str(item.get("keyword", "")).lower() in name)),
                None,
            )
            if not match:
                continue
            for key in (
                "views", "subscribers", "channel_avg_views", "engagement_ratio",
                "outperformance_index", "velocity_vph", "likes", "comments",
                "likes_available", "comments_available",
                "duration_seconds", "average_view_duration_seconds",
                "average_view_percentage", "retention_available",
                "channel_avg_views_is_sample", "subscriber_count_available",
                "source_videos",
            ):
                if key in match:
                    candidate[key] = match[key]
        return candidates

    def _score_yt_videos(self, videos: list) -> list:
        scored = []
        for v in videos:
            engagement_ratio = round(v.views / max(v.subscribers, 1), 3)
            outperformance_index = round(v.views / max(v.channel_avg_views, 1), 2)
            velocity_vph = round(v.views / max(v.hours_since_publish, 0.1), 1)

            composite_score = (
                min(engagement_ratio * 0.3, 3.0) +
                min(outperformance_index * 0.4, 4.0) +
                min(velocity_vph / 100, 3.0) * 0.3
            )

            competition = "HIGH" if composite_score >= 5.0 else (
                "MEDIUM" if composite_score >= 2.5 else "LOW"
            )

            extracted_keyword, keyword_is_raw_title = _extract_keyword(v.title)
            scored.append({
                "keyword": extracted_keyword,
                "keyword_is_raw_title": keyword_is_raw_title,
                "composite_score": composite_score,
                "views": v.views,
                "subscribers": v.subscribers,
                "channel_avg_views": v.channel_avg_views,
                "competition": competition,
                "engagement_ratio": engagement_ratio,
                "outperformance_index": outperformance_index,
                "velocity_vph": velocity_vph,
                "likes": v.likes,
                "comments": v.comments,
                "likes_available": v.likes_available,
                "comments_available": v.comments_available,
                "duration_seconds": v.duration_seconds,
                "average_view_duration_seconds": v.average_view_duration_seconds,
                "average_view_percentage": v.average_view_percentage,
                "retention_available": v.retention_available,
                "channel_avg_views_is_sample": v.channel_avg_views_is_sample,
                "subscriber_count_available": v.subscriber_count_available,
                "is_outperformer": False,
                "source": "youtube",
                "source_videos": [{
                    "title": v.title,
                    "channel_title": v.channel_title,
                    "video_id": v.video_id,
                    "views": v.views,
                    "subscribers": v.subscribers,
                    "likes": v.likes,
                    "comments": v.comments,
                    "likes_available": v.likes_available,
                    "comments_available": v.comments_available,
                    "duration_seconds": v.duration_seconds,
                    "average_view_duration_seconds": v.average_view_duration_seconds,
                    "average_view_percentage": v.average_view_percentage,
                    "retention_available": v.retention_available,
                    "channel_avg_views_is_sample": v.channel_avg_views_is_sample,
                    "subscriber_count_available": v.subscriber_count_available,
                    "hours_since_publish": v.hours_since_publish,
                }],
            })

        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        if scored:
            scored[0]["is_outperformer"] = True
        return scored

    # ──────────────────────────────────────────────────────────
    # 폴백: Claude 없거나 실패 시
    # ──────────────────────────────────────────────────────────
    def _fallback_candidates(self, news_kw: list, yt_candidates: list,
                              outperformer_count: int, limit: int) -> list:
        result = []
        seen = set()

        # 뉴스 키워드 우선 추가
        for kw in news_kw[:limit]:
            if kw["keyword"] not in seen:
                seen.add(kw["keyword"])
                result.append({
                    "keyword": kw["keyword"],
                    "search_volume": kw["count"] * 100,
                    "competition": "MEDIUM",
                    "reason": f"뉴스 {kw['count']}회 등장 · {kw['sample_headline'][:60]}",
                    "content_angle": "",
                    "source": "news",
                    "estimated_interest": "medium",
                    "engagement_ratio": 0.0,
                    "outperformance_index": 0.0,
                    "velocity_vph": 0.0,
                    "is_outperformer": len(result) < outperformer_count,
                    "source_videos": [],
                })

        # 부족하면 YouTube로 보충
        for c in yt_candidates:
            if len(result) >= limit:
                break
            if c["keyword"] not in seen:
                seen.add(c["keyword"])
                result.append({
                    **c,
                    "search_volume": int(c.get("velocity_vph", 0) * 1.5),
                    "is_outperformer": len(result) < outperformer_count,
                })

        return result[:limit]

    def _enforce_seed_priority(self, candidates: list, seed: str, limit: int) -> list:
        """Make a non-empty request seed a hard editorial constraint.

        Ranking can legitimately find broad market headlines, but they are
        not valid replacements for an explicitly requested company/topic.
        This guard runs after both Claude ranking and the no-LLM fallback so
        quota exhaustion cannot silently change the subject of a job.
        """
        normalized_seed = re.sub(r"\s+", " ", seed or "").strip()
        if not normalized_seed:
            return candidates[:limit]

        terms = _seed_specific_terms(normalized_seed)
        related = [
            candidate for candidate in candidates
            if _candidate_matches_seed(candidate, terms)
        ]

        # The exact requested topic is always the first candidate.  It has no
        # invented metric or factual claim and is therefore safe even when the
        # YouTube quota is exhausted or current news has not indexed yet.
        primary = _seed_candidate(
            normalized_seed,
            "입력 키워드 우선 후보입니다. 카테고리는 분석 범위로만 사용하며, "
            "이 주제를 다른 일반 시장 이슈로 대체하지 않습니다.",
            "입력 주제의 핵심 사실과 시장 영향을 검증된 자료 범위에서 정리합니다.",
        )

        result = [primary]
        seen = {normalized_seed.casefold()}
        for candidate in related:
            keyword = str(candidate.get("keyword", "")).strip()
            if not keyword or keyword.casefold() in seen:
                continue
            candidate["is_outperformer"] = False
            result.append(candidate)
            seen.add(keyword.casefold())
            if len(result) >= limit:
                return result

        # Do not refill a seed-driven search with unrelated KOSPI news.  These
        # are neutral editorial angles, not fabricated news titles or data.
        for suffix, angle in (
            ("핵심 쟁점", "실적에 영향을 주는 핵심 변수를 분리해 봅니다."),
            ("시장 영향", "카테고리 시장과 연관 종목에 미칠 수 있는 영향을 점검합니다."),
            ("확인할 지표", "영상에서 검증해야 할 실적·수요·시장 지표를 정리합니다."),
            ("투자자 체크포인트", "확정 사실과 불확실한 정보를 구분해 체크포인트로 제시합니다."),
        ):
            if len(result) >= limit:
                break
            keyword = f"{normalized_seed} {suffix}"
            if keyword.casefold() in seen:
                continue
            result.append(_seed_candidate(
                keyword,
                "입력 키워드를 벗어나지 않는 세부 영상 관점입니다. "
                "공개 YouTube 지표가 없으면 수치 우위를 추정하지 않습니다.",
                angle,
            ))
            seen.add(keyword.casefold())

        result[0]["is_outperformer"] = True
        return result[:limit]


# ──────────────────────────────────────────────────────────
# 유틸 함수
# ──────────────────────────────────────────────────────────
def _extract_keyword(title: str) -> tuple[str, bool]:
    """Return a usable topic phrase, never an entire clickbait title by default."""
    cleaned = re.sub(r"[\[\(].*?[\]\)]", " ", title or "")
    cleaned = re.sub(r"[#|｜].*$", " ", cleaned)
    cleaned = re.sub(r"(긴급|속보|충격|반드시|지금|왜|이유|전망|분석|공개)", " ", cleaned, flags=re.I)
    tokens = [token for token in re.findall(r"[A-Za-z0-9가-힣]+", cleaned) if len(token) >= 2]
    phrase = " ".join(tokens[:4]).strip()
    # Very short/empty titles are safer to display as-is than to invent a
    # normalised phrase. The flag lets UI/API consumers disclose that case.
    return (phrase or (title or "").strip(), not bool(phrase))


def _seed_specific_terms(seed: str) -> list[str]:
    """Extract terms that distinguish a user brief from a broad category."""
    stop_words = {
        "코스피", "코스닥", "주식", "증시", "시장", "경제", "이슈", "뉴스",
        "관련", "분석", "전망", "영향", "주가", "오늘", "최근",
    }
    terms = []
    for raw in re.split(r"\s+", seed):
        token = re.sub(r"[^0-9A-Za-z가-힣]", "", raw).strip()
        if not token or token in stop_words or token.isdigit():
            continue
        if token not in terms:
            terms.append(token)
    return terms


def _candidate_matches_seed(candidate: dict, terms: list[str]) -> bool:
    """Require meaningful overlap before a ranked candidate can be reused."""
    if not terms:
        return True
    text = " ".join(str(candidate.get(key, "")) for key in ("keyword", "reason", "content_angle"))
    # Canonical aliases (삼전→삼성전자, 3분기→Q3, etc.) take precedence over
    # literal substring matching so the discovery and script stages agree.
    if seed_match(" ".join(terms), text):
        return True
    normalized = re.sub(r"\s+", "", text).casefold()
    matches = [term for term in terms if term.casefold() in normalized]
    # A multi-word brief needs at least two core terms; a one-word brief needs
    # its one term.  This prevents a lone generic word such as "실적" from
    # pulling a Samsung-specific job toward an unrelated index story.
    required = 1 if len(terms) == 1 else 2
    return len(matches) >= required


def _seed_candidate(keyword: str, reason: str, content_angle: str) -> dict:
    return {
        "keyword": keyword,
        "search_volume": 0,
        "competition": "UNAVAILABLE",
        "reason": reason,
        "content_angle": content_angle,
        "source": "input",
        "estimated_interest": "medium",
        "engagement_ratio": 0.0,
        "outperformance_index": 0.0,
        "velocity_vph": 0.0,
        "evidence_video_ids": [],
        "is_outperformer": False,
        "source_videos": [],
        "seed_priority": True,
        "metrics_available": False,
    }


def _build_market_summary(market_data: dict) -> str:
    """시장 데이터를 Claude 프롬프트용 요약 텍스트로 변환"""
    lines = []

    kr = market_data.get("kr")
    if kr:
        idx = kr.get("index", {})
        kospi = idx.get("kospi")
        if kospi:
            lines.append(f"[한국] 코스피: {kospi['close']:,.1f}pt "
                         f"({kospi['change_pct']:+.2f}%)")
        kosdaq = idx.get("kosdaq")
        if kosdaq:
            lines.append(f"[한국] 코스닥: {kosdaq['close']:,.1f}pt "
                         f"({kosdaq['change_pct']:+.2f}%)")
        sd = kr.get("supply_demand", {})
        kospi_sd = sd.get("kospi", {})
        if kospi_sd:
            lines.append(f"외국인 코스피 순매수: {kospi_sd.get('foreign_net_buy', 'N/A')}")
        mi = kr.get("market_indicators", {})
        if mi.get("usd_krw"):
            lines.append(f"달러/원: {mi['usd_krw']:,.1f}원")

    us = market_data.get("us")
    if us:
        idx = us.get("index", {})
        sp500 = idx.get("sp500")
        if sp500:
            lines.append(f"[미국] S&P500: {sp500['close']:,.1f} "
                         f"({sp500['change_pct']:+.2f}%)")
        nasdaq = idx.get("nasdaq")
        if nasdaq:
            lines.append(f"[미국] 나스닥: {nasdaq['close']:,.1f} "
                         f"({nasdaq['change_pct']:+.2f}%)")
        macro = us.get("macro", {})
        if macro.get("fed_rate"):
            lines.append(f"연준 기준금리: {macro['fed_rate']:.2f}%")
        if macro.get("cpi"):
            lines.append(f"미국 CPI: {macro['cpi']:.1f}")

    assoc = market_data.get("associated_data")
    if assoc:
        lines.append(f"\n[연관 종목군 시세현황] (기준 주식: {assoc.get('main_keyword')})")
        for stock in assoc.get("associated_stocks", []):
            lines.append(f" - {stock['name']} ({stock['symbol']}): {stock['close']:,.2f} ({stock['change_pct']:+.2f}%)")

    return "\n".join(lines) if lines else "시장 데이터 수집 중..."

"""
Phase 3-1 — 키워드 탐색 워커 v2 (주식 콘텐츠 특화)

v2 변경사항:
  [신규] 실시간 경제 뉴스 RSS + 네이버 검색 API로 뉴스 기반 키워드 발굴
  [신규] pykrx + yfinance로 당일 시장 지표 수집 (market_snapshot)
  [기존] YouTube 트렌딩 분석 병행 유지
  [신규] Claude API로 뉴스 + YouTube 후보를 통합 순위화 + 콘텐츠 가능성 평가
  [신규] market_snapshot을 결과에 포함 → ScriptWorker에 재활용

흐름:
  1. 뉴스 RSS + 네이버 API → NLP 키워드 추출
  2. YouTube 트렌딩 → 점수 기반 후보 생성
  3. 시장 데이터 수집 (pykrx + yfinance)
  4. Claude로 통합 순위화 (시장 맥락 포함)
  5. 최종 후보 반환 (market_snapshot 포함)
"""
import os
import re
import json
import logging
from typing import Optional

from app.providers.factory import get_trending_video_analyzer
from app.workers.market_data_collector import MarketDataCollector
from app.workers.news_keyword_extractor import NewsKeywordExtractor

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


class KeywordWorker:

    def __init__(self):
        self.analyzer = get_trending_video_analyzer()
        self.collector = MarketDataCollector()
        self.extractor = NewsKeywordExtractor()

    def search(self, category: str, seed: str, limit: int = 5,
               outperformer_count: int = 1, job_id: int = 0) -> dict:

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
                logger.info(f"Claude 순위화 완료: {len(candidates)}개 후보")
            except Exception as e:
                logger.warning(f"Claude 순위화 실패, 폴백 사용: {e}")
                candidates = self._fallback_candidates(
                    news_keywords, yt_candidates, outperformer_count, limit
                )
        else:
            candidates = self._fallback_candidates(
                news_keywords, yt_candidates, outperformer_count, limit
            )

        logger.info(f"키워드 탐색 완료: {len(candidates)}개 최종 후보")

        return {
            "job_id": job_id,
            "seed": seed,
            "category": category,
            "candidates": candidates,
            "market_snapshot": market_data,   # ScriptWorker에 재활용
            "news_keyword_count": len(news_keywords),
            "yt_candidate_count": len(yt_candidates),
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
            f"'{c['keyword']}' (YouTube 종합점수 {c['composite_score']:.2f}, "
            f"outperformer={'예' if c.get('is_outperformer') else '아니오'})"
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

선정 기준:
1. 오늘 실제 시장 상황과 관련성이 높은가?
2. 시청자(개인 투자자)의 관심을 끌 수 있는 주제인가?
3. 20분 분량 영상으로 충분히 다룰 수 있는 깊이가 있는가?
4. 뉴스와 YouTube 양쪽에서 주목받고 있는가?

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "candidates": [
    {{
      "keyword": "키워드",
      "reason": "선정 이유 (시장 맥락 포함, 2-3문장)",
      "content_angle": "영상에서 다룰 핵심 관점",
      "source": "news|youtube|both",
      "estimated_interest": "high|medium|low"
    }}
  ]
}}"""

        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

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
                "is_outperformer": i == 0,
                "source_videos": [],
            })
        return result

    # ──────────────────────────────────────────────────────────
    # YouTube 점수 계산 (기존 로직 유지)
    # ──────────────────────────────────────────────────────────
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

            scored.append({
                "keyword": _extract_keyword(v.title),
                "composite_score": composite_score,
                "competition": competition,
                "engagement_ratio": engagement_ratio,
                "outperformance_index": outperformance_index,
                "velocity_vph": velocity_vph,
                "is_outperformer": False,
                "source": "youtube",
                "source_videos": [{
                    "title": v.title,
                    "channel_title": v.channel_title,
                    "views": v.views,
                    "subscribers": v.subscribers,
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


# ──────────────────────────────────────────────────────────
# 유틸 함수
# ──────────────────────────────────────────────────────────
def _extract_keyword(title: str) -> str:
    return title.strip()


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

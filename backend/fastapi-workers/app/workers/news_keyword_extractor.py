"""
뉴스 기반 키워드 추출기 — 한국/미국 경제 뉴스에서 핵심 키워드 발굴

한국:
  - RSS 피드: 한국경제, 매일경제, 조선비즈, Google뉴스(주식)
  - NAVER API HUB 뉴스 검색·검색어 트렌드 (별도 활성화 필요)
  - kiwipiepy 한국어 명사 추출 + TF-IDF 순위화

미국:
  - Finnhub general_news API (FINNHUB_API_KEY 필요)
  - NLTK/기본 파싱으로 영문 키워드 추출
"""
import re
import os
import logging
import time
from html import unescape
from datetime import date, datetime, timezone, timedelta
from collections import Counter
from typing import Optional
from urllib.parse import urlparse

import requests
import feedparser

from app.config import FINNHUB_API_KEY
from app.services.naver_api_hub import NaverApiHubClient, naver_api_hub_configured

logger = logging.getLogger(__name__)

KOREAN_FINANCE_NEWS_OUTLETS: list[dict[str, str]] = [
    {"name": "연합뉴스", "domain": "yna.co.kr"},
    {"name": "뉴스1", "domain": "news1.kr"},
    {"name": "뉴시스", "domain": "newsis.com"},
    {"name": "한국경제", "domain": "hankyung.com"},
    {"name": "매일경제", "domain": "mk.co.kr"},
    # chosun.com보다 먼저 판정해야 조선비즈 이름이 종합지로 덮이지 않는다.
    {"name": "조선비즈", "domain": "biz.chosun.com"},
    {"name": "이데일리", "domain": "edaily.co.kr"},
    {"name": "머니투데이", "domain": "mt.co.kr"},
    {"name": "파이낸셜뉴스", "domain": "fnnews.com"},
    {"name": "헤럴드경제", "domain": "herald.co.kr"},
    {"name": "서울경제", "domain": "sedaily.com"},
    {"name": "아시아경제", "domain": "asiae.co.kr"},
    {"name": "인베스트조선", "domain": "investchosun.com"},
    {"name": "글로벌이코노믹", "domain": "g-enews.com"},
    {"name": "비즈워치", "domain": "bizwatch.co.kr"},
    {"name": "조선일보", "domain": "chosun.com"},
    {"name": "중앙일보", "domain": "joongang.co.kr"},
    {"name": "동아일보", "domain": "donga.com"},
    {"name": "한국일보", "domain": "hankookilbo.com"},
    {"name": "전자신문", "domain": "etnews.com"},
    {"name": "뉴스핌", "domain": "newspim.com"},
    {"name": "더벨", "domain": "thebell.co.kr"},
    {"name": "한국금융신문", "domain": "fntimes.com"},
]

_EXCLUDED_NON_FINANCE_HOSTS = {"sports.chosun.com"}


def _is_finance_outlet(url: str) -> tuple[bool, str]:
    """URL 호스트가 승인된 금융 언론사 도메인인지 안전하게 판정한다."""
    if not url:
        return False, ""
    try:
        parsed = urlparse(str(url).strip())
        if parsed.scheme not in {"http", "https"}:
            return False, ""
        hostname = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return False, ""
    if not hostname or hostname in _EXCLUDED_NON_FINANCE_HOSTS:
        return False, ""
    for outlet in KOREAN_FINANCE_NEWS_OUTLETS:
        domain = outlet["domain"]
        if hostname == domain or hostname.endswith(f".{domain}"):
            return True, outlet["name"]
    return False, ""

# 한국 경제 뉴스 RSS 피드
KR_RSS_FEEDS = {
    "한국경제": "https://www.hankyung.com/feed/finance",
    "매일경제": "https://www.mk.co.kr/rss/30000001/",
    "조선비즈": "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml",
    "Google뉴스_코스피": "https://news.google.com/rss/search?q=코스피+주식&hl=ko&gl=KR&ceid=KR:ko",
    "Google뉴스_미국주식": "https://news.google.com/rss/search?q=미국주식+나스닥&hl=ko&gl=KR&ceid=KR:ko",
}

# 카테고리별 RSS 우선 피드 선택
CATEGORY_RSS_MAP = {
    "KOSPI": ["한국경제", "매일경제", "Google뉴스_코스피"],
    "KOSDAQ": ["한국경제", "매일경제", "조선비즈"],
    "US_STOCKS": ["Google뉴스_미국주식", "매일경제"],
    "GLOBAL_MACRO": ["한국경제", "매일경제", "조선비즈", "Google뉴스_코스피"],
    "INDIVIDUAL_STOCK": ["한국경제", "매일경제", "조선비즈"],
    "CUSTOM": list(KR_RSS_FEEDS.keys()),
}

# 불용어 (주식 뉴스에서 의미없는 단어)
KR_STOPWORDS = {
    "뉴스", "기자", "특파원", "제공", "관련", "대한", "따른", "통해", "위한", "관해",
    "이후", "이전", "최근", "현재", "오늘", "내일", "지난", "이번", "다음",
    "우리", "그", "이", "저", "것", "수", "등", "및", "의", "가", "이", "은", "는",
    "일", "월", "년", "분", "초", "시간", "만", "억", "조",
    "대표", "회사", "기업", "관계자", "발표", "보도", "전망", "예상", "분석",
}

# 주식/경제 관련 도메인 어휘 (kiwipiepy 사용자 사전)
FINANCE_VOCAB = [
    ("코스피", "NNP"), ("코스닥", "NNP"), ("HBM", "NNP"), ("ETF", "NNP"),
    ("AI반도체", "NNP"), ("양자컴퓨터", "NNP"), ("K배터리", "NNP"),
    ("외인", "NNG"), ("기관", "NNG"), ("개인", "NNG"), ("공매도", "NNG"),
    ("스티프닝", "NNG"), ("플래트닝", "NNG"), ("금리인하", "NNG"), ("금리인상", "NNG"),
    ("나스닥", "NNP"), ("다우존스", "NNP"), ("S&P500", "NNP"), ("VIX", "NNP"),
    ("FOMC", "NNP"), ("CPI", "NNP"), ("PCE", "NNP"), ("ISM", "NNP"),
    ("매수세", "NNG"), ("매도세", "NNG"), ("순매수", "NNG"), ("순매도", "NNG"),
    ("상승세", "NNG"), ("하락세", "NNG"), ("박스권", "NNG"), ("랠리", "NNG"),
]

EN_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "shall", "can", "need", "dare", "ought", "used",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "up", "about",
    "into", "through", "during", "before", "after", "above", "below",
    "and", "but", "or", "nor", "so", "yet", "both", "either", "neither",
    "not", "no", "nor", "as", "if", "than", "then", "because", "while",
    "said", "says", "according", "report", "reports", "reported", "sources",
    "new", "also", "its", "their", "this", "that", "these", "those",
}


class NewsKeywordExtractor:
    """경제 뉴스 RSS + API에서 주식 관련 키워드를 추출한다."""

    def __init__(self):
        self._kiwi = None  # 지연 로드

    def _get_kiwi(self):
        if self._kiwi is None:
            try:
                from kiwipiepy import Kiwi
                kiwi = Kiwi()
                for word, tag in FINANCE_VOCAB:
                    try:
                        kiwi.add_user_word(word, tag)
                    except Exception:
                        pass
                self._kiwi = kiwi
                logger.info("Kiwi NLP 초기화 완료")
            except ImportError:
                logger.warning("kiwipiepy 미설치 — 단순 정규식 키워드 사용")
        return self._kiwi

    # ─────────────────────────────────────────────────────
    # 한국 뉴스 키워드 추출 (메인)
    # ─────────────────────────────────────────────────────
    def extract_kr_keywords(self, category: str, seed: str = "",
                            top_n: int = 20) -> list[dict]:
        """
        RSS 피드 + 네이버 검색 API → kiwipiepy NLP → TF-IDF 순위화
        반환: [{"keyword": "삼성전자", "score": 0.85, "count": 12,
                "sources": ["한국경제", ...], "sample_headline": "..."}]
        """
        headlines = []

        # 1. RSS 피드 수집
        feed_names = CATEGORY_RSS_MAP.get(category, list(KR_RSS_FEEDS.keys()))
        for fname in feed_names:
            url = KR_RSS_FEEDS.get(fname)
            if not url:
                continue
            try:
                # requests로 타임아웃을 지정하여 안정적으로 콘텐츠를 먼저 가져온 후 feedparser로 파싱
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    for entry in feed.entries[:15]:
                        title = entry.get("title", "")
                        summary = entry.get("summary", "")
                        if title:
                            headlines.append({
                                "text": f"{title}. {summary}",
                                "source": fname,
                                "title": title,
                            })
                    logger.info(f"RSS {fname}: {len(feed.entries)}건 수집")
                else:
                    logger.warning(f"RSS {fname} HTTP 오류 (status: {resp.status_code})")
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"RSS {fname} 수집 실패: {e}")

        # 2. NAVER API HUB 뉴스 검색 (설정된 경우)
        if naver_api_hub_configured():
            naver_articles = self._fetch_naver_news(seed or "주식 코스피")
            headlines.extend(naver_articles)

        if not headlines:
            logger.warning("뉴스 수집 실패 — 빈 키워드 반환")
            return []

        # 3. kiwipiepy 명사 추출
        all_nouns = []
        doc_nouns = []  # TF-IDF용

        kiwi = self._get_kiwi()
        for article in headlines:
            text = _clean_text(article["text"])
            if kiwi:
                try:
                    result = kiwi.analyze(text)
                    nouns = [
                        t.form for sent in result
                        for t in sent[0]
                        if t.tag.startswith("NN") and len(t.form) >= 2
                        and t.form not in KR_STOPWORDS
                    ]
                except Exception:
                    nouns = _fallback_noun_extract(text)
            else:
                nouns = _fallback_noun_extract(text)
            all_nouns.extend(nouns)
            doc_nouns.append(nouns)

        # 4. TF-IDF 점수 계산
        keyword_data = _compute_tfidf(doc_nouns, headlines, top_n)

        # 5. seed 키워드 관련성 부스팅
        if seed:
            seed_tokens = set(seed.split())
            for item in keyword_data:
                if any(s in item["keyword"] for s in seed_tokens):
                    item["score"] = min(item["score"] * 1.3, 1.0)
            keyword_data.sort(key=lambda x: x["score"], reverse=True)

        self._attach_naver_trends(keyword_data)
        logger.info(f"한국 뉴스 키워드 {len(keyword_data)}개 추출 (category={category})")
        return keyword_data[:top_n]

    # ─────────────────────────────────────────────────────
    # 네이버 검색 API
    # ─────────────────────────────────────────────────────
    def search_recent_news(
        self,
        query: str,
        max_age_hours: int = 2,
        limit: int = 6,
        outlet_filter: bool = False,
    ) -> list[dict]:
        """NAVER API HUB를 우선 사용하고 Google News RSS를 보조로 사용한다.

        outlet_filter는 수동 긴급뉴스 확인에서만 명시적으로 활성화한다.
        기존 7일 후보 점수 경로는 기본값 False로 원래 수집 범위를 유지한다.
        """
        normalized = re.sub(r"\s+", " ", query or "").strip()
        if not normalized:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, min(max_age_hours, 24 * 30)))
        if naver_api_hub_configured():
            try:
                items = NaverApiHubClient().search_news(
                    normalized,
                    display=min(max(limit * 3, 10), 100),
                    sort="date",
                ).get("items", [])
                articles = []
                for item in items:
                    published_at = _parse_naver_published_at(item.get("pubDate"))
                    if published_at is None or published_at < cutoff:
                        continue
                    article_url = str(item.get("originallink") or item.get("link") or "")
                    outlet_name = ""
                    if outlet_filter:
                        is_match, outlet_name = _is_finance_outlet(article_url)
                        if not is_match:
                            continue
                    articles.append({
                        "title": _clean_text(item.get("title", "")),
                        "description": _clean_text(item.get("description", ""))[:200],
                        "source": outlet_name or "NAVER 뉴스",
                        "outlet": outlet_name,
                        "url": article_url,
                        "publishedAt": published_at.isoformat().replace("+00:00", "Z"),
                        "hoursSincePublish": round((datetime.now(timezone.utc) - published_at).total_seconds() / 3600, 1),
                    })
                    if len(articles) >= limit:
                        return articles
            except Exception as exc:
                logger.warning("NAVER API HUB 최근 뉴스 조회 실패(query=%s): %s", normalized, exc)
        try:
            response = requests.get(
                "https://news.google.com/rss/search",
                params={"q": normalized, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=8,
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            articles = []
            for entry in feed.entries:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if not published:
                    continue
                published_at = datetime(*published[:6], tzinfo=timezone.utc)
                if published_at < cutoff:
                    continue
                raw_source = entry.get("source", {})
                source_name = (
                    raw_source.get("title", "Google 뉴스")
                    if isinstance(raw_source, dict)
                    else str(raw_source or "Google 뉴스")
                )
                source_url = raw_source.get("href", "") if isinstance(raw_source, dict) else ""
                article_url = entry.get("link", "")
                outlet_name = ""
                if outlet_filter:
                    is_match, outlet_name = _is_finance_outlet(source_url or article_url)
                    if not is_match:
                        continue
                articles.append({
                    "title": re.sub(r"\s+", " ", unescape(entry.get("title", ""))).strip(),
                    "description": re.sub(
                        r"\s+",
                        " ",
                        unescape(re.sub(r"<[^>]+>", " ", entry.get("summary", ""))).replace("\xa0", " "),
                    ).strip()[:200],
                    "source": outlet_name or re.sub(r"\s+", " ", source_name).strip(),
                    "outlet": outlet_name,
                    "url": article_url,
                    "publishedAt": published_at.isoformat().replace("+00:00", "Z"),
                    "hoursSincePublish": round((datetime.now(timezone.utc) - published_at).total_seconds() / 3600, 1),
                })
                if len(articles) >= limit:
                    break
            return articles
        except Exception as exc:
            logger.warning("최근 Google 뉴스 조회 실패(query=%s): %s", normalized, exc)
            return []

    def search_recent_news_us_market(
        self,
        query: str,
        max_age_hours: int = 24,
        limit: int = 10,
    ) -> list[dict]:
        """Finnhub 공개 일반 뉴스에서 시간창과 검색어가 맞는 미국 기사를 반환한다."""
        api_key = os.environ.get("FINNHUB_API_KEY", "").strip() or FINNHUB_API_KEY
        normalized = re.sub(r"\s+", " ", query or "").strip().casefold()
        if not api_key or not normalized:
            if not api_key:
                logger.warning("FINNHUB_API_KEY 미설정 — 미국 시장 뉴스 건너뜀")
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, min(max_age_hours, 24 * 30)))
        try:
            import finnhub

            client = finnhub.Client(api_key=api_key)
            raw_news = client.general_news("general", min_id=0)
            articles = []
            for item in raw_news:
                published_at = datetime.fromtimestamp(int(item.get("datetime") or 0), tz=timezone.utc)
                if published_at < cutoff:
                    continue
                title = re.sub(r"\s+", " ", str(item.get("headline") or "")).strip()
                description = re.sub(r"\s+", " ", str(item.get("summary") or "")).strip()
                if normalized not in f"{title} {description}".casefold():
                    continue
                source = re.sub(r"\s+", " ", str(item.get("source") or "Finnhub")).strip()
                articles.append({
                    "title": title,
                    "description": description[:200],
                    "source": source,
                    "outlet": source,
                    "url": str(item.get("url") or ""),
                    "publishedAt": published_at.isoformat().replace("+00:00", "Z"),
                    "hoursSincePublish": round((datetime.now(timezone.utc) - published_at).total_seconds() / 3600, 1),
                })
                if len(articles) >= limit:
                    break
            return articles
        except Exception as exc:
            logger.warning("Finnhub news 조회 실패: %s", exc)
            return []

    def search_news_multi_window(self, query: str, limit: int = 12) -> dict:
        """24시간 뉴스 및 7일 뉴스 조회를 동시에 수행해 모멘텀 비교용 데이터를 반환한다."""
        recent_24h = self.search_recent_news(query, max_age_hours=24, limit=limit)
        recent_7d = self.search_recent_news(query, max_age_hours=24 * 7, limit=limit * 2)
        
        return {
            "query": query,
            "news_24h": recent_24h,
            "news_7d": recent_7d,
            "count_24h": len(recent_24h),
            "count_7d": len(recent_7d),
            "avg_daily_7d": round(len(recent_7d) / 7.0, 2),
        }

    def _fetch_naver_news(self, query: str, display: int = 20) -> list[dict]:
        """NAVER API HUB 뉴스 검색 → 헤드라인 리스트"""
        try:
            items = NaverApiHubClient().search_news(query, display=display, sort="date").get("items", [])
            for item in items:
                title = re.sub(r"<[^>]+>", "", item.get("title", ""))
                desc = re.sub(r"<[^>]+>", "", item.get("description", ""))
                articles.append({
                    "text": f"{title}. {desc}",
                    "source": "네이버뉴스",
                    "title": title,
                })
            logger.info(f"NAVER API HUB 뉴스: {len(articles)}건 수집 (query={query})")
            return articles
        except Exception as e:
            logger.warning(f"NAVER API HUB 뉴스 실패: {e}")
            return []

    def _attach_naver_trends(self, keyword_data: list[dict]) -> None:
        """상위 후보에 상대 검색 추이 원본을 덧붙인다. 점수·금융 수치에는 사용하지 않는다."""
        if not keyword_data or not naver_api_hub_configured():
            return
        groups = [
            {"groupName": str(item["keyword"]), "keywords": [str(item["keyword"])]}
            for item in keyword_data[:5]
            if str(item.get("keyword") or "").strip()
        ]
        if not groups:
            return
        end_date = date.today()
        start_date = end_date - timedelta(days=28)
        try:
            result = NaverApiHubClient().search_trend(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                time_unit="week",
                keyword_groups=groups,
            )
        except Exception as exc:
            logger.warning("NAVER API HUB 검색어 트렌드 조회 실패: %s", exc)
            return
        trend_by_title = {str(row.get("title") or ""): row.get("data") or [] for row in result.get("results", [])}
        for item in keyword_data:
            data = trend_by_title.get(str(item.get("keyword") or ""))
            if not data:
                continue
            item["naver_search_trend"] = {
                "source": "NAVER API HUB 검색어 트렌드",
                "start_date": result.get("startDate"),
                "end_date": result.get("endDate"),
                "time_unit": result.get("timeUnit"),
                "data": data,
                "ratio_note": "절대 검색량이 아닌 요청 결과 내 상대 지표입니다.",
            }

    # ─────────────────────────────────────────────────────
    # 미국 뉴스 키워드 추출
    # ─────────────────────────────────────────────────────
    def extract_us_keywords(self, top_n: int = 20) -> list[dict]:
        """Finnhub market news → 영문 키워드 추출"""
        headlines = []

        if FINNHUB_API_KEY:
            try:
                import finnhub

                fc = finnhub.Client(api_key=FINNHUB_API_KEY)
                news = fc.general_news("general", min_id=0)
                for n in news[:30]:
                    headline = n.get("headline", "")
                    summary = n.get("summary", "")
                    if headline:
                        headlines.append({
                            "text": f"{headline}. {summary}",
                            "source": n.get("source", "Finnhub"),
                            "title": headline,
                        })
                logger.info(f"Finnhub 뉴스: {len(headlines)}건 수집")
            except Exception as e:
                logger.warning(f"Finnhub 뉴스 수집 실패: {e}")

        if not headlines:
            return []

        # 영문 명사구 추출 (단순 방식 — Java 없이)
        doc_nouns = []
        for article in headlines:
            nouns = _extract_en_nouns(article["text"])
            doc_nouns.append(nouns)

        return _compute_tfidf(doc_nouns, headlines, top_n)


# ─────────────────────────────────────────────────────────
# 유틸 함수
# ─────────────────────────────────────────────────────────
def _clean_text(text: str) -> str:
    """HTML, 특수문자 제거"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    return text.strip()


def _parse_naver_published_at(value: object) -> datetime | None:
    try:
        return datetime.strptime(str(value or ""), "%a, %d %b %Y %H:%M:%S %z").astimezone(timezone.utc)
    except ValueError:
        return None


def _fallback_noun_extract(text: str) -> list[str]:
    """kiwipiepy 없을 때 단순 정규식 명사 추출 (2-6자 한글 단어)"""
    return re.findall(r"[가-힣]{2,6}", text)


def _extract_en_nouns(text: str) -> list[str]:
    """영문 텍스트에서 대문자로 시작하는 명사구 추출"""
    text = re.sub(r"<[^>]+>", "", text)
    # 대문자 단어, 숫자%, 기업명 패턴 추출
    tokens = re.findall(r"\b[A-Z][a-zA-Z]{2,}\b|\b[A-Z]{2,}\b|\b\d+\.?\d*%?\b", text)
    return [t for t in tokens if t.lower() not in EN_STOPWORDS and len(t) >= 2]


def _compute_tfidf(doc_nouns: list, articles: list, top_n: int) -> list[dict]:
    """TF-IDF 기반 키워드 순위화"""
    if not doc_nouns:
        return []

    # 문서 빈도 계산
    doc_count = len(doc_nouns)
    df = Counter()
    for nouns in doc_nouns:
        for noun in set(nouns):
            df[noun] += 1

    # TF-IDF 점수
    tf = Counter()
    for nouns in doc_nouns:
        tf.update(nouns)

    scores = {}
    import math
    total_terms = sum(tf.values()) or 1
    for term, count in tf.items():
        if count < 2:  # 최소 2회 이상 등장
            continue
        tf_score = count / total_terms
        idf = math.log((doc_count + 1) / (df[term] + 1)) + 1
        scores[term] = tf_score * idf

    # 정규화
    max_score = max(scores.values()) if scores else 1
    result = []
    seen = set()
    for kw, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        if kw in seen:
            continue
        seen.add(kw)
        # 연관 헤드라인 찾기
        sample = next(
            (a["title"] for a in articles if kw in a["text"]), ""
        )
        sources = list({a["source"] for a in articles if kw in a["text"]})[:3]
        result.append({
            "keyword": kw,
            "score": round(score / max_score, 4),
            "count": tf[kw],
            "sources": sources,
            "sample_headline": sample[:80] if sample else "",
        })
        if len(result) >= top_n:
            break

    return result

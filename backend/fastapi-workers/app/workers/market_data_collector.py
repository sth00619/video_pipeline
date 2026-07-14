"""
시장 데이터 수집기 — 한국/미국 주식 시장 실시간 데이터

데이터 소스:
  KR: pykrx (KRX 직접), FinanceDataReader (보조), feedparser (RSS)
  US: yfinance (시세), finnhub (뉴스·감성), fredapi (거시경제)

모든 수집은 실패 시 graceful degradation (빈 값 반환, 예외 억제)
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional
import requests

logger = logging.getLogger(__name__)

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
DART_API_KEY = os.environ.get("DART_API_KEY", "")

# 한국 주요 ETF/지수 코드
KR_INDEX_TICKERS = {
    "KOSPI": "KS11",
    "KOSDAQ": "KQ11",
    "KRW_USD": "USD/KRW",
}

# 미국 주요 지수 야후 파이낸스 심볼
US_INDEX_TICKERS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "vix": "^VIX",
    "dxy": "DX-Y.NYB",
}

# FRED 거시경제 시리즈 ID
FRED_SERIES = {
    "fed_rate": "FEDFUNDS",
    "cpi": "CPIAUCSL",
    "unemployment": "UNRATE",
    "us_10yr_yield": "DGS10",
    "dollar_index": "DTWEXBGS",
}


# 연관 종목군 고정 매핑
ASSOCIATED_STOCKS_MAP = {
    "삼성전자": [
        {"name": "SK하이닉스", "symbol": "000660", "market": "KR"},
        {"name": "한미반도체", "symbol": "042700", "market": "KR"},
        {"name": "이수페타시스", "symbol": "007660", "market": "KR"},
        {"name": "원익IPS", "symbol": "240810", "market": "KR"}
    ],
    "SK하이닉스": [
        {"name": "삼성전자", "symbol": "005930", "market": "KR"},
        {"name": "한미반도체", "symbol": "042700", "market": "KR"},
        {"name": "이수페타시스", "symbol": "007660", "market": "KR"},
        {"name": "HPSP", "symbol": "403020", "market": "KR"}
    ],
    "엔비디아": [
        {"name": "AMD", "symbol": "AMD", "market": "US"},
        {"name": "TSMC", "symbol": "TSM", "market": "US"},
        {"name": "ASML", "symbol": "ASML", "market": "US"},
        {"name": "인텔", "symbol": "INTC", "market": "US"}
    ],
    "테슬라": [
        {"name": "LG에너지솔루션", "symbol": "373220", "market": "KR"},
        {"name": "삼성SDI", "symbol": "006400", "market": "KR"},
        {"name": "에코프로비엠", "symbol": "247540", "market": "KR"},
        {"name": "엘앤에프", "symbol": "066970", "market": "KR"}
    ],
    "애플": [
        {"name": "LG이노텍", "symbol": "011070", "market": "KR"},
        {"name": "비에이치", "symbol": "090460", "market": "KR"},
        {"name": "구글", "symbol": "GOOGL", "market": "US"},
        {"name": "마이크로소프트", "symbol": "MSFT", "market": "US"}
    ]
}


def get_associated_stocks(keyword: str) -> list[dict]:
    # 1. 키워드 정제
    cleaned = keyword.replace("전망", "").replace("주가", "").replace("분석", "").strip()
    
    # 2. 맵 매칭 확인
    for key, stocks in ASSOCIATED_STOCKS_MAP.items():
        if key in cleaned or cleaned in key:
            return stocks
            
    # 3. Fallback: KRX listing에서 유사 업종(Sector) 검색
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("KRX")
        if df is not None and not df.empty:
            match = df[df["Name"].str.contains(cleaned, case=False, na=False)]
            if not match.empty:
                sector = match.iloc[0].get("Sector")
                if sector:
                    same_sector = df[(df["Sector"] == sector) & (df["Name"] != cleaned)].head(4)
                    return [
                        {"name": row["Name"], "symbol": row["Code"], "market": "KR"}
                        for _, row in same_sector.iterrows()
                    ]
    except Exception as e:
        logger.warning(f"Associated stocks fallback extraction failed: {e}")
        
    return [
        {"name": "삼성전자", "symbol": "005930", "market": "KR"},
        {"name": "SK하이닉스", "symbol": "000660", "market": "KR"},
        {"name": "현대차", "symbol": "005380", "market": "KR"},
        {"name": "원익IPS", "symbol": "240810", "market": "KR"}
    ]


class MarketDataCollector:
    """
    카테고리별 실시간 시장 데이터 수집기.
    수집 실패 시 None/빈 dict으로 graceful fallback.
    """

    def collect_associated_stocks_data(self, keyword: str) -> dict:
        associated_list = get_associated_stocks(keyword)
        results = []
        
        import FinanceDataReader as fdr
        import yfinance as yf
        
        for stock in associated_list:
            name = stock["name"]
            symbol = stock["symbol"]
            market = stock["market"]
            
            close_val = 0.0
            change_pct = 0.0
            
            try:
                if market == "KR":
                    df = fdr.DataReader(symbol)
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        prev = df.iloc[-2] if len(df) > 1 else latest
                        close_val = float(latest["Close"])
                        change_pct = float((latest["Close"] - prev["Close"]) / prev["Close"] * 100)
                else:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period="5d")
                    if not hist.empty:
                        latest = hist.iloc[-1]
                        prev = hist.iloc[-2] if len(hist) > 1 else latest
                        close_val = float(latest["Close"])
                        change_pct = float((latest["Close"] - prev["Close"]) / prev["Close"] * 100)
            except Exception as e:
                logger.warning(f"Failed to fetch market data for associated stock {name} ({symbol}): {e}")
                
            results.append({
                "name": name,
                "symbol": symbol,
                "market": market,
                "close": round(close_val, 2),
                "change_pct": round(change_pct, 2)
            })
            
        return {
            "main_keyword": keyword,
            "associated_stocks": results
        }

    def collect_for_category(self, category: str, keyword: str) -> dict:
        """카테고리에 따라 한국/미국/양쪽 데이터 자동 수집"""
        kr_categories = {"KOSPI", "KOSDAQ", "INDIVIDUAL_STOCK", "ASSOCIATED_STOCKS"}
        us_categories = {"US_STOCKS"}

        result = {
            "category": category,
            "keyword": keyword,
            "collected_at": datetime.now().isoformat(),
            "kr": None,
            "us": None,
            "associated_data": None
        }

        if category in kr_categories:
            result["kr"] = self.collect_kr(keyword, category)
        elif category in us_categories:
            result["us"] = self.collect_us(keyword)
        else:  # GLOBAL_MACRO, CRYPTO, CUSTOM
            result["kr"] = self.collect_kr(keyword, category)
            result["us"] = self.collect_us(keyword)

        if category == "ASSOCIATED_STOCKS":
            result["associated_data"] = self.collect_associated_stocks_data(keyword)

        return result

    # ─────────────────────────────────────────────────────
    # 한국 시장 데이터
    # ─────────────────────────────────────────────────────
    def collect_kr(self, keyword: str, category: str = "KOSPI") -> dict:
        """pykrx + FinanceDataReader로 한국 시장 데이터 수집"""
        data = {
            "index": {},
            "chart_series": {},
            "supply_demand": {},
            "top_stocks": [],
            "market_indicators": {},
            "data_date": datetime.now().strftime("%Y-%m-%d"),
        }

        today = datetime.now().strftime("%Y%m%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

        # 1. 코스피/코스닥 지수 (FinanceDataReader 우선, pykrx 폴백)
        try:
            import FinanceDataReader as fdr
            # 코스피 지수
            kospi_df = fdr.DataReader("KS11")
            if not kospi_df.empty:
                latest = kospi_df.iloc[-1]
                prev = kospi_df.iloc[-2] if len(kospi_df) > 1 else latest
                change = latest["Close"] - prev["Close"]
                change_pct = (latest["Close"] - prev["Close"]) / prev["Close"] * 100
                data["index"]["kospi"] = {
                    "close": float(latest["Close"]),
                    "change": float(change),
                    "change_pct": round(float(change_pct), 2),
                    "volume": int(latest.get("Volume", 0)),
                    "trading_value": int(latest.get("Amount", 0)),
                }
                series = _to_chart_series(kospi_df)
                if series:
                    data["chart_series"]["kospi"] = series
                logger.info(f"FinanceDataReader 코스피 지수 수집: {data['index']['kospi']['close']}")
        except Exception as e:
            logger.warning(f"FinanceDataReader 코스피 수집 실패: {e}")
            # pykrx 폴백
            try:
                from pykrx import stock as krx
                kospi_df = krx.get_index_ohlcv_by_date(week_ago, today, "1001")
                if not kospi_df.empty:
                    latest = kospi_df.iloc[-1]
                    prev = kospi_df.iloc[-2] if len(kospi_df) > 1 else latest
                    data["index"]["kospi"] = {
                        "close": float(latest["종가"]),
                        "change": float(latest["종가"] - prev["종가"]),
                        "change_pct": round(float((latest["종가"] - prev["종가"]) / prev["종가"] * 100), 2),
                        "volume": int(latest.get("거래량", 0)),
                        "trading_value": int(latest.get("거래대금", 0)),
                    }
            except Exception as pe:
                logger.warning(f"pykrx 코스피 폴백 실패: {pe}")

        try:
            import FinanceDataReader as fdr
            # 코스닥 지수
            kosdaq_df = fdr.DataReader("KQ11")
            if not kosdaq_df.empty:
                latest = kosdaq_df.iloc[-1]
                prev = kosdaq_df.iloc[-2] if len(kosdaq_df) > 1 else latest
                change = latest["Close"] - prev["Close"]
                change_pct = (latest["Close"] - prev["Close"]) / prev["Close"] * 100
                data["index"]["kosdaq"] = {
                    "close": float(latest["Close"]),
                    "change": float(change),
                    "change_pct": round(float(change_pct), 2),
                    "volume": int(latest.get("Volume", 0)),
                }
                series = _to_chart_series(kosdaq_df)
                if series:
                    data["chart_series"]["kosdaq"] = series
                logger.info(f"FinanceDataReader 코스닥 지수 수집: {data['index']['kosdaq']['close']}")
        except Exception as e:
            logger.warning(f"FinanceDataReader 코스닥 수집 실패: {e}")
            # pykrx 폴백
            try:
                from pykrx import stock as krx
                kosdaq_df = krx.get_index_ohlcv_by_date(week_ago, today, "2001")
                if not kosdaq_df.empty:
                    latest = kosdaq_df.iloc[-1]
                    prev = kosdaq_df.iloc[-2] if len(kosdaq_df) > 1 else latest
                    data["index"]["kosdaq"] = {
                        "close": float(latest["종가"]),
                        "change": float(latest["종가"] - prev["종가"]),
                        "change_pct": round(float((latest["종가"] - prev["종가"]) / prev["종가"] * 100), 2),
                        "volume": int(latest.get("거래량", 0)),
                    }
            except Exception as pe:
                logger.warning(f"pykrx 코스닥 폴백 실패: {pe}")

        # 2. 외국인·기관 순매수 (pykrx)
        try:
            from pykrx import stock as krx

            investor_df = krx.get_market_trading_value_by_date(week_ago, today, "KOSPI")
            if not investor_df.empty:
                latest = investor_df.iloc[-1]
                data["supply_demand"]["kospi"] = {
                    "foreign_net_buy": _format_krw(latest.get("외국인합계", 0)),
                    "institution_net_buy": _format_krw(latest.get("기관합계", 0)),
                    "retail_net_buy": _format_krw(latest.get("개인", 0)),
                }
                logger.info(f"외인 수급 수집: 외국인 {data['supply_demand']['kospi']['foreign_net_buy']}")
        except Exception as e:
            logger.warning(f"pykrx 수급 수집 실패: {e}")

        # 3. 시가총액 상위 종목 (FinanceDataReader)
        try:
            import FinanceDataReader as fdr

            market = "KOSPI" if category in ("KOSPI", "CUSTOM", "GLOBAL_MACRO") else "KOSDAQ"
            listing = fdr.StockListing(market)
            if listing is not None and not listing.empty:
                # 시총 상위 10개 (Market Cap 기준)
                cap_col = next((c for c in listing.columns if "Marcap" in c or "시가총액" in c), None)
                if cap_col:
                    top = listing.nlargest(10, cap_col)[["Name", "Code", cap_col]].dropna()
                    data["top_stocks"] = [
                        {"name": row["Name"], "symbol": row["Code"],
                         "market_cap": _format_krw(row[cap_col])}
                        for _, row in top.iterrows()
                    ]
        except Exception as e:
            logger.warning(f"FinanceDataReader 상위종목 수집 실패: {e}")

        # 4. 환율 (달러/원)
        try:
            import FinanceDataReader as fdr

            krw = fdr.DataReader("USD/KRW", week_ago[:4] + "-" + week_ago[4:6] + "-" + week_ago[6:])
            if not krw.empty:
                data["market_indicators"]["usd_krw"] = round(float(krw["Close"].iloc[-1]), 2)
        except Exception as e:
            logger.warning(f"환율 수집 실패: {e}")

        return data

    # ─────────────────────────────────────────────────────
    # 미국 시장 데이터
    # ─────────────────────────────────────────────────────
    def collect_us(self, keyword: str) -> dict:
        """yfinance + Finnhub + FRED로 미국 시장 데이터 수집"""
        data = {
            "index": {},
            "chart_series": {},
            "macro": {},
            "sector": {},
            "news_sentiment": None,
            "data_date": datetime.now().strftime("%Y-%m-%d"),
        }

        # 1. 주요 지수 (yfinance)
        try:
            import yfinance as yf

            for name, symbol in US_INDEX_TICKERS.items():
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period="1mo")
                    if not hist.empty:
                        latest_close = float(hist["Close"].iloc[-1])
                        prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else latest_close
                        change_pct = round((latest_close - prev_close) / prev_close * 100, 2)
                        data["index"][name] = {
                            "close": round(latest_close, 2),
                            "change_pct": change_pct,
                            "volume": int(hist["Volume"].iloc[-1]),
                        }
                        series = _to_chart_series(hist)
                        if series:
                            data["chart_series"][name] = series
                except Exception:
                    pass
            logger.info(f"미국 지수 수집: {list(data['index'].keys())}")
        except Exception as e:
            logger.warning(f"yfinance 미국 지수 수집 실패: {e}")

        # 2. 거시경제 지표 (FRED)
        if FRED_API_KEY:
            try:
                from fredapi import Fred

                fred = Fred(api_key=FRED_API_KEY)
                for key, series_id in FRED_SERIES.items():
                    try:
                        series = fred.get_series(series_id)
                        if series is not None and not series.empty:
                            data["macro"][key] = round(float(series.dropna().iloc[-1]), 3)
                    except Exception:
                        pass
                logger.info(f"FRED 거시경제 수집: {list(data['macro'].keys())}")
            except Exception as e:
                logger.warning(f"FRED 수집 실패: {e}")
        else:
            # FRED 키 없으면 정적 추정값 사용 (최근 공개값 참고)
            data["macro"]["note"] = "FRED_API_KEY 미설정 - 공식 FRED 사이트 참고"

        # 3. Finnhub 시장 뉴스 + 감성
        if FINNHUB_API_KEY:
            try:
                import finnhub

                fc = finnhub.Client(api_key=FINNHUB_API_KEY)
                news = fc.general_news("general", min_id=0)
                if news:
                    data["news_sentiment"] = {
                        "headline_count": len(news),
                        "top_headlines": [
                            {"headline": n.get("headline", ""), "source": n.get("source", ""),
                             "datetime": n.get("datetime", 0)}
                            for n in news[:5]
                        ],
                    }
                logger.info(f"Finnhub 뉴스 {len(news)}건 수집")
            except Exception as e:
                logger.warning(f"Finnhub 뉴스 수집 실패: {e}")

        return data

    def collect_finnhub_sentiment(self, symbol: str) -> Optional[dict]:
        """Finnhub 개별 종목 뉴스 감성지수"""
        if not FINNHUB_API_KEY:
            return None
        try:
            import finnhub

            fc = finnhub.Client(api_key=FINNHUB_API_KEY)
            sentiment = fc.news_sentiment(symbol)
            return {
                "buzz_weekly_average": sentiment.get("buzz", {}).get("weeklyAverage", 0),
                "sentiment_score": sentiment.get("sentiment", {}).get("bullishPercent", 0),
                "articles_in_last_week": sentiment.get("buzz", {}).get("articlesInLastWeek", 0),
            }
        except Exception as e:
            logger.warning(f"Finnhub 감성 수집 실패 ({symbol}): {e}")
            return None


def _format_krw(value) -> str:
    """억 원 단위로 포맷팅"""
    try:
        v = int(value)
        if abs(v) >= 100_000_000:
            return f"{v // 100_000_000:+,}억원"
        elif abs(v) >= 10_000:
            return f"{v // 10_000:+,}만원"
        return f"{v:+,}원"
    except Exception:
        return str(value)


def _to_chart_series(dataframe, limit: int = 30) -> list[dict]:
    """Serialize only collected closing prices; do not fabricate missing dates."""
    try:
        if dataframe is None or dataframe.empty or "Close" not in dataframe.columns:
            return []
        rows = dataframe.tail(limit)
        return [
            {"date": str(index)[:10], "close": round(float(row["Close"]), 4)}
            for index, row in rows.iterrows()
            if row.get("Close") is not None
        ]
    except Exception:
        return []

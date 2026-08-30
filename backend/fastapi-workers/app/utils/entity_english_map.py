"""
통합 엔티티 레지스트리 및 영문 변환 모듈 (app/utils/entity_english_map.py).

파이프라인 전역에서 사용되는 200개 이상의 금융/기업/원자재/지수 엔티티의
정확한 IR 공식 영문 사명(english_official) 및 가상 라벨(fictional_label)을 단일 진실 출처(SSOT)로 관리한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass(frozen=True)
class EntityInfo:
    korean: str
    english_official: str
    fictional_label: str
    category: str

# ---------------------------------------------------------------------------
# 200개+ 통합 엔티티 레지스트리 데이터베이스
# ---------------------------------------------------------------------------
_RAW_ENTITY_LIST: list[EntityInfo] = [
    # -----------------------------------------------------------------------
    # A. 국내 대형주 (KOSPI 시총 상위 ~50개+)
    # -----------------------------------------------------------------------
    EntityInfo("삼성전자", "Samsung Electronics", "SCREEN CORP K", "kospi_large"),
    EntityInfo("SK하이닉스", "SK Hynix", "SEMI CORP K", "kospi_large"),
    EntityInfo("LG에너지솔루션", "LG Energy Solution", "BATTERY CORP K", "kospi_large"),
    EntityInfo("삼성바이오로직스", "Samsung Biologics", "BIO PHARMA CORP K2", "kospi_large"),
    EntityInfo("현대차", "Hyundai Motor", "EV AUTOMAKER K", "kospi_large"),
    EntityInfo("기아", "Kia", "EV AUTOMAKER K2", "kospi_large"),
    EntityInfo("셀트리온", "Celltrion", "BIO PHARMA CORP K", "kospi_large"),
    EntityInfo("삼성SDI", "Samsung SDI", "BATTERY CORP K2", "kospi_large"),
    EntityInfo("POSCO홀딩스", "POSCO Holdings", "STEEL CORP K", "kospi_large"),
    EntityInfo("포스코", "POSCO", "STEEL CORP K", "kospi_large"),
    EntityInfo("NAVER", "NAVER", "SEARCH CORP K", "kospi_large"),
    EntityInfo("네이버", "NAVER", "SEARCH CORP K", "kospi_large"),
    EntityInfo("카카오", "Kakao", "PLATFORM CORP K", "kospi_large"),
    EntityInfo("현대모비스", "Hyundai Mobis", "AUTO PARTS K", "kospi_large"),
    EntityInfo("LG화학", "LG Chem", "CHEM CORP K", "kospi_large"),
    EntityInfo("삼성생명", "Samsung Life Insurance", "INSURANCE CORP K", "kospi_large"),
    EntityInfo("SK스퀘어", "SK Square", "INVESTMENT CORP K", "kospi_large"),
    EntityInfo("한화에어로스페이스", "Hanwha Aerospace", "AERO CORP K", "kospi_large"),
    EntityInfo("HD현대중공업", "HD Hyundai Heavy Industries", "HEAVY IND K", "kospi_large"),
    EntityInfo("두산에너빌리티", "Doosan Enerbility", "ENERGY CORP K", "kospi_large"),
    EntityInfo("KB금융", "KB Financial Group", "FIN CORP K", "kospi_large"),
    EntityInfo("신한지주", "Shinhan Financial Group", "FIN CORP K2", "kospi_large"),
    EntityInfo("신한금융", "Shinhan Financial Group", "FIN CORP K2", "kospi_large"),
    EntityInfo("하나금융지주", "Hana Financial Group", "FIN CORP K3", "kospi_large"),
    EntityInfo("하나금융", "Hana Financial Group", "FIN CORP K3", "kospi_large"),
    EntityInfo("우리금융지주", "Woori Financial Group", "FIN CORP K4", "kospi_large"),
    EntityInfo("우리금융", "Woori Financial Group", "FIN CORP K4", "kospi_large"),
    EntityInfo("LG전자", "LG Electronics", "DEVICE CORP K", "kospi_large"),
    EntityInfo("SK이노베이션", "SK Innovation", "ENERGY CORP K2", "kospi_large"),
    EntityInfo("삼성물산", "Samsung C&T", "TRADING CORP K", "kospi_large"),
    EntityInfo("삼성화재", "Samsung Fire & Marine Insurance", "INSURANCE CORP K2", "kospi_large"),
    EntityInfo("KT", "KT Corporation", "TELECOM CORP K2", "kospi_large"),
    EntityInfo("SK텔레콤", "SK Telecom", "TELECOM CORP K", "kospi_large"),
    EntityInfo("LG생활건강", "LG Household & Health Care", "BEAUTY CORP K", "kospi_large"),
    EntityInfo("한국전력", "KEPCO", "POWER CORP K", "kospi_large"),
    EntityInfo("현대제철", "Hyundai Steel", "STEEL CORP K2", "kospi_large"),
    EntityInfo("롯데케미칼", "Lotte Chemical", "CHEM CORP K2", "kospi_large"),
    EntityInfo("한화솔루션", "Hanwha Solutions", "SOLAR CORP K", "kospi_large"),
    EntityInfo("S-Oil", "S-Oil", "OIL CORP K", "kospi_large"),
    EntityInfo("에스오일", "S-Oil", "OIL CORP K", "kospi_large"),
    EntityInfo("GS", "GS Holdings", "HOLDINGS CORP K", "kospi_large"),
    EntityInfo("CJ제일제당", "CJ CheilJedang", "FOOD CORP K", "kospi_large"),
    EntityInfo("대한항공", "Korean Air", "AIRLINE CORP K", "kospi_large"),
    EntityInfo("아시아나항공", "Asiana Airlines", "AIRLINE CORP K2", "kospi_large"),
    EntityInfo("HMM", "HMM", "SHIPPING CORP K", "kospi_large"),
    EntityInfo("현대글로비스", "Hyundai Glovis", "LOGISTICS CORP K", "kospi_large"),
    EntityInfo("크래프톤", "Krafton", "GAME CORP K", "kospi_large"),
    EntityInfo("NC소프트", "NCSOFT", "GAME CORP K2", "kospi_large"),
    EntityInfo("엔씨소프트", "NCSOFT", "GAME CORP K2", "kospi_large"),
    EntityInfo("넷마블", "Netmarble", "GAME CORP K3", "kospi_large"),
    EntityInfo("하이브", "HYBE", "ENTERTAINMENT CORP K", "kospi_large"),
    EntityInfo("한미약품", "Hanmi Pharm", "PHARMA CORP K", "kospi_large"),
    EntityInfo("유한양행", "Yuhan Corporation", "PHARMA CORP K2", "kospi_large"),
    EntityInfo("GC녹십자", "GC Pharma", "PHARMA CORP K3", "kospi_large"),

    # -----------------------------------------------------------------------
    # B. 코스닥 및 중소형 주요주 (~30개+)
    # -----------------------------------------------------------------------
    EntityInfo("에코프로", "Ecopro", "ECO CORP K", "kosdaq_mid"),
    EntityInfo("에코프로비엠", "Ecopro BM", "BATTERY MAT CORP K", "kosdaq_mid"),
    EntityInfo("알테오젠", "Alteogen", "BIO TECH CORP K", "kosdaq_mid"),
    EntityInfo("HLB", "HLB", "BIO TECH CORP K2", "kosdaq_mid"),
    EntityInfo("파두", "FADU", "FABLESS CORP K", "kosdaq_mid"),
    EntityInfo("쎄트렉아이", "Satrec Initiative", "SATELLITE CORP K", "kosdaq_mid"),
    EntityInfo("삼천당제약", "Samchundang Pharm", "PHARMA CORP K4", "kosdaq_mid"),
    EntityInfo("레인보우로보틱스", "Rainbow Robotics", "ROBOT CORP K", "kosdaq_mid"),
    EntityInfo("엔켐", "Enchem", "CHEM CORP K3", "kosdaq_mid"),
    EntityInfo("셀트리온제약", "Celltrion Pharm", "BIO PHARMA CORP K3", "kosdaq_mid"),
    EntityInfo("리가켐바이오", "LigaChem Biosciences", "BIO TECH CORP K3", "kosdaq_mid"),
    EntityInfo("클래시스", "Classys", "MEDTECH CORP K", "kosdaq_mid"),
    EntityInfo("펄어비스", "Pearl Abyss", "GAME CORP K4", "kosdaq_mid"),
    EntityInfo("씨젠", "Seegene", "DIAGNOSTICS CORP K", "kosdaq_mid"),
    EntityInfo("카카오게임즈", "Kakao Games", "GAME CORP K5", "kosdaq_mid"),
    EntityInfo("JYP Ent.", "JYP Entertainment", "ENTERTAINMENT CORP K2", "kosdaq_mid"),
    EntityInfo("JYP엔터", "JYP Entertainment", "ENTERTAINMENT CORP K2", "kosdaq_mid"),
    EntityInfo("SM엔터", "SM Entertainment", "ENTERTAINMENT CORP K3", "kosdaq_mid"),
    EntityInfo("YG엔터", "YG Entertainment", "ENTERTAINMENT CORP K4", "kosdaq_mid"),
    EntityInfo("포스코DX", "POSCO DX", "IT SERVICES K", "kosdaq_mid"),
    EntityInfo("원익IPS", "Wonik IPS", "SEMI EQUIP K", "kosdaq_mid"),
    EntityInfo("리노공업", "Leeno Industrial", "SEMI PARTS K", "kosdaq_mid"),
    EntityInfo("동진쎄미켐", "Dongjin Semichem", "SEMI MAT K", "kosdaq_mid"),
    EntityInfo("솔브레인", "SoulBrain", "SEMI MAT K2", "kosdaq_mid"),
    EntityInfo("주성엔지니어링", "Jusung Engineering", "SEMI EQUIP K2", "kosdaq_mid"),
    EntityInfo("파두", "FADU", "FABLESS CORP K", "kosdaq_mid"),
    EntityInfo("HPSP", "HPSP", "SEMI EQUIP K3", "kosdaq_mid"),
    EntityInfo("이오테크닉스", "EO Technics", "LASER EQUIP K", "kosdaq_mid"),

    # -----------------------------------------------------------------------
    # C. 미국 빅테크 및 해외 대형주 (~40개+)
    # -----------------------------------------------------------------------
    EntityInfo("애플", "Apple", "DEVICE CORP US", "us_tech"),
    EntityInfo("마이크로소프트", "Microsoft", "CLOUD CORP US", "us_tech"),
    EntityInfo("엔비디아", "Nvidia", "AI CHIP CORP", "us_tech"),
    EntityInfo("알파벳", "Alphabet", "SEARCH CORP US", "us_tech"),
    EntityInfo("구글", "Google", "SEARCH CORP US", "us_tech"),
    EntityInfo("아마존", "Amazon", "CLOUD CORP US2", "us_tech"),
    EntityInfo("메타", "Meta Platforms", "SOCIAL CORP US", "us_tech"),
    EntityInfo("테슬라", "Tesla", "EV AUTOMAKER US", "us_tech"),
    EntityInfo("브로드컴", "Broadcom", "CHIP CORP US", "us_tech"),
    EntityInfo("일라이릴리", "Eli Lilly", "PHARMA CORP US", "us_tech"),
    EntityInfo("AMD", "AMD", "CPU CORP US2", "us_tech"),
    EntityInfo("마이크론", "Micron Technology", "DRAM CORP US", "us_tech"),
    EntityInfo("인텔", "Intel", "CPU CORP US", "us_tech"),
    EntityInfo("퀄컴", "Qualcomm", "MOBILE CHIP US", "us_tech"),
    EntityInfo("넷플릭스", "Netflix", "STREAMING US", "us_tech"),
    EntityInfo("버크셔해서웨이", "Berkshire Hathaway", "INVESTMENT US", "us_tech"),
    EntityInfo("JP모건", "JPMorgan Chase", "BANK CORP US", "us_tech"),
    EntityInfo("비자", "Visa", "PAYMENT CORP US", "us_tech"),
    EntityInfo("마스터카드", "Mastercard", "PAYMENT CORP US2", "us_tech"),
    EntityInfo("코스트코", "Costco", "RETAIL CORP US", "us_tech"),
    EntityInfo("월마트", "Walmart", "RETAIL CORP US2", "us_tech"),
    EntityInfo("존슨앤드존슨", "Johnson & Johnson", "HEALTHCARE US", "us_tech"),
    EntityInfo("유나이티드헬스", "UnitedHealth Group", "HEALTH INS US", "us_tech"),
    EntityInfo("엑슨모빌", "ExxonMobil", "OIL CORP US", "us_tech"),
    EntityInfo("셰브론", "Chevron", "OIL CORP US2", "us_tech"),
    EntityInfo("샌디스크", "SanDisk", "FLASH STORAGE CO", "us_tech"),
    EntityInfo("TSMC", "TSMC", "FOUNDRY CORP TW", "us_tech"),
    EntityInfo("ARM", "ARM Holdings", "CHIP DESIGN UK", "us_tech"),
    EntityInfo("ASML", "ASML", "LITHO EQUIP NL", "us_tech"),
    EntityInfo("오라클", "Oracle", "SOFTWARE CORP US", "us_tech"),
    EntityInfo("세일즈포스", "Salesforce", "CRM CORP US", "us_tech"),
    EntityInfo("시스코", "Cisco Systems", "NETWORK CORP US", "us_tech"),
    EntityInfo("디즈니", "Walt Disney", "MEDIA CORP US", "us_tech"),
    EntityInfo("보잉", "Boeing", "AERO CORP US", "us_tech"),
    EntityInfo("나이키", "Nike", "SPORTS CORP US", "us_tech"),
    EntityInfo("스타벅스", "Starbucks", "COFFEE CORP US", "us_tech"),
    EntityInfo("코카콜라", "Coca-Cola", "BEVERAGE CORP US", "us_tech"),
    EntityInfo("펩시코", "PepsiCo", "BEVERAGE CORP US2", "us_tech"),
    EntityInfo("화이자", "Pfizer", "PHARMA CORP US2", "us_tech"),
    EntityInfo("모더나", "Moderna", "BIOTECH US", "us_tech"),

    # -----------------------------------------------------------------------
    # D. 지수 및 거래소 (~15개+)
    # -----------------------------------------------------------------------
    EntityInfo("코스피", "KOSPI", "KOSPI INDEX", "index_exchange"),
    EntityInfo("코스닥", "KOSDAQ", "KOSDAQ INDEX", "index_exchange"),
    EntityInfo("나스닥", "NASDAQ", "NASDAQ INDEX", "index_exchange"),
    EntityInfo("나스닥100", "Nasdaq-100", "NASDAQ100 INDEX", "index_exchange"),
    EntityInfo("다우존스", "Dow Jones Industrial Average", "DOW INDEX", "index_exchange"),
    EntityInfo("다우", "DOW", "DOW INDEX", "index_exchange"),
    EntityInfo("S&P500", "S&P 500", "SP500 INDEX", "index_exchange"),
    EntityInfo("필라델피아 반도체지수", "PHLX Semiconductor Sector (SOX)", "SOX INDEX", "index_exchange"),
    EntityInfo("SOX", "SOX Index", "SOX INDEX", "index_exchange"),
    EntityInfo("니케이225", "Nikkei 225", "NIKKEI INDEX", "index_exchange"),
    EntityInfo("상하이종합지수", "Shanghai Composite", "SHANGHAI INDEX", "index_exchange"),
    EntityInfo("항셍지수", "Hang Seng Index", "HANG SENG INDEX", "index_exchange"),
    EntityInfo("유로스톡스50", "EURO STOXX 50", "EUROSTOXX INDEX", "index_exchange"),
    EntityInfo("영국 FTSE100", "FTSE 100", "FTSE INDEX", "index_exchange"),
    EntityInfo("VIX", "VIX Volatility Index", "VIX INDEX", "index_exchange"),

    # -----------------------------------------------------------------------
    # E. 원자재 및 거시 경제지표 (~20개+)
    # -----------------------------------------------------------------------
    EntityInfo("국제유가", "WTI Crude Oil", "CRUDE OIL", "macro_commodity"),
    EntityInfo("WTI", "WTI Crude Oil", "WTI OIL", "macro_commodity"),
    EntityInfo("브렌트유", "Brent Crude Oil", "BRENT OIL", "macro_commodity"),
    EntityInfo("구리", "Copper", "COPPER METAL", "macro_commodity"),
    EntityInfo("금", "Gold", "GOLD METAL", "macro_commodity"),
    EntityInfo("은", "Silver", "SILVER METAL", "macro_commodity"),
    EntityInfo("천연가스", "Natural Gas", "NATURAL GAS", "macro_commodity"),
    EntityInfo("원달러 환율", "USD/KRW Exchange Rate", "USD KRW RATE", "macro_commodity"),
    EntityInfo("원달러", "USD/KRW Rate", "USD KRW RATE", "macro_commodity"),
    EntityInfo("미국 10년물 국채금리", "US 10-Year Treasury Yield", "US10Y YIELD", "macro_commodity"),
    EntityInfo("미국 연준", "US FED", "US FED", "macro_commodity"),
    EntityInfo("연준", "FED", "US FED", "macro_commodity"),
    EntityInfo("한국은행", "Bank of Korea (BOK)", "BOK CENTRAL BANK", "macro_commodity"),
    EntityInfo("소비자물가지수", "Consumer Price Index (CPI)", "CPI METRIC", "macro_commodity"),
    EntityInfo("CPI", "CPI", "CPI METRIC", "macro_commodity"),
    EntityInfo("리튬", "Lithium", "LITHIUM METAL", "macro_commodity"),
    EntityInfo("니켈", "Nickel", "NICKEL METAL", "macro_commodity"),
    EntityInfo("팔라듐", "Palladium", "PALLADIUM METAL", "macro_commodity"),
    EntityInfo("백금", "Platinum", "PLATINUM METAL", "macro_commodity"),
    EntityInfo("철광석", "Iron Ore", "IRON ORE", "macro_commodity"),
    EntityInfo("비트코인", "Bitcoin (BTC)", "CRYPTO BTC", "macro_commodity"),
    EntityInfo("이더리움", "Ethereum (ETH)", "CRYPTO ETH", "macro_commodity"),

    # -----------------------------------------------------------------------
    # F. 핵심 금융/투자 용어 (~30개+)
    # -----------------------------------------------------------------------
    EntityInfo("PER", "PER", "PER RATIO", "financial_terms"),
    EntityInfo("PBR", "PBR", "PBR RATIO", "financial_terms"),
    EntityInfo("ROE", "ROE", "ROE METRIC", "financial_terms"),
    EntityInfo("ROA", "ROA", "ROA METRIC", "financial_terms"),
    EntityInfo("EPS", "EPS", "EPS METRIC", "financial_terms"),
    EntityInfo("EV/EBITDA", "EV/EBITDA", "EV EBITDA RATIO", "financial_terms"),
    EntityInfo("영업이익률", "Operating Margin", "OPERATING MARGIN", "financial_terms"),
    EntityInfo("시가총액", "Market Capitalization", "MARKET CAP", "financial_terms"),
    EntityInfo("배당수익률", "Dividend Yield", "DIVIDEND YIELD", "financial_terms"),
    EntityInfo("자기자본", "Shareholder Equity", "EQUITY METRIC", "financial_terms"),
    EntityInfo("순이익", "Net Profit", "NET PROFIT", "financial_terms"),
    EntityInfo("매출액", "Revenue", "REVENUE METRIC", "financial_terms"),
    EntityInfo("부채비율", "Debt-to-Equity Ratio", "DEBT RATIO", "financial_terms"),
    EntityInfo("유동비율", "Current Ratio", "CURRENT RATIO", "financial_terms"),
    EntityInfo("공매도", "Short Selling", "SHORT SELLING", "financial_terms"),
    EntityInfo("외국인 순매수", "Foreign Net Buying", "FOREIGN BUYING", "financial_terms"),
    EntityInfo("기관 순매도", "Institutional Net Selling", "INSTITUTIONAL SELLING", "financial_terms"),
    EntityInfo("자사주 매입", "Share Buyback", "SHARE BUYBACK", "financial_terms"),
    EntityInfo("영업이익", "Operating Profit", "OPERATING PROFIT", "financial_terms"),
    EntityInfo("당기순이익", "Net Income", "NET INCOME", "financial_terms"),
    EntityInfo("배당금", "Dividend", "DIVIDEND PAYOUT", "financial_terms"),
    EntityInfo("유상증자", "Paid-in Capital Increase", "RIGHTS OFFERING", "financial_terms"),
    EntityInfo("무상증자", "Bonus Issue", "BONUS ISSUE", "financial_terms"),
    EntityInfo("주당순이익", "Earnings Per Share (EPS)", "EPS METRIC", "financial_terms"),
    EntityInfo("주가수익비율", "Price-to-Earnings Ratio (PER)", "PER RATIO", "financial_terms"),
    EntityInfo("주가순자산비율", "Price-to-Book Ratio (PBR)", "PBR RATIO", "financial_terms"),
    EntityInfo("자기자본이익률", "Return on Equity (ROE)", "ROE METRIC", "financial_terms"),
    EntityInfo("자산수익률", "Return on Assets (ROA)", "ROA METRIC", "financial_terms"),
    EntityInfo("영업활동현금흐름", "Operating Cash Flow", "CASH FLOW METRIC", "financial_terms"),

    # -----------------------------------------------------------------------
    # G. 파생/채권/산업 용어 (~20개+)
    # -----------------------------------------------------------------------
    EntityInfo("HBM", "HBM", "HBM MEMORY", "derivatives_industry"),
    EntityInfo("파운드리", "Foundry", "FOUNDRY BIZ", "derivatives_industry"),
    EntityInfo("양극재", "Cathode Material", "CATHODE MAT", "derivatives_industry"),
    EntityInfo("음극재", "Anode Material", "ANODE MAT", "derivatives_industry"),
    EntityInfo("신주인수권", "Warrant", "WARRANT OPTION", "derivatives_industry"),
    EntityInfo("CDS 프리미엄", "CDS Premium", "CDS PREMIUM", "derivatives_industry"),
    EntityInfo("회사채", "Corporate Bond", "CORP BOND", "derivatives_industry"),
    EntityInfo("국채", "Government Bond", "GOV BOND", "derivatives_industry"),
    EntityInfo("ETF", "ETF", "ETF FUND", "derivatives_industry"),
    EntityInfo("공모주", "IPO", "IPO OFFERING", "derivatives_industry"),
    EntityInfo("IPO", "IPO", "IPO OFFERING", "derivatives_industry"),
    EntityInfo("선물", "Futures", "FUTURES CONTRACT", "derivatives_industry"),
    EntityInfo("옵션", "Options", "OPTIONS CONTRACT", "derivatives_industry"),
    EntityInfo("NAND", "NAND Flash", "NAND FLASH", "derivatives_industry"),
    EntityInfo("DRAM", "DRAM Memory", "DRAM MEMORY", "derivatives_industry"),
    EntityInfo("EUV", "EUV Lithography", "EUV TECH", "derivatives_industry"),
    EntityInfo("생성형 AI", "Generative AI", "GEN AI TECH", "derivatives_industry"),
    EntityInfo("자율주행", "Autonomous Driving", "AUTO DRIVING", "derivatives_industry"),
    EntityInfo("전고체 배터리", "Solid-State Battery", "SOLID BATTERY", "derivatives_industry"),
    EntityInfo("신재생에너지", "Renewable Energy", "RENEWABLE ENERGY", "derivatives_industry"),
]


def all_entity_infos() -> tuple[EntityInfo, ...]:
    """프롬프트 경계 검증에서 사용할 불변 엔티티 레지스트리 뷰를 반환한다."""
    return tuple(_RAW_ENTITY_LIST)

# ---------------------------------------------------------------------------
# SSOT 레지스트리 맵 구축 (중복 키 방지)
# ---------------------------------------------------------------------------
ENTITY_REGISTRY: dict[str, EntityInfo] = {info.korean: info for info in _RAW_ENTITY_LIST}

# 하위 호환성 룩업 딕셔너리 (REAL_ENTITY_ENGLISH_MAP & FICTIONALIZED_LABEL_MAP 호환)
REAL_ENTITY_ENGLISH_MAP: dict[str, str] = {
    info.korean: info.english_official for info in _RAW_ENTITY_LIST
}

FICTIONALIZED_LABEL_MAP: dict[str, str] = {
    info.korean: info.fictional_label for info in _RAW_ENTITY_LIST
}

def get_entity_english_name(ent: str, mode: str = "real") -> tuple[str, str]:
    """
    엔티티 명칭을 받아 렌더링할 텍스트와 신뢰도를 반환한다.
    기계적 로마자 변환을 절대 실행하지 않으며 3단계 폴백을 따른다.

    반환: (표기할 텍스트, 신뢰도)
    신뢰도: "verified" | "ascii_passthrough" | "uncertain"
    """
    ent_clean = str(ent or "").strip()
    if ent_clean in ENTITY_REGISTRY:
        info = ENTITY_REGISTRY[ent_clean]
        target = info.fictional_label if mode == "fictional" else info.english_official
        return target, "verified"

    if ent_clean.isascii():
        return ent_clean, "ascii_passthrough"

    # 3순위 (uncertain): 레지스트리에 없고 한글 포함 -> 기계적 로마자 변환 금지, 원문 그대로 반환하고 uncertain 표기
    return ent_clean, "uncertain"

def get_entity_info(ent: str) -> EntityInfo | None:
    """엔티티 상세 정보 반환 (카테고리, 가상 라벨 포함)"""
    return ENTITY_REGISTRY.get(str(ent or "").strip())

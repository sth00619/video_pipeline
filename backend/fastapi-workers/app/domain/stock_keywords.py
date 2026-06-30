"""
주식 카테고리별 키워드 패턴 + 더미 채널 정의.
실제 YouTube에서 자주 등장하는 패턴을 반영.
"""

STOCK_CATEGORIES = {
    "KOSPI": {
        "default_seeds": ["코스피", "코스피 지수", "한국 증시"],
        "title_patterns": [
            "{seed} 다음 주 전망",
            "{seed} 핵심 정리 5분",
            "{seed} 시나리오 3가지",
            "{seed} 외국인 매매 동향",
            "{seed} 기관 vs 외국인 매수세",
            "{seed} 박스권 돌파 가능성",
            "{seed} 차트 분석",
            "{seed} 어디까지 갈까",
            "{seed} 매수 매도 시그널",
        ],
        "common_channels": ["주식의신", "한국주식분석", "코스피라이브", "투자의신호", "재테크TV"],
    },
    "KOSDAQ": {
        "default_seeds": ["코스닥", "코스닥 종목", "테마주", "중소형주"],
        "title_patterns": [
            "{seed} 급등 종목 TOP 5",
            "{seed} 핫이슈 정리",
            "{seed} 다음 주 주목할 종목",
            "{seed} 거래량 폭발 종목",
            "{seed} 신규 상장주 분석",
            "{seed} 단타 종목 정리",
            "{seed} 매집 시그널 포착",
        ],
        "common_channels": ["코스닥분석가", "테마주연구소", "급등주헌터", "단타의신"],
    },
    "US_STOCKS": {
        "default_seeds": ["미국 주식", "S&P 500", "나스닥", "다우 지수"],
        "title_patterns": [
            "{seed} 실적 발표 후 전망",
            "{seed} 매수 타이밍 분석",
            "{seed} 분기 실적 정리",
            "{seed} AI 시대 핵심주",
            "{seed} 매도해야 할 시점",
            "{seed} 미국 시장 마감 분석",
            "{seed} 빅테크 동향",
            "{seed} 어디까지 상승할까",
        ],
        "common_channels": ["월가의신", "미국주식전문가", "글로벌투자자", "나스닥인사이트"],
    },
    "INDIVIDUAL_STOCK": {
        "default_seeds": ["삼성전자", "SK하이닉스", "테슬라", "엔비디아"],
        "title_patterns": [
            "{seed} 매수 매도 시그널",
            "{seed} 목표가 분석",
            "{seed} 4분기 실적 전망",
            "{seed} 차트 패턴 분석",
            "{seed} 신고가 돌파 후 전략",
            "{seed} 배당 분석",
            "{seed} 주가 흐름 진단",
            "{seed} 지금 사도 될까",
        ],
        "common_channels": ["종목분석연구소", "차트분석가", "기업분석왕", "주식고수"],
    },
    "GLOBAL_MACRO": {
        "default_seeds": ["FOMC", "연준 금리", "환율", "원달러", "미국 CPI"],
        "title_patterns": [
            "{seed} 다음 회의 시나리오",
            "{seed} 발표 후 시장 전망",
            "{seed} 인하 시그널 분석",
            "{seed} 영향 받을 종목",
            "{seed} 한국 시장 파급 효과",
            "{seed} 핵심 정리",
            "{seed} 글로벌 시장 영향",
        ],
        "common_channels": ["거시경제연구소", "환율분석가", "글로벌매크로", "금리리포트"],
    },
    "CRYPTO": {
        "default_seeds": ["비트코인", "이더리움", "암호화폐", "알트코인"],
        "title_patterns": [
            "{seed} 다음 목표가 분석",
            "{seed} 차트 분석 라이브",
            "{seed} ETF 승인 후 전망",
            "{seed} 반감기 이후 시나리오",
            "{seed} 매수 타이밍",
            "{seed} 급락 후 반등 가능성",
        ],
        "common_channels": ["코인분석가", "암호화폐연구소", "비트코인투자", "크립토라이브"],
    },
    "CUSTOM": {
        "default_seeds": [],
        "title_patterns": [
            "{seed} 완벽 가이드",
            "{seed} 다음 주 전망",
            "{seed} 핵심 정리",
            "{seed} 매매 전략",
            "{seed} 시나리오 분석",
            "{seed} 어디까지 갈까",
        ],
        "common_channels": ["주식분석", "투자전문가", "재테크"],
    },
}


def get_category_data(category: str) -> dict:
    return STOCK_CATEGORIES.get(category, STOCK_CATEGORIES["CUSTOM"])

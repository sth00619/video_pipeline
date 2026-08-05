"""Simulation script to compare candidate scoring for 20 candidates in UTF-8 markdown format."""

import sys
from app.utils.candidate_scoring import score_candidates

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class MockExtractor:
    def __init__(self, news_by_kw):
        self._news_by_kw = news_by_kw

    def search_recent_news(self, query: str, max_age_hours: int = 72, limit: int = 6):
        return self._news_by_kw.get(query, [])


def run_simulation():
    sample_candidates = [
        {"keyword": "삼성전자 3분기 반도체 실적", "category": "KOSPI", "reason": "HBM3E 공급 및 3분기 실적 전망", "vol_pct": 2.1, "news_24h": 8, "news_7d": 14, "is_global": False},
        {"keyword": "SK하이닉스 HBM4 수주", "category": "KOSPI", "reason": "HBM4 독점 공급 및 영업이익률 40% 달성", "vol_pct": 3.4, "news_24h": 6, "news_7d": 10, "is_global": False},
        {"keyword": "FOMC 금리 결정 인하 기대", "category": "GLOBAL_MACRO", "reason": "연준 기준금리 인하 가능성 및 미국 CPI 지표 안정", "vol_pct": 1.8, "news_24h": 10, "news_7d": 25, "is_global": True},
        {"keyword": "엔비디아 블랙웰 생산 차질 해소", "category": "US_STOCKS", "reason": "미국 빅테크 AI 서버 수요 폭발 및 유가 안정", "vol_pct": 2.8, "news_24h": 7, "news_7d": 15, "is_global": True},
        {"keyword": "현대차 밸류업 주주환원", "category": "KOSPI", "reason": "자사주 소각 및 배당수익률 5% 발표", "vol_pct": 1.1, "news_24h": 1, "news_7d": 2, "is_global": False},
        {"keyword": "카카오 신임 대표 인적쇄신", "category": "KOSPI", "reason": "카카오그룹 계열사 정리 및 구조조정", "vol_pct": 0.5, "news_24h": 0, "news_7d": 10, "is_global": False},
        {"keyword": "네이버 치지직 스트리밍 성장", "category": "KOSPI", "reason": "스트리밍 시장 점유율 40% 달성", "vol_pct": 0.8, "news_24h": 1, "news_7d": 2, "is_global": False},
        {"keyword": "테슬라 로보택시 공개", "category": "US_STOCKS", "reason": "자율주행 FSD 규제 승인 및 환율 변동", "vol_pct": 4.2, "news_24h": 9, "news_7d": 20, "is_global": True},
        {"keyword": "바이오텍 한미약품 신약 임상", "category": "KOSDAQ", "reason": "비만치료제 임상 3상 결과 성공 발표", "vol_pct": 2.9, "news_24h": 5, "news_7d": 8, "is_global": False},
        {"keyword": "알테오젠 키트루다 SC 계약", "category": "KOSDAQ", "reason": "독점 계약 마일스톤 1조원 수령", "vol_pct": 5.1, "news_24h": 6, "news_7d": 12, "is_global": False},
        {"keyword": "한화에어로스페이스 방산 수주", "category": "KOSPI", "reason": "폴란드 K9 자주포 2차 이행계약 체결", "vol_pct": 1.9, "news_24h": 4, "news_7d": 7, "is_global": True},
        {"keyword": "두산에너빌리티 SMR 원전 수출", "category": "KOSPI", "reason": "뉴스케일파워 SMR 제작 계약 체결", "vol_pct": 2.3, "news_24h": 3, "news_7d": 5, "is_global": False},
        {"keyword": "애플 아이폰16 AI 기능 탑재", "category": "US_STOCKS", "reason": "애플 인텔리전스 공개 및 교체 수요", "vol_pct": 1.5, "news_24h": 8, "news_7d": 18, "is_global": True},
        {"keyword": "달러 원 환율 1400원 돌파", "category": "GLOBAL_MACRO", "reason": "달러 강세 및 엔화 약세 심화", "vol_pct": 1.7, "news_24h": 7, "news_7d": 14, "is_global": True},
        {"keyword": "국제유가 WTI 80달러 재상승", "category": "GLOBAL_MACRO", "reason": "중동 지정학 리스크 및 OPEC 감산", "vol_pct": 2.0, "news_24h": 5, "news_7d": 11, "is_global": True},
        {"keyword": "LG에너지솔루션 4680 배터리 양산", "category": "KOSPI", "reason": "오창 공장 4680 원통형 배터리 양산", "vol_pct": 1.3, "news_24h": 2, "news_7d": 6, "is_global": False},
        {"keyword": "포스코홀딩스 리튬 공장 준공", "category": "KOSPI", "reason": "광양 수산화리튬 공장 가동 시작", "vol_pct": 0.9, "news_24h": 1, "news_7d": 1, "is_global": False},
        {"keyword": "셀트리온 짐펜트라 미국 출시", "category": "KOSPI", "reason": "미국 PBM 처방집 등재 확대", "vol_pct": 1.4, "news_24h": 3, "news_7d": 6, "is_global": False},
        {"keyword": "크래프톤 배틀그라운드 매출 호조", "category": "KOSPI", "reason": "인도 법인 BGMI 매출 역대 최대", "vol_pct": 1.6, "news_24h": 2, "news_7d": 4, "is_global": False},
        {"keyword": "금양 이차전지 자금조달 논란", "category": "KOSDAQ", "reason": "유상증자 공시 및 주가 변동성 급증", "vol_pct": 6.8, "news_24h": 4, "news_7d": 9, "is_global": False},
    ]

    news_map = {}
    for c in sample_candidates:
        kw = c["keyword"]
        n_24h = c["news_24h"]
        n_7d = c["news_7d"]
        articles = []
        for i in range(n_24h):
            articles.append({"title": f"{kw} 속보 {i+1}", "source": "한국경제", "hoursSincePublish": 4, "publishedAt": "2026-08-06T00:00:00Z"})
        for i in range(n_7d - n_24h):
            articles.append({"title": f"{kw} 기사 {i+1}", "source": "매일경제", "hoursSincePublish": 48, "publishedAt": "2026-08-04T00:00:00Z"})
        news_map[kw] = articles

    extractor = MockExtractor(news_map)

    print("| No | 후보 키워드 | 카테고리 | 신규 점수 | news(모멘텀) | market(z보정) | cat(글로벌) | 24h건수 / 7d건수 (일평균) | 모멘텀 라벨(비율) | z-score (가점) | 글로벌 보정 | Exception 적용 | auto_confirm |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    protected_count = 0

    for idx, item in enumerate(sample_candidates, 1):
        market_data = {
            "kr": {"index": {"kospi": {"close": 2700, "change_pct": item["vol_pct"]}}},
            "us": {"index": {"sp500": {"close": 5500, "change_pct": item["vol_pct"]}}}
        }
        cand_list = [{"keyword": item["keyword"], "reason": item["reason"]}]
        res = score_candidates(cand_list, [], market_data, item["category"], item["keyword"], extractor=extractor)[0]
        
        ev = res["evidence"]
        mom_dir = ev["momentum_direction"]
        z_score = ev["market_move_magnitude"]
        global_rel = ev["global_macro_relevance"]
        count_7d = ev["news_count"]
        count_24h = item["news_24h"]
        avg_7d = round(count_7d / 7.0, 2)
        
        if mom_dir == "protected_low_volume":
            protected_count += 1
            floor_str = "**YES (보호)**"
        else:
            floor_str = "No"

        # z-score 가점 액수 계산
        z_bonus = 7 if z_score >= 4.0 else (5 if z_score >= 2.0 else (3 if z_score >= 1.0 else 0))
        glob_bonus = 5 if global_rel >= 0.8 else 0

        print(f"| {idx} | {item['keyword']} | {item['category']} | **{res['score']}점** | {res['news_score']} | {res['market_data_score']} | {res['category_score']} | {count_24h}건 / {count_7d}건 ({avg_7d}건/일) | `{mom_dir}` ({ev['momentum_ratio']}x) | {z_score} (+{z_bonus}점) | {global_rel} (+{glob_bonus}점) | {floor_str} | {res['auto_confirm_eligible']} |")

    print(f"\n총 후보: {len(sample_candidates)}건 | protected_low_volume 적용 건수: {protected_count}건")


if __name__ == "__main__":
    run_simulation()

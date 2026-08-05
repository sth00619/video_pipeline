"""Generate 3 content_depth_quality report samples for real scripts."""

import json
from app.utils.script_content_depth_analyzer import assess_script_content_depth


def run_samples():
    sample1_script = "오늘 미국 FOMC에서 연준이 기준금리를 0.25%포인트 인하했습니다. 그 결과 고금리 부담에 눌려있던 빅테크 기술주들이 강력한 상승세를 보였습니다. 이는 시장 유동성 공급과 투자심리 회복으로 이어졌습니다. 하지만 일각에서는 인플레이션 재발 우려도 제기됩니다."
    sample1_sections = [
        {"section_type": "intro", "content": "오늘 미국 FOMC에서 연준이 기준금리를 0.25%포인트 인하했습니다."},
        {"section_type": "background", "content": "그 결과 고금리 부담에 눌려있던 빅테크 기술주들이 강력한 상승세를 보였습니다."},
        {"section_type": "data", "content": "이는 시장 유동성 공급과 투자심리 회복으로 이어졌습니다."},
        {"section_type": "conclusion", "content": "하지만 일각에서는 인플레이션 재발 우려도 제기됩니다."}
    ]
    sample1_facts = [
        {"fact": "연준 기준금리 0.25%p 인하", "figure": "0.25%p", "source_field": "us.macro.fed_rate", "source_ref": ["us.macro.fed_rate", "news_reuters"], "cross_verified": True, "contradiction_detected": False},
        {"fact": "빅테크 주가 상승 및 기술주 랠리", "figure": "나스닥 +1.8%", "source_field": "us.index.nasdaq", "source_ref": ["us.index.nasdaq"], "cross_verified": False, "contradiction_detected": False}
    ]

    sample2_script = "삼성전자가 3분기 반도체 부문에서 영업이익 5조원을 기록했습니다. 이는 HBM3E 공급 지연 때문에 증권가 예상치 6조원보다 낮은 수치입니다. 그 결과 외국인 기관의 순매도가 집중됐습니다. 다만 4분기부터는 레거시 D램 가격 반등이 기대됩니다."
    sample2_sections = [
        {"section_type": "intro", "content": "삼성전자가 3분기 반도체 부문에서 영업이익 5조원을 기록했습니다."},
        {"section_type": "data", "content": "이는 HBM3E 공급 지연 때문에 증권가 예상치 6조원보다 낮은 수치입니다."},
        {"section_type": "background", "content": "그 결과 외국인 기관의 순매도가 집중됐습니다."},
        {"section_type": "action", "content": "다만 4분기부터는 레거시 D램 가격 반등이 기대됩니다."}
    ]
    sample2_facts = [
        {"fact": "삼성전자 3분기 영업이익 5조원", "figure": "5조원", "source_field": "news_hankyung", "source_ref": ["news_hankyung", "news_mk"], "cross_verified": True, "contradiction_detected": False},
        {"fact": "증권가 전망치 수치 차이 논란", "figure": "5.5조 vs 6.2조", "source_field": "news_conflict", "source_ref": ["broker_a", "broker_b"], "cross_verified": False, "contradiction_detected": True}
    ]

    sample3_script = "달러 원 환율이 1400원선에 안착했습니다. 수입 물가 상승으로 인해 한국은행의 금리 인하 여력이 크게 제한되고 있습니다. 그 결과 코스피 지수가 2650선 아래로 하강했습니다."
    sample3_sections = [
        {"section_type": "intro", "content": "달러 원 환율이 1400원선에 안착했습니다."},
        {"section_type": "data", "content": "수입 물가 상승으로 인해 한국은행의 금리 인하 여력이 크게 제한되고 있습니다."},
        {"section_type": "conclusion", "content": "그 결과 코스피 지수가 2650선 아래로 하강했습니다."}
    ]
    sample3_facts = [
        {"fact": "달러 원 환율 1400원", "figure": "1400원", "source_field": "kr.market_indicators.usd_krw", "source_ref": ["kr.market_indicators.usd_krw", "news_bok"], "cross_verified": True, "contradiction_detected": False}
    ]

    rep1 = assess_script_content_depth(sample1_script, sample1_sections, sample1_facts)
    rep2 = assess_script_content_depth(sample2_script, sample2_sections, sample2_facts)
    rep3 = assess_script_content_depth(sample3_script, sample3_sections, sample3_facts)

    print("=== Sample 1: FOMC 금리 인하 대본 ===")
    print(json.dumps(rep1, ensure_ascii=False, indent=2))
    print("\n=== Sample 2: 삼성전자 실적 대본 (상충 발견 케이스) ===")
    print(json.dumps(rep2, ensure_ascii=False, indent=2))
    print("\n=== Sample 3: 환율 1400원 대본 ===")
    print(json.dumps(rep3, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_samples()

"""
대본 문장 유형 분류 엔진 (scene_content_classifier.py) 유닛 테스트
"""
import pytest
from app.utils.scene_content_classifier import classify_narration_content_type

def test_classify_concept_explainer():
    # 1. PER 개념 설명
    s1 = classify_narration_content_type("개념부터 짚고 가겠습니다. PER이란 주가를 주당순이익으로 나눈 값으로, 기업이 고평가인지 저평가인지 가늠하는 지표입니다.")
    assert s1.content_type == "concept_explainer"
    assert "ROE, PER, PBR" in s1.label_text_rule

    # 2. 미학습 ROE 개념 설명
    s2 = classify_narration_content_type("ROE란 자기자본이익률로, 기업이 주주의 돈을 얼마나 효율적으로 활용해 이익을 냈는지 보여주는 핵심 지표입니다.")
    assert s2.content_type == "concept_explainer"

def test_classify_entity_news():
    # 1. 테슬라 실적 발표
    s1 = classify_narration_content_type("테슬라가 예상을 뛰어넘는 실적을 발표하자 주가가 장중 8.4퍼센트 급등했습니다.", core_entities=["Tesla"])
    # 2. 미학습 카카오 AI 신규 요금제 발표
    s2 = classify_narration_content_type("카카오가 하반기 새로운 AI 구독 서비스 요금제 출시 계획을 전격 발표했습니다.", core_entities=["카카오"])
    assert s2.content_type == "entity_news"
    assert "Kakao" in s2.label_text_rule

def test_classify_macro_geopolitical():
    # 1. 중동 유가
    s1 = classify_narration_content_type("중동발 지정학적 리스크로 국제유가가 배럴당 92달러를 돌파하며 국내 정유주가 일제히 강세를 보였습니다.")
    assert s1.content_type == "macro_geopolitical"

    # 2. 미학습 구리 가격 폭등
    s2 = classify_narration_content_type("글로벌 정련소 공급 차질로 구리 가격이 톤당 9,500달러를 돌파하며 최고치를 경신했습니다.")
    assert s2.content_type == "macro_geopolitical"
    assert "Copper" in s2.label_text_rule

def test_classify_comparison():
    # 1. 삼성전자 vs SK하이닉스 상반 실적
    s1 = classify_narration_content_type("삼성전자는 이번 분기 영업이익이 12조 원을 넘겼지만, SK하이닉스는 시장 예상치를 밑돌며 주가가 급락했습니다.", core_entities=["삼성전자", "SK하이닉스"])
    assert s1.content_type == "comparison"

    # 2. 미학습 현대차 vs 기아
    s2 = classify_narration_content_type("현대차는 미국 서부 공장 판매량이 15퍼센트 급증한 반면, 기아는 부품 공급난으로 출고량이 하락했습니다.", core_entities=["현대차", "기아"])
    assert s2.content_type == "comparison"

def test_classify_market_index_move():
    # 1. 코스피 사상 최고치
    s1 = classify_narration_content_type("코스피가 2,847.35포인트로, 4.12퍼센트 급등하며 사상 최고치를 새로 썼습니다.")
    assert s1.content_type in ["market_index_move", "comparison"]

    # 2. 미학습 코스닥 지수 폭락
    s2 = classify_narration_content_type("코스닥 지수가 5퍼센트 폭락하며 시장에 매도세가 쏟아졌습니다.")
    assert s2.content_type == "market_index_move"

"""
200개+ 통합 엔티티 레지스트리 및 3단계 폴백 유닛 테스트 (tests/test_entity_english_map.py)
"""
import pytest
from app.utils.entity_english_map import (
    ENTITY_REGISTRY,
    REAL_ENTITY_ENGLISH_MAP,
    FICTIONALIZED_LABEL_MAP,
    get_entity_english_name,
    get_entity_info,
)

def test_registry_count_and_categories():
    """레지스트리 200개 이상 등재 및 7개 카테고리 분포 검증"""
    total_count = len(ENTITY_REGISTRY)
    assert total_count >= 200, f"Expected 200+ items, got {total_count}"

    categories = {info.category for info in ENTITY_REGISTRY.values()}
    expected_categories = {
        "kospi_large",
        "kosdaq_mid",
        "us_tech",
        "index_exchange",
        "macro_commodity",
        "financial_terms",
        "derivatives_industry",
    }
    assert expected_categories.issubset(categories)

def test_three_tier_fallback():
    """3단계 폴백 동작 검증 (verified, ascii_passthrough, uncertain) 및 기계적 로마자 변환 없음 검증"""
    # 1순위: Verified (레지스트리 등재)
    name, confidence = get_entity_english_name("삼성전자")
    assert confidence == "verified"
    assert name == "Samsung Electronics"

    name_fictional, confidence = get_entity_english_name("삼성전자", mode="fictional")
    assert confidence == "verified"
    assert name_fictional == "SCREEN CORP K"

    # 2순위: ASCII passthrough (이미 영문/숫자)
    name2, confidence2 = get_entity_english_name("NVIDIA")
    assert confidence2 == "ascii_passthrough"
    assert name2 == "NVIDIA"

    # 3순위: Uncertain (미등재 한글 엔티티) -> 로마자 기계 변환 금지, 원문 그대로 반환
    unmapped_korean = "한미반도체"
    name3, confidence3 = get_entity_english_name(unmapped_korean)
    assert confidence3 == "uncertain"
    assert name3 == "한미반도체"  # 로마자 변환(Hanmi Semiconductor 등 기계 합성) 없이 원문 그대로 반환됨

def test_legacy_maps_compatibility():
    """하위 호환성 딕셔너리 호환 검증"""
    assert "SK하이닉스" in REAL_ENTITY_ENGLISH_MAP
    assert REAL_ENTITY_ENGLISH_MAP["SK하이닉스"] == "SK Hynix"

    assert "SK하이닉스" in FICTIONALIZED_LABEL_MAP
    assert FICTIONALIZED_LABEL_MAP["SK하이닉스"] == "SEMI CORP K"

def test_specific_verified_entities():
    """주요 미검증 고도화 엔티티 영문명 100% 정밀도 검증"""
    assert ENTITY_REGISTRY["HD현대중공업"].english_official == "HD Hyundai Heavy Industries"
    assert ENTITY_REGISTRY["두산에너빌리티"].english_official == "Doosan Enerbility"
    assert ENTITY_REGISTRY["삼성물산"].english_official == "Samsung C&T"
    assert ENTITY_REGISTRY["삼성화재"].english_official == "Samsung Fire & Marine Insurance"
    assert ENTITY_REGISTRY["LG생활건강"].english_official == "LG Household & Health Care"
    assert ENTITY_REGISTRY["삼천당제약"].english_official == "Samchundang Pharm"
    assert ENTITY_REGISTRY["엔켐"].english_official == "Enchem"
    assert ENTITY_REGISTRY["리가켐바이오"].english_official == "LigaChem Biosciences"
    assert ENTITY_REGISTRY["클래시스"].english_official == "Classys"

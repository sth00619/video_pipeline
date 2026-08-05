"""Unit tests for script_content_depth_analyzer."""

from app.utils.script_content_depth_analyzer import assess_script_content_depth
from app.workers.script_worker import ScriptWorker


def test_content_depth_analyzer_basic():
    script = "코스피 지수가 2700포인트를 돌파했습니다. 그 결과 외국인 매수세가 크게 늘어났기 때문입니다. 이는 시장 유동성 확대로 이어졌습니다."
    sections = [
        {"section_type": "intro", "content": "코스피 지수가 2700포인트를 돌파했습니다."},
        {"section_type": "data", "content": "그 결과 외국인 매수세가 크게 늘어났기 때문입니다. 이는 시장 유동성 확대로 이어졌습니다."}
    ]
    verified_facts = [
        {"fact": "코스피 지수 2700포인트 돌파", "figure": "2700pt", "source_field": "kr.index.kospi", "source_ref": ["kr.index.kospi", "news_rss"], "cross_verified": True},
        {"fact": "외국인 매수세 증가", "figure": "5000억", "source_field": "kr.supply_demand", "source_ref": ["kr.supply_demand"], "cross_verified": False}
    ]

    report = assess_script_content_depth(script, sections, verified_facts)

    assert "score" in report
    assert report["causal_sentence_count"] >= 1
    assert report["cross_validation"]["verified_facts_total"] == 2
    assert report["cross_validation"]["cross_verified_count"] == 1
    assert report["cross_validation"]["single_source_count"] == 1


def test_cross_validation_cases():
    # Case 1: Multi-source matched (cross_verified=True)
    # Case 2: Single-source (cross_verified=False)
    # Case 3: Contradiction detected (contradiction_detected=True)
    worker = ScriptWorker()
    r3_sample = """```json
[
  {
    "fact": "코스피 2700 돌파",
    "figure": "2700",
    "source_field": "kr.index.kospi",
    "source_ref": ["kr.index.kospi", "news_hankyung"],
    "confidence": 1.0,
    "cross_verified": true,
    "contradiction_detected": false
  },
  {
    "fact": "환율 1350원",
    "figure": "1350원",
    "source_field": "kr.market_indicators",
    "source_ref": ["kr.market_indicators"],
    "confidence": 0.8,
    "cross_verified": false,
    "contradiction_detected": false
  },
  {
    "fact": "삼성전자 3분기 영업이익 수치 상충",
    "figure": "9조 vs 10조",
    "source_field": "news_conflict",
    "source_ref": ["news_hankyung", "news_mk"],
    "confidence": 0.5,
    "cross_verified": false,
    "contradiction_detected": true
  }
]
```"""
    facts = worker._parse_verified_facts(r3_sample)
    assert len(facts) == 3
    assert facts[0]["cross_verified"] is True
    assert facts[1]["cross_verified"] is False
    assert facts[2]["contradiction_detected"] is True

    report = assess_script_content_depth("테스트 대본 내용입니다.", [{"section_type": "data", "content": "테스트"}], facts)
    assert report["cross_validation"]["cross_verified_count"] == 1
    assert report["cross_validation"]["single_source_count"] == 2
    assert len(report["cross_validation"]["contradictions"]) == 1

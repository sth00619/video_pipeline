import json

from app.utils.flow_qa import review_flow
from app.utils.narrative_planner import plan_narrative


FACTS = [
    {"fact": "목표 범위는 3.5%에서 3.75%로 유지됐다.", "figure": "3.5%~3.75%"},
    {"fact": "물가는 2% 목표보다 높다.", "figure": "2%"},
    {"fact": "경제활동은 견조한 속도로 확대되고 있다.", "figure": ""},
]


def test_planner_uses_llm_selected_hook_and_fact_ids():
    def fake_call(_system, _messages, _max_tokens):
        return json.dumps({
            "plan_id": "rate-context",
            "hook_type": "belief_reversal",
            "selection_reason": "동결을 무사건으로 오해하기 쉽다",
            "story_beats": [
                {"role": "오해", "fact_ids": ["F1"], "transition_goal": "통념을 제시"},
                {"role": "근거", "fact_ids": ["F2"], "transition_goal": "오해에 답한다"},
                {"role": "정리", "fact_ids": ["F3"], "transition_goal": "확인 지점을 남긴다"},
            ],
            "checkpoint_fact_ids": ["F1", "F2", "F3"],
            "transition_rules": ["질문 뒤에는 답을 둔다"],
        }, ensure_ascii=False)

    plan = plan_narrative(fake_call, selected_terms=["미국 기준금리"], verified_facts=FACTS,
                          candidate_context={"category": "미국 주식"}, format_name="shorts")

    assert plan["planner"] == "claude"
    assert plan["hook_type"] == "belief_reversal"
    assert plan["story_beats"][1]["fact_ids"] == ["F2"]


def test_flow_qa_surfaces_semantic_review_without_rewriting_facts():
    def fake_call(_system, _messages, _max_tokens):
        return json.dumps({
            "passed": True,
            "question_answer_issues": [],
            "repetition_issues": [],
            "ending_issue": None,
            "transition_issues": [],
            "revision_instruction": "수정 없음",
        }, ensure_ascii=False)

    result = review_flow(fake_call, script=(
        "님들, 금리 목표 범위는 3.5퍼센트에서 3.75퍼센트야. 또 그대로야. "
        "그럼 아무 일도 없는 걸까? 아니야. 물가는 2퍼센트 목표보다 높아. "
        "다음 발표에서 금리와 물가 설명을 함께 보면 돼."
    ), narrative_plan={"plan_id": "test", "story_beats": []})

    assert result["passed"]
    assert result["question_answer_issues"] == []
    assert result["deterministic"]["repetitions"] == []

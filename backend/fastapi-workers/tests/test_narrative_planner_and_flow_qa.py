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
        "여러분, 금리 목표는 그대로입니다. 이번에도 동결됐죠. "
        "그렇다면 아무 일도 없는 걸까요? 꼭 그렇지는 않은 겁니다. "
        "물가는 목표보다 높습니다. 그래서 금리와 물가를 함께 봐야 합니다."
    ), narrative_plan={"plan_id": "test", "story_beats": []})

    assert result["passed"]
    assert result["question_answer_issues"] == []
    assert result["deterministic"]["repetitions"] == []


def test_flow_qa_allows_three_plain_sentences_but_rejects_five():
    def fake_call(_system, _messages, _max_tokens):
        return json.dumps({
            "passed": True,
            "question_answer_issues": [],
            "repetition_issues": [],
            "ending_issue": None,
            "transition_issues": [],
            "rhythm_issues": [],
            "revision_instruction": "문장 역할을 섞으세요.",
        }, ensure_ascii=False)

    three = review_flow(fake_call, script=(
        "금리는 그대로입니다. 경제는 버티고 있습니다. 물가는 아직 높습니다."
    ), narrative_plan={"plan_id": "test", "story_beats": []})

    result = review_flow(fake_call, script=(
        "금리는 그대로입니다. 경제는 버티고 있습니다. 물가는 아직 높습니다. "
        "수요도 이어지고 있습니다. 시장은 이를 반영하고 있습니다."
    ), narrative_plan={"plan_id": "test", "story_beats": []})

    assert three["passed"]
    assert not result["passed"]
    assert result["deterministic"]["rhetorical_rhythm"]["plain_declarative_runs"] == [
        {"role": "description", "sentence_indexes": [1, 2, 3, 4, 5], "length": 5}
    ]


def test_flow_qa_rejects_five_repeated_formal_endings_even_when_sentence_roles_differ():
    def fake_call(_system, _messages, _max_tokens):
        return json.dumps({
            "passed": True,
            "question_answer_issues": [],
            "repetition_issues": [],
            "ending_issue": None,
            "transition_issues": [],
            "rhythm_issues": [],
            "revision_instruction": "종결 리듬을 섞으세요.",
        }, ensure_ascii=False)

    result = review_flow(fake_call, script=(
        "에너지 가격도 영향을 줬습니다. 좋은 신호만 있는 건 아닙니다. "
        "그래서 동결만 보면 안 됩니다. 왜 동결했는지도 봐야 합니다. "
        "조건을 함께 확인해야 합니다."
    ), narrative_plan={"plan_id": "test", "story_beats": []})

    assert not result["passed"]
    assert result["deterministic"]["rhetorical_rhythm"]["formal_ending_runs"] == [
        {"ending": "formal_declarative", "sentence_indexes": [1, 2, 3, 4, 5], "length": 5}
    ]


def test_flow_qa_requires_question_mark_for_spoken_korean_question():
    def fake_call(_system, _messages, _max_tokens):
        return json.dumps({
            "passed": True,
            "question_answer_issues": [],
            "repetition_issues": [],
            "ending_issue": None,
            "transition_issues": [],
            "rhythm_issues": [],
            "revision_instruction": "물음표를 보완하세요.",
        }, ensure_ascii=False)

    result = review_flow(fake_call, script=(
        "이번 발표를 그냥 넘겨도 될까요. 그렇지 않습니다. "
        "금리 옆의 조건까지 같이 봐야 합니다."
    ), narrative_plan={"plan_id": "test", "story_beats": []})

    assert not result["passed"]
    assert result["deterministic"]["spoken_pacing"]["question_punctuation_issues"] == [1]


def test_flow_qa_does_not_treat_explanatory_nikkayo_as_question():
    result = review_flow(
        lambda *args: json.dumps({"passed": True}),
        script="코스피 비금융 상장사 실적의 중심이니까요.",
        narrative_plan={"story_beats": []},
    )

    assert result["deterministic"]["spoken_pacing"]["question_punctuation_issues"] == []


def test_flow_qa_treats_listener_direction_as_emphasis_not_plain_description():
    result = review_flow(
        lambda *args: json.dumps({"passed": True}),
        script=(
            "시장은 이미 다음 장을 기다리고 있습니다. "
            "발표 하나로 끝나는 이야기가 아닌 겁니다. "
            "그날의 시장 반응을 기억하세요."
        ),
        narrative_plan={"story_beats": []},
    )

    rhythm = result["deterministic"]["rhetorical_rhythm"]
    assert rhythm["roles"] == ["description", "description", "emphasis"]
    assert rhythm["plain_declarative_runs"] == []
    assert result["passed"] is True


def test_flow_qa_rejects_sentence_over_generation_hard_cap():
    result = review_flow(
        lambda *args: json.dumps({"passed": True}),
        script=("삼성전자와 SK하이닉스의 반도체 실적과 주주환원 정책이 생산 설비 투자, "
                "수급 변화, 밸류에이션과 향후 주가 판단에 어떤 영향을 주는지 아주 자세히 확인합니다."),
        narrative_plan={"story_beats": []},
    )

    overlong = result["deterministic"]["spoken_pacing"]["overlong_sentences"]
    assert result["passed"] is False
    assert overlong[0]["sentence_index"] == 1
    assert overlong[0]["length"] > 52


def test_flow_qa_rejects_more_than_twenty_spaced_words_even_when_chars_are_short():
    sentence = " ".join(["값"] * 21) + "."
    result = review_flow(
        lambda *args: json.dumps({"passed": True}),
        script=sentence,
        narrative_plan={"story_beats": []},
    )

    issue = result["deterministic"]["spoken_pacing"]["overlong_sentences"][0]
    assert result["passed"] is False
    assert issue["word_count"] == 21


def test_flow_qa_normalizes_false_without_any_failure_reason():
    result = review_flow(
        lambda *args: json.dumps({
            "passed": False,
            "question_answer_issues": [],
            "repetition_issues": [],
            "ending_issue": None,
            "transition_issues": [],
            "rhythm_issues": [],
            "revision_instruction": "",
        }),
        script="PER보다 이익 추정 근거를 먼저 확인해 볼까요? 근거가 판단의 시작인 겁니다.",
        narrative_plan={"story_beats": []},
    )

    assert result["passed"] is True


def test_flow_qa_does_not_pass_a_malformed_empty_response():
    result = review_flow(
        lambda *args: "응답 형식 오류",
        script="PER보다 이익 추정 근거를 먼저 확인해 볼까요? 근거가 판단의 시작인 겁니다.",
        narrative_plan={"story_beats": []},
    )

    assert result["passed"] is False

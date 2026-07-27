"""대본의 문장 연결과 반복을 사실 수정 없이 검사한다."""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Callable

from app.utils.sentence_splitter import split_sentences


def _compact(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value or "")


def _deterministic_checks(script: str) -> dict[str, Any]:
    sentences = split_sentences(re.sub(r"\s+", " ", script or "").strip())
    repeats = []
    for left in range(len(sentences)):
        for right in range(left + 1, min(len(sentences), left + 4)):
            a, b = _compact(sentences[left]), _compact(sentences[right])
            if len(a) >= 12 and len(b) >= 12 and SequenceMatcher(None, a, b).ratio() >= 0.82:
                repeats.append({"sentence_indexes": [left + 1, right + 1], "similarity": round(SequenceMatcher(None, a, b).ratio(), 3)})
    questions = [index + 1 for index, sentence in enumerate(sentences) if "?" in sentence or "왜 " in sentence]
    opening = _compact(" ".join(sentences[:max(1, len(sentences) // 5)]))
    ending = _compact(" ".join(sentences[-max(1, len(sentences) // 5):]))
    overlap = SequenceMatcher(None, opening, ending).ratio() if opening and ending else 0.0
    return {"sentence_count": len(sentences), "repetitions": repeats, "question_indexes": questions, "opening_ending_similarity": round(overlap, 3)}


def review_flow(
    llm_call: Callable[[str, list[dict[str, str]], int], str], *, script: str, narrative_plan: dict[str, Any]
) -> dict[str, Any]:
    """Claude의 의미 판정과 결정론 중복 검사를 합쳐 수정 필요 여부를 반환한다."""
    deterministic = _deterministic_checks(script)
    system = """당신은 한국어 경제 영상 대본의 흐름 QA 편집자입니다.
사실을 추가하거나 고치지 말고, 특정 채널 문체를 모사하지 마세요. JSON 객체만 반환하세요."""
    prompt = f"""내러티브 플랜: {json.dumps(narrative_plan, ensure_ascii=False)}
대본: {script}
결정론 사전검사: {json.dumps(deterministic, ensure_ascii=False)}

다음을 검사하세요: (1) 질문 바로 뒤에 답·근거가 이어지는가, (2) 같은 정보가 새 역할 없이 반복되는가,
(3) 결말이 도입을 새 정보 없이 되풀이하는가, (4) 앞 문장에서 뒷문장으로 넘어갈 때 논리적 단절이 있는가.
{{"passed":true,"question_answer_issues":[],"repetition_issues":[],"ending_issue":null,"transition_issues":[],"revision_instruction":"사실을 바꾸지 않는 한 줄 편집 지시"}}"""
    raw = llm_call(system, [{"role": "user", "content": prompt}], 1200)
    match = re.search(r"\{[\s\S]*\}", raw or "")
    try:
        review = json.loads(match.group(0)) if match else {}
    except ValueError:
        review = {}
    if not isinstance(review, dict):
        review = {}
    llm_passed = bool(review.get("passed"))
    critical_repeat = bool(deterministic["repetitions"])
    result = {
        "passed": llm_passed and not critical_repeat,
        "deterministic": deterministic,
        "question_answer_issues": review.get("question_answer_issues", []),
        "repetition_issues": review.get("repetition_issues", []),
        "ending_issue": review.get("ending_issue"),
        "transition_issues": review.get("transition_issues", []),
        "revision_instruction": str(review.get("revision_instruction", ""))[:500],
        "method": "claude_plus_deterministic",
    }
    return result

"""대본의 문장 연결과 반복을 사실 수정 없이 검사한다."""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Callable

from app.utils.sentence_splitter import split_sentences


# 한국어 한 문장을 영어식 "단어 수"와 글자 수 중 하나로만 자르면 의미가
# 파편화된다. 레퍼런스 호흡에 맞춰 공백 제외 글자 수와 띄어쓰기 단어 수를
# 함께 검사한다. 38단어짜리 문장은 막되, 35~50자의 자연스러운 한국어 한
# 문장은 5~6초 화면에서 읽을 수 있도록 허용한다.
_SPOKEN_SENTENCE_HARD_CAP_CHARS = 52
_SPOKEN_SENTENCE_HARD_CAP_WORDS = 20


def _compact(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value or "")


def _sentence_role(sentence: str) -> str:
    """낭독 리듬을 위한 문장 역할을 보수적으로 분류한다.

    종결어미만 보면 ``입니다``와 ``중요합니다``를 같은 리듬으로 오판한다.
    질문·반전·강조·이유처럼 청자가 실제로 다르게 듣는 기능을 먼저 구분하고,
    나머지만 설명형으로 본다. 사실을 평가하거나 수정하는 용도는 아니다.
    """
    text = re.sub(r"\s+", " ", sentence or "").strip()
    if not text:
        return "empty"
    if "?" in text or re.search(r"(?:일까요|까요|습니까|인가요)[.!…]?$", text):
        return "question"
    if re.search(r"(?:하지만|그런데|다만|반대로|꼭 그렇지는 않|그렇지 않|아닙니다|문제는|여기서)", text):
        return "turn"
    if re.search(
        r"(?:중요한 건|핵심은|봐야 할 건|바로 .*입니다|한 줄만|절대|"
        r"(?:기억|주목|확인|살펴|생각해)\s*.*(?:하세요|보세요)[.!…]?$)",
        text,
    ):
        return "emphasis"
    if re.search(r"(?:때문입니다|이유는|왜냐하면|그래서)", text):
        return "reason"
    # ``~죠``·``~인 겁니다``는 사실을 그대로 전달하는 문장이어도 TTS에서
    # 정형적인 ``~습니다`` 설명문과 분명히 다른 리듬으로 들린다. 종결
    # 다양화가 실제로 설명형 연속 구간도 끊도록 별도 역할로 분류한다.
    if re.search(r"(?:(?:인|은|는) 겁니다|인거예요|죠|고요|해볼까요|볼까요)[.!…]?$", text):
        return "conversational"
    return "description"


def sentence_role(sentence: str) -> str:
    """SCRIPT 리듬 복구 단계와 동일한 문장 역할 판정을 공유한다."""
    return _sentence_role(sentence)


def _ending_register(sentence: str) -> str:
    """존댓말 문장의 종결 리듬을 보수적으로 분류한다.

    사실 전달용 ``~습니다`` 자체는 유지하되, 같은 종결이 연달아 나오면
    TTS에서 안내문처럼 들릴 수 있다. ``~인 겁니다``, ``~겠죠``, ``~고요``처럼
    존댓말을 유지한 준구어체는 별도 리듬으로 취급한다.
    """
    text = re.sub(r"\s+", " ", sentence or "").strip()
    if re.search(r"(?:(?:인|은|는) 겁니다|인거예요|죠|고요|해볼까요|볼까요)[.!…]?$", text):
        return "conversational_honorific"
    if re.search(r"니다[.!…]?$", text):
        return "formal_declarative"
    return "other"


def _rhythm_checks(sentences: list[str]) -> dict[str, Any]:
    """짧은 존댓말 대본이 안내문처럼 들리는 패턴을 찾는다."""
    roles = [_sentence_role(sentence) for sentence in sentences]
    runs: list[dict[str, Any]] = []
    start = 0
    for index, role in enumerate(roles + ["__end__"]):
        if index and role != roles[start]:
            length = index - start
            if roles[start] == "description" and length >= 5:
                runs.append({
                    "role": "description",
                    "sentence_indexes": list(range(start + 1, index + 1)),
                    "length": length,
                })
            start = index
    counts = {role: roles.count(role) for role in ("description", "question", "turn", "emphasis", "reason")}
    ending_registers = [_ending_register(sentence) for sentence in sentences]
    formal_ending_runs: list[dict[str, Any]] = []
    start = 0
    for index, ending in enumerate(ending_registers + ["__end__"]):
        if index and ending != ending_registers[start]:
            length = index - start
            if ending_registers[start] == "formal_declarative" and length >= 5:
                formal_ending_runs.append({
                    "ending": "formal_declarative",
                    "sentence_indexes": list(range(start + 1, index + 1)),
                    "length": length,
                })
            start = index
    return {
        "roles": roles,
        "role_counts": counts,
        "plain_declarative_runs": runs,
        "ending_registers": ending_registers,
        "formal_ending_runs": formal_ending_runs,
        "passed": not runs and not formal_ending_runs,
    }

def _spoken_pacing_checks(sentences: list[str]) -> dict[str, Any]:
    """Keep the script readable in one TTS performance before captions split it."""
    visible_lengths = [len(re.sub(r"\s+", "", sentence)) for sentence in sentences]
    overlong = [
        {
            "sentence_index": index + 1,
            "length": length,
            "word_count": len(sentences[index].split()),
        }
        for index, length in enumerate(visible_lengths)
        if length > _SPOKEN_SENTENCE_HARD_CAP_CHARS
        or len(sentences[index].split()) > _SPOKEN_SENTENCE_HARD_CAP_WORDS
    ]
    short_runs: list[dict[str, Any]] = []
    start: int | None = None
    for index, length in enumerate([*visible_lengths, 99]):
        if length <= 8:
            if start is None:
                start = index
            continue
        if start is not None and index - start >= 3:
            short_runs.append({
                "sentence_indexes": list(range(start + 1, index + 1)),
                "length": index - start,
            })
        start = None

    question_punctuation_issues = [
        index + 1
        for index, sentence in enumerate(sentences)
        # 설명형 ``~니까요.``에는 ``까요`` 글자가 포함되지만 질문이 아니다.
        # 이를 질문부호 누락으로 잡으면 정상적인 이유 문장이 Flow QA를
        # 실패시키므로 ``니까요`` 안의 ``까요``는 제외한다.
        if re.search(r"(?:(?<!니)까요|습니까|나요)\s*\.?$", sentence.strip()) and "?" not in sentence
    ]
    return {
        "visible_lengths": visible_lengths,
        "overlong_sentences": overlong,
        "short_sentence_runs": short_runs,
        "question_punctuation_issues": question_punctuation_issues,
        "passed": not overlong and not short_runs and not question_punctuation_issues,
    }


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
    return {
        "sentence_count": len(sentences),
        "repetitions": repeats,
        "question_indexes": questions,
        "opening_ending_similarity": round(overlap, 3),
        "rhetorical_rhythm": _rhythm_checks(sentences),
        "spoken_pacing": _spoken_pacing_checks(sentences),
    }


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
(3) 결말이 도입을 새 정보 없이 되풀이하는가, (4) 앞 문장에서 뒷문장으로 넘어갈 때 논리적 단절이 있는가,
(5) 설명형 평서문이 세 문장 이상 이어져 안내문처럼 들리지 않는가,
(6) ``~습니다/입니다`` 종결이 세 문장 이상 이어지지 않는가. 후자의 경우 존댓말은 유지하되
``~인 겁니다``, ``~겠죠``, ``~고요``, ``~해볼까요?`` 같은 표현을 필요한 구간에만 제한적으로
섞으세요. 짧은 문장은 유지하되 질문·반전·강조·이유 중 사실에 맞는 역할을 섞어야 합니다.
{{"passed":true,"question_answer_issues":[],"repetition_issues":[],"ending_issue":null,"transition_issues":[],"rhythm_issues":[],"revision_instruction":"사실을 바꾸지 않는 한 줄 편집 지시"}}"""
    raw = llm_call(system, [{"role": "user", "content": prompt}], 1200)
    match = re.search(r"\{[\s\S]*\}", raw or "")
    try:
        review = json.loads(match.group(0)) if match else {}
    except ValueError:
        review = {}
    if not isinstance(review, dict):
        review = {}
    issue_fields = (
        review.get("question_answer_issues"),
        review.get("repetition_issues"),
        review.get("ending_issue"),
        review.get("transition_issues"),
        review.get("rhythm_issues"),
    )
    has_semantic_issue = any(bool(value) for value in issue_fields)
    # Claude가 ``passed:false``를 반환하면서 모든 실패 목록과 수정 지시를
    # 비우는 모순 응답을 낼 수 있다. 명시적 passed 키가 있고 실제 사유가
    # 하나도 없을 때만 이를 통과로 정규화한다. 파싱 실패로 빈 객체가 된
    # 응답은 명시적 키가 없으므로 계속 실패한다.
    llm_passed = bool(review.get("passed")) or (
        "passed" in review and not has_semantic_issue
    )
    critical_repeat = bool(deterministic["repetitions"])
    rhythm_passed = bool(deterministic["rhetorical_rhythm"]["passed"])
    spoken_pacing_passed = bool(deterministic["spoken_pacing"]["passed"])
    result = {
        "passed": llm_passed and not critical_repeat and rhythm_passed and spoken_pacing_passed,
        "deterministic": deterministic,
        "question_answer_issues": review.get("question_answer_issues", []),
        "repetition_issues": review.get("repetition_issues", []),
        "ending_issue": review.get("ending_issue"),
        "transition_issues": review.get("transition_issues", []),
        "rhythm_issues": review.get("rhythm_issues", []),
        "revision_instruction": str(review.get("revision_instruction", ""))[:500],
        "method": "claude_plus_deterministic",
    }
    return result

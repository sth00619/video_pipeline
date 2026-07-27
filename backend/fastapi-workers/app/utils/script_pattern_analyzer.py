"""대본 하우스 스타일의 결정론·LLM 보강 분석기.

금융 사실과 수치는 이 모듈이 생성하거나 수정하지 않는다. LLM은 선택적으로
수사적 역할만 라벨링하며, 기본 분석과 출고 하드 게이트는 결정론적으로 동작한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from app.utils.script_style import HOUSE_STYLE_V1
from app.utils.sentence_splitter import split_sentences


ANALYSIS_CACHE_PATH = Path(os.getenv("SCRIPT_ANALYSIS_CACHE_PATH", "/app/data/analysis_cache"))
NUMBER_RE = re.compile(r"(?<![A-Za-z가-힣])[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|(?<![A-Za-z가-힣])[-+]?\d+(?:\.\d+)?")
ANALOGY_RE = re.compile(r"(?:처럼|같(?:은|아|다|아요|죠)|마치|비유하(?:면|자면)|닮았(?:다|어요))")
QUESTION_RE = re.compile(r"[?？]")
SECOND_PERSON_RE = re.compile(r"(?:님들|우리|너(?:희|의|는|가|를|도)?|내 돈|우리 계좌)")
DIRECT_ADDRESS_RE = re.compile(r"(?:님들|여러분|너(?:희|의|는|가|를|도)?)")
NOVICE_QUESTION_RE = re.compile(r"(?:왜|뭐가|어떻게|그럼|처음 보면|헷갈리|궁금).{0,40}[?？]")
ROADMAP_RE = re.compile(r"(?:오늘|이번 영상).{0,24}(?:딱\s*)?(?:한|두|세|네|다섯|\d+)\s*가지")
CHECKPOINT_RE = re.compile(r"(?:체크\s*포인트|확인해야\s*할|봐야\s*할).{0,24}(?:한|두|세|네|다섯|\d+)\s*가지")
FEAR_REFRAME_RE = re.compile(r"(?:공포|불안|패닉|겁나|무섭).{0,90}(?:하지만|그런데|사실|반대로|기회|조건)")
CONNECTIVES = ("그런데", "하지만", "반대로", "다만", "그래서", "문제는", "즉", "결국")
ABSTRACT_TERMS = ("밸류에이션", "유동성", "변동성", "기대치", "수급", "인플레이션", "금리", "리스크", "심리", "성장률", "실적")


@dataclass(frozen=True)
class ScriptProfile:
    """8축 분석 결과. dict 호환 접근도 제공해 기존 JSON 소비자가 쉽게 쓸 수 있다."""

    axis1_structure: dict[str, Any]
    axis2_retention: dict[str, Any]
    axis3_rhythm: dict[str, Any]
    axis4_register: dict[str, Any]
    axis5_analogy: dict[str, Any]
    axis6_hook: dict[str, Any]
    axis7_safety: dict[str, Any]
    axis8_fact: dict[str, Any]
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis1_structure": self.axis1_structure,
            "axis2_retention": self.axis2_retention,
            "axis3_rhythm": self.axis3_rhythm,
            "axis4_register": self.axis4_register,
            "axis5_analogy": self.axis5_analogy,
            "axis6_hook": self.axis6_hook,
            "axis7_safety": self.axis7_safety,
            "axis8_fact": self.axis8_fact,
            "meta": self.meta,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


def _canonical_number(value: str) -> str:
    return value.replace(",", "").lstrip("+")


def _numbers(text: str) -> list[str]:
    return [_canonical_number(match.group(0)) for match in NUMBER_RE.finditer(text or "")]


def _verified_number_set(verified_facts: list[dict[str, Any]] | None) -> set[str]:
    values: set[str] = set()
    for fact in verified_facts or []:
        if not isinstance(fact, dict):
            continue
        for value in fact.values():
            values.update(_numbers(str(value)))
    return values


def _ends_with_banmal(sentence: str) -> bool:
    return bool(re.search(
        r"(?:했어|였어|있어|없어|거야|같아|달라져|가지야|잖아|거든|겠지|"
        r"했지|하지|보자|봐|돼|해|까|지|야|아|어|죠)[.!?…]?$",
        sentence.strip(),
    ))


def _ending(sentence: str) -> str:
    match = re.search(
        r"(습니다|세요|해요|어요|아요|네요|거든|거야|같아|했어|였어|있어|없어|"
        r"보자|빼자|봐|돼|까|죠|다|지|야|아|어|해)[.!?…]?$",
        sentence.strip(),
    )
    return match.group(1) if match else "기타"


def _ngram_similarity(text: str, references: list[str], n: int = 5) -> float:
    normalized = re.sub(r"\s+", "", text or "")
    grams = {normalized[index:index + n] for index in range(max(0, len(normalized) - n + 1))}
    if not grams:
        return 0.0
    best = 0.0
    for reference in references:
        source = re.sub(r"\s+", "", reference or "")
        reference_grams = {source[index:index + n] for index in range(max(0, len(source) - n + 1))}
        if reference_grams:
            best = max(best, len(grams & reference_grams) / len(grams))
    return round(best, 4)


def _cache_path(script_hash: str) -> Path:
    return ANALYSIS_CACHE_PATH / f"{script_hash}.json"


def _load_cached_labels(script_hash: str) -> dict[str, Any] | None:
    try:
        value = json.loads(_cache_path(script_hash).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _store_cached_labels(script_hash: str, labels: dict[str, Any]) -> None:
    try:
        ANALYSIS_CACHE_PATH.mkdir(parents=True, exist_ok=True)
        _cache_path(script_hash).write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    except OSError:
        # 분석 캐시는 성능 최적화일 뿐, 대본 품질 판정을 실패시키지 않는다.
        return


def _claude_labeler(text: str, format_name: str) -> dict[str, Any]:
    """Claude 고정 모델로 수사 장치만 라벨링한다. 금융 사실을 생성하지 않는다."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {}
    from anthropic import Anthropic
    from app.config import CLAUDE_MODEL

    system = """당신은 한국 금융 대본의 수사 장치 라벨러입니다.
금융 사실·숫자·예측을 추가하거나 수정하지 마세요. 특정 창작자 문체를 모사하지 마세요.
반드시 JSON만 반환하세요: fake_reader_q_count, analogy_concepts, concepts_with_analogy,
fear_reframe_count, hook_type. analogy_concepts는 추상 개념 문자열 배열입니다."""
    response = Anthropic(api_key=api_key).messages.create(
        model=CLAUDE_MODEL,
        max_tokens=700,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": f"형식: {format_name}\n대본:\n{text}"}],
    )
    raw = "".join(block.text for block in response.content if hasattr(block, "text")).strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _resolve_llm_labels(text: str, format_name: str, meta: dict[str, Any], script_hash: str) -> tuple[dict[str, Any], str]:
    provided = meta.get("llm_labels")
    if isinstance(provided, dict):
        return provided, "llm"
    cached = _load_cached_labels(script_hash)
    if cached is not None:
        return cached, "llm_cache"
    labeler = meta.get("llm_labeler")
    enabled = bool(meta.get("llm_labeling_enabled"))
    if not enabled and not callable(labeler):
        return {}, "deterministic"
    try:
        labels = labeler(text, format_name) if callable(labeler) else _claude_labeler(text, format_name)
        labels = labels if isinstance(labels, dict) else {}
        _store_cached_labels(script_hash, labels)
        return labels, "llm"
    except Exception:
        # LLM 라벨 실패는 결정론 안전 게이트의 통과/실패에 영향을 주지 않는다.
        return {}, "deterministic"


def analyze_script(text: str, meta: dict[str, Any] | None = None) -> ScriptProfile:
    """임의 대본을 8축으로 분석한다.

    ``meta``는 format, verified_facts, kind, reference_texts, llm_labeling_enabled를 받는다.
    결정론 지표는 항상 계산하고, LLM 결과는 선택적 어드바이저리 보강으로만 사용한다.
    """
    meta = dict(meta or {})
    format_name = str(meta.get("format") or "longform").lower()
    if format_name not in {"shorts", "longform"}:
        format_name = "longform"
    normalized = re.sub(r"\s+", " ", text or "").strip()
    sentences = split_sentences(normalized)
    char_count = max(1, len(re.sub(r"\s+", "", normalized)))
    script_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    labels, label_method = _resolve_llm_labels(normalized, format_name, meta, script_hash)

    first_window = normalized[:60]
    number_present = bool(_numbers(first_window))
    question_present = bool(QUESTION_RE.search(first_window))
    contrast_present = bool(re.search(r"(?:근데|하지만|반대로|왜)", first_window))
    direct_address_present = bool(DIRECT_ADDRESS_RE.search(first_window))
    opening_sentences = sentences[:3]
    opening_number_count = sum(len(_numbers(sentence)) for sentence in opening_sentences)
    number_shock_present = bool(re.match(r"^\s*[-+]?\d", first_window))
    hook_type = "number_shock" if number_shock_present else ("number_first" if number_present else ("question" if question_present else ("contrast" if contrast_present else "none")))
    if isinstance(labels.get("hook_type"), str) and labels["hook_type"] in HOUSE_STYLE_V1["hook_types"]:
        hook_type = labels["hook_type"]

    fake_reader_q = sum(bool(NOVICE_QUESTION_RE.search(sentence)) for sentence in sentences)
    analogy_sentences = [sentence for sentence in sentences if ANALOGY_RE.search(sentence)]
    abstract_sentences = [sentence for sentence in sentences if any(term in sentence for term in ABSTRACT_TERMS)]
    # 명시적 추상 명사가 없어도 "A는 B와 같다" 구조는 하나의 설명 대상과
    # 비유를 함께 담는다. 이를 0으로 두면 정상적인 짧은 비유 대본이
    # 커버리지 0으로 잘못 판정된다.
    deterministic_concepts = len(abstract_sentences) or len(analogy_sentences)
    deterministic_covered = sum(bool(ANALOGY_RE.search(sentence)) for sentence in abstract_sentences)
    if not abstract_sentences:
        deterministic_covered = len(analogy_sentences)
    concept_count = len(labels["analogy_concepts"]) if isinstance(labels.get("analogy_concepts"), list) else deterministic_concepts
    concepts_with_analogy = int(labels.get("concepts_with_analogy", deterministic_covered) or 0)
    fear_count = len(FEAR_REFRAME_RE.findall(normalized))
    if isinstance(labels.get("fake_reader_q_count"), (int, float)):
        fake_reader_q = max(fake_reader_q, int(labels["fake_reader_q_count"]))
    if isinstance(labels.get("fear_reframe_count"), (int, float)):
        fear_count = max(fear_count, int(labels["fear_reframe_count"]))

    enders = [_ending(sentence) for sentence in sentences]
    max_same_ender_run = 0
    run = 0
    previous = None
    for ender in enders:
        run = run + 1 if ender == previous else 1
        previous = ender
        max_same_ender_run = max(max_same_ender_run, run)
    connective_hits = [word for word in CONNECTIVES if word in normalized]
    lengths = [len(re.sub(r"\s+", "", sentence)) for sentence in sentences]
    sorted_lengths = sorted(lengths)
    p90 = sorted_lengths[max(0, int(len(sorted_lengths) * .9) - 1)] if sorted_lengths else 0
    banmal_sentences = sum(_ends_with_banmal(sentence) for sentence in sentences)
    second_person_count = len(SECOND_PERSON_RE.findall(normalized))
    stake_count = sum(normalized.count(term) for term in HOUSE_STYLE_V1["register"]["stake_framing"])
    numbers = _numbers(normalized)
    verified = _verified_number_set(meta.get("verified_facts"))
    untraceable = [value for value in numbers if value not in verified]
    banned = HOUSE_STYLE_V1["banned"]
    buy_sell_count = sum(normalized.count(value) for value in banned["buy_sell_verbs"])
    hype_count = sum(normalized.count(value) for value in banned["hype"])
    signature_count = sum(normalized.count(value) for value in banned["signature_phrases"] if value)
    similarity = _ngram_similarity(normalized, list(meta.get("reference_texts") or []))

    devices = {
        "D1": bool(number_present and (question_present or contrast_present)),
        "D2": bool(ROADMAP_RE.search(normalized[: max(120, char_count // 5)])),
        "D3": fake_reader_q > 0,
        "D4": bool(analogy_sentences),
        "D5": fear_count > 0,
        "D6": bool(CHECKPOINT_RE.search(normalized)),
        "D7": bool(re.search(r"(?:시나리오|경우의 수|확률).{0,80}(?:가능성|판단|조건)", normalized)),
        "D8": second_person_count > 0 and stake_count > 0,
        "twist": bool(re.search(r"(?:하지만|반대로|그런데|다만)", normalized)),
        "ending_nondirective": not bool(re.search(r"(?:매수|매도|사라|팔아라|담아라|보유)\s*[.!?…]?$", normalized)),
    }
    required = HOUSE_STYLE_V1["required_devices"][format_name]
    order_ok = devices["D1"] and (format_name == "shorts" or devices["D2"])
    coverage = round(concepts_with_analogy / concept_count, 4) if concept_count else (1.0 if analogy_sentences else 0.0)

    return ScriptProfile(
        axis1_structure={"devices_present": devices, "required": required, "order_ok": order_ok, "method": "deterministic"},
        axis2_retention={
            "fake_reader_q_count": fake_reader_q,
            "analogy_count": len(analogy_sentences),
            "fear_reframe_count": fear_count,
            "checkpoint_count": len(CHECKPOINT_RE.findall(normalized)),
            "per_1k_chars": {
                "fake_reader_q": round(fake_reader_q * 1000 / char_count, 3),
                "analogy": round(len(analogy_sentences) * 1000 / char_count, 3),
            },
            "method": label_method if label_method != "deterministic" else "deterministic",
        },
        axis3_rhythm={
            "sent_len_mean": round(mean(lengths), 2) if lengths else 0.0,
            "sent_len_p90": p90,
            "short_emphasis_ratio": round(sum(length <= 18 for length in lengths) / len(lengths), 4) if lengths else 0.0,
            "ender_variety": round(len(set(enders)) / len(enders), 4) if enders else 0.0,
            "connective_variety": round(len(connective_hits) / len(CONNECTIVES), 4),
            "max_same_ender_run": max_same_ender_run,
            "method": "deterministic",
        },
        axis4_register={
            "banmal_ratio": round(banmal_sentences / len(sentences), 4) if sentences else 0.0,
            "second_person_per_1k": round(second_person_count * 1000 / char_count, 3),
            "stake_framing_count": stake_count,
            "method": "deterministic",
        },
        axis5_analogy={
            "concept_count": concept_count,
            "concepts_with_analogy": concepts_with_analogy,
            "coverage": coverage,
            "method": label_method if label_method != "deterministic" else "deterministic",
        },
        axis6_hook={
            "type": hook_type,
            "has_number": number_present,
            "has_question": question_present,
            "has_direct_address": direct_address_present,
            "number_shock_present": number_shock_present,
            "opening_three_sentence_number_count": opening_number_count,
            "number_density_per_100_chars": round(len(numbers) * 100 / char_count, 4),
            "first3s_char_window": first_window,
            "method": label_method if label_method != "deterministic" else "deterministic",
        },
        axis7_safety={"buy_sell_directive_count": buy_sell_count, "banned_phrase_count": signature_count, "hype_count": hype_count, "reference_ngram_similarity": similarity, "method": "deterministic"},
        axis8_fact={"numbers_total": len(numbers), "numbers_traceable": len(numbers) - len(untraceable), "untraceable": untraceable, "method": "deterministic"},
        meta={"format": format_name, "kind": meta.get("kind", "generated"), "script_sha256": script_hash, "char_count": char_count},
    )

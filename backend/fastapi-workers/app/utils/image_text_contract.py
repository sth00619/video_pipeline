"""승인된 장면 문자열만 이미지 생성 경계로 전달하는 계약.

문자가 있다는 사실을 실패로 취급하지 않는다. 실패는 현재 장면의 승인 대사와
``screen_texts``에 없는 문구를 추가하거나, 승인 문자열을 훼손하는 것이다.
다만 지수값·등락률 같은 금융 수치는 저장소 전역 규칙에 따라 이미지 모델에
쓰게 하지 않고 결정론 렌더러로 보낸다.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


_QUOTED_TEXT_RE = re.compile(r"(?P<quote>['\"])(?P<value>[^'\"\n]{1,100})(?P=quote)")
_DISPLAY_VALUE_RE = re.compile(
    r"\b(?:display|screen|monitor|board|banner|sign|placard|speech\s+bubble)\b"
    r"[^.;\n]{0,80}\b(?:show(?:ing|s)?|contain(?:ing|s)?|with)\b"
    r"[^.;\n]{0,80}(?:\d|(?-i:[A-Z]{2,})|[가-힣])",
    re.IGNORECASE,
)
_EXACT_VALUE_RE = re.compile(
    r"\b(?:showing|rendering|displaying)\s+(?:exactly\s+)?"
    r"(?:[+-]?\d[\d.,]*\s*(?:%|x|×|배|pt|포인트)?|(?-i:[A-Z][A-Z0-9 .&/-]{1,40}))",
    re.IGNORECASE,
)
_NEGATIVE_CONTEXT_RE = re.compile(
    r"\b(?:no|without|avoid|zero|never|not)\b[^.;\n]{0,35}$",
    re.IGNORECASE,
)
_NUMERIC_FACT_RE = re.compile(
    r"(?<![A-Za-z가-힣])(?:[+-]?\d[\d,.]*(?:\.\d+)?)\s*"
    r"(?:%|퍼센트|포인트|pt|배|x|×|조|억|만|원|달러|년|월|일)?",
    re.IGNORECASE,
)

_BLANK_SURFACE = "an unlettered scene-integrated visual surface with non-linguistic shapes"
_UNQUOTED_TEXT_CLAUSE_RE = re.compile(
    r"\b(?:label(?:ed|led)?|reading|saying|titled|captioned|stamped|printed)\s+"
    r"(?!with\s+an?\s+(?:blank\s+)?unlettered\b)"
    r"(?!an?\s+(?:blank\s+)?unlettered\b)[^,.;\n]{1,100}",
    re.IGNORECASE,
)


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\s'\"`.,:;!?()\[\]{}<>_\-/\\]+", "", normalized)


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value or "").strip()
        key = _compact(candidate)
        if candidate and key and key not in seen:
            result.append(candidate)
            seen.add(key)
    return result


def contains_financial_number(value: str) -> bool:
    """금융 정보로 오인될 수 있는 숫자 표기가 있는지 판정한다."""
    return bool(_NUMERIC_FACT_RE.search(str(value or "")))


def build_scene_text_contract(scene: dict[str, Any] | None) -> dict[str, Any]:
    """장면 메타데이터에서 생성 가능 문자와 결정론 문자를 분리한다.

    전역 ``verified_facts``는 다른 장면의 사실까지 포함할 수 있으므로 허용 목록
    원천으로 사용하지 않는다. 화면에 필요한 문구는 장면 단위 ``screen_texts``가
    반드시 명시해야 한다.
    """
    source = scene or {}
    validation = source.get("screen_text_validation") or {}
    raw_plan = source.get("screen_text_plan") or []
    plan = [dict(item) for item in raw_plan if isinstance(item, dict) and str(item.get("text") or "").strip()]
    approved = _dedupe([
        *(source.get("screen_texts") or []),
        *(str(item.get("text") or "") for item in plan),
    ])
    if validation and validation.get("passed") is False:
        approved = []

    generated = [value for value in approved if not contains_financial_number(value)]
    deterministic = [value for value in approved if contains_financial_number(value)]
    semantic_routing = []
    if source.get("text_render_policy") == "semantic_roles_v1":
        # 버전 명시 장면만 새 의미 계약을 사용한다. 기존 승인 장면을 소급 변환하지 않는다.
        if validation.get("passed") is not True:
            raise ValueError("의미형 문자 계약에는 장면 문구 승인이 필요합니다.")
        if not isinstance(raw_plan, list) or len(raw_plan) != len(plan):
            raise ValueError("표면 계획은 비어 있지 않은 문구 객체 목록이어야 합니다.")
        if not isinstance(source.get("screen_texts", []), list):
            raise ValueError("승인 문구는 목록이어야 합니다.")
        approved = list(dict.fromkeys(str(v).strip() for v in (source.get("screen_texts") or []) if str(v).strip()))
        for item in plan:
            if item["text"].strip() not in approved:
                raise ValueError("표면 계획의 문구가 장면 승인 목록에 없습니다.")
            if item.get("purpose", "information") not in {"information", "decorative"}:
                raise ValueError("문구 성격은 information/decorative만 허용합니다.")
        generated = []
        deterministic = approved.copy()
        for value in approved:
            uses = [item for item in plan if item["text"].strip() == value]
            decorative = bool(uses) and all(item.get("purpose") == "decorative" for item in uses) and not re.search(r"\d", value)
            semantic_routing.append({
                "text": value, "purpose": "decorative" if decorative else "information",
                "route": "deterministic",
                "reason": "decoration_size_calibration_pending" if decorative else "informational_text_exact",
                "measured_min_character_height_ratio": None,
            })
    bubble_text = str(source.get("bubble_text") or "").strip()
    bubble_validation = source.get("bubble_validation") or {}
    bubble_allowed = bool(
        source.get("allow_speech_bubble")
        and bubble_text
        and bubble_validation.get("passed") is True
    )
    bubble_policy = str(source.get("bubble_policy") or "").strip().lower()
    if bubble_policy not in {"allowed", "required", "forbidden"}:
        bubble_policy = "allowed" if bubble_allowed else "unplanned"
    explicit_holographic_surface = any(
        str(item.get("surface_style") or item.get("material") or "").strip().lower()
        in {"holographic", "transparent_hologram", "translucent_hologram"}
        for item in plan
    )
    surface_material_policy = (
        "explicit_scene_plan_allows_holographic"
        if explicit_holographic_surface else
        "integrated_opaque_scene_surface"
    )
    return {
        "version": "scene-local-text-contract-v5-approved-scene-surface",
        "approved_texts": approved,
        "generated_texts": generated,
        "deterministic_texts": deterministic,
        "surface_plan": plan,
        "surface_count": len({str(item.get("surface") or item.get("role") or index) for index, item in enumerate(plan)}),
        "placement_mode": "explicit_plan" if plan else "contextual_supporting",
        "hierarchy_policy": (
            "follow_explicit_scene_plan"
            if plan else
            "script_objects_and_action_above_supporting_text"
        ),
        "surface_material_policy": surface_material_policy,
        "detached_translucent_card_allowed": explicit_holographic_surface,
        "bubble_policy": bubble_policy,
        "bubble_allowed": bubble_allowed,
        "bubble_text": bubble_text if bubble_allowed else "",
        "sources": ["scene.screen_texts", "scene.screen_text_plan"],
        "text_render_policy": source.get("text_render_policy", "legacy"),
        "semantic_routing": semantic_routing,
    }


def _is_text_payload(value: str) -> bool:
    candidate = str(value or "").strip()
    return bool(candidate and re.search(r"[가-힣]|\d|[A-Z]{2,}", candidate))


def _is_allowed_payload(value: str, allowed_texts: Iterable[str]) -> bool:
    value_key = _compact(value)
    return bool(value_key and any(value_key == _compact(allowed) for allowed in allowed_texts))


def prompt_text_contract_violations(
    prompt: str,
    allowed_texts: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """허용 목록 밖의 긍정형 문자 생성 지시를 위치와 함께 반환한다."""
    source = str(prompt or "")
    allowed = _dedupe(allowed_texts or [])
    violations: list[dict[str, Any]] = []

    for match in _QUOTED_TEXT_RE.finditer(source):
        payload = match.group("value")
        if _is_text_payload(payload) and not _is_allowed_payload(payload, allowed):
            violations.append({
                "kind": "unapproved_quoted_text",
                "text": match.group(0),
                "value": payload,
                "start": match.start(),
            })

    for regex, kind in (
        (_DISPLAY_VALUE_RE, "unapproved_display_instruction"),
        (_EXACT_VALUE_RE, "unapproved_exact_value"),
    ):
        for match in regex.finditer(source):
            prefix = source[max(0, match.start() - 45):match.start()]
            if _NEGATIVE_CONTEXT_RE.search(prefix):
                continue
            if any(_compact(value) in _compact(match.group(0)) for value in allowed):
                continue
            violations.append({"kind": kind, "text": match.group(0), "start": match.start()})

    violations.sort(key=lambda item: (int(item["start"]), str(item["kind"])))
    return violations


def _replace_display_value_instruction(match: re.Match[str]) -> str:
    value = match.group(0)
    verb = re.search(r"\b(?:show(?:ing|s)?|contain(?:ing|s)?|with)\b", value, re.IGNORECASE)
    prefix = value[:verb.start()].rstrip() if verb else value.split(maxsplit=1)[0]
    return f"{prefix} containing {_BLANK_SURFACE}"


def sanitize_generated_text_prompt(
    prompt: str,
    *,
    allowed_texts: Iterable[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """장면은 보존하고 허용 목록 밖의 문자 지시만 중립 표면으로 바꾼다."""
    source = str(prompt or "").strip()
    allowed = _dedupe(allowed_texts or [])
    before = prompt_text_contract_violations(source, allowed)

    def replace_quoted(match: re.Match[str]) -> str:
        payload = match.group("value")
        if _is_text_payload(payload) and not _is_allowed_payload(payload, allowed):
            return _BLANK_SURFACE
        return match.group(0)

    cleaned = _QUOTED_TEXT_RE.sub(replace_quoted, source)
    # 따옴표 문자열 뒤에 붙었던 의미 없는 글자 장식 표현까지 중립 표면에
    # 달라붙으면 ``typographylow`` 같은 새 의사 문구가 생긴다. 문자열을
    # 제거한 경우에만 그 장식 꼬리를 함께 정리한다.
    cleaned = re.sub(
        rf"{re.escape(_BLANK_SURFACE)}\s+(?:expectation|warning|headline|caption|label)\s+"
        r"(?:glow|text|sign|lettering)?",
        _BLANK_SURFACE,
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        rf"\b(?:label(?:ed|led)?|reading|saying|titled|captioned|"
        rf"stamped|printed|write|written|spelled)\b\s*(?:as|with|:)?\s*"
        rf"(?={re.escape(_BLANK_SURFACE)})",
        "with ",
        cleaned,
        flags=re.IGNORECASE,
    )

    def replace_unquoted(match: re.Match[str]) -> str:
        if any(_compact(value) in _compact(match.group(0)) for value in allowed):
            return match.group(0)
        return f"with {_BLANK_SURFACE}"

    cleaned = _UNQUOTED_TEXT_CLAUSE_RE.sub(replace_unquoted, cleaned)

    def replace_exact(match: re.Match[str]) -> str:
        if any(_compact(value) in _compact(match.group(0)) for value in allowed):
            return match.group(0)
        return _BLANK_SURFACE

    cleaned = _EXACT_VALUE_RE.sub(replace_exact, cleaned)

    def replace_display(match: re.Match[str]) -> str:
        if any(_compact(value) in _compact(match.group(0)) for value in allowed):
            return match.group(0)
        return _replace_display_value_instruction(match)

    cleaned = _DISPLAY_VALUE_RE.sub(replace_display, cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    after = prompt_text_contract_violations(cleaned, allowed)
    return cleaned, {
        "version": "scene-local-text-contract-v5-approved-scene-surface",
        "changed": cleaned != source,
        "allowed_generated_texts": allowed,
        "violations_before": before,
        "violations_after": after,
    }


def require_sanitized_generated_text_prompt(
    prompt: str,
    *,
    allowed_texts: Iterable[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """이미지 API 경계에서 비승인 문자 지시가 남으면 즉시 중단한다."""
    cleaned, report = sanitize_generated_text_prompt(prompt, allowed_texts=allowed_texts)
    if report["violations_after"]:
        summary = ", ".join(
            f"{item['kind']}:{item['text']}" for item in report["violations_after"][:6]
        )
        raise ValueError(f"이미지 프롬프트 문자 생성 계약 위반이 남아 있습니다: {summary}")
    return cleaned, report


def visible_text_contract_result(
    visible_tokens: Iterable[str],
    scene: dict[str, Any] | None,
) -> dict[str, Any]:
    """OCR 토큰을 장면 허용 문자열과 비교하는 빠른 1차 게이트."""
    contract = build_scene_text_contract(scene)
    approved = list(contract["approved_texts"])
    approved_compact = [_compact(value) for value in approved]
    source = scene or {}
    narration = str(
        source.get("text_for_tts")
        or source.get("content")
        or source.get("text")
        or source.get("narration")
        or ""
    )
    narration_compact = _compact(narration)
    generated_ocr_policy = source.get("generated_text_ocr_policy") or {}
    reject_unapproved = bool(
        isinstance(generated_ocr_policy, dict)
        and generated_ocr_policy.get("reject_unapproved") is True
    )
    raw_detected = [str(value or "").strip() for value in visible_tokens if str(value or "").strip()]
    detected = _dedupe(raw_detected)
    unexpected = []
    narration_grounded: list[str] = []
    review_required_nonnumeric: list[str] = []
    review_required_numeric: list[str] = []
    for token in detected:
        token_key = _compact(token)
        if not token_key:
            continue
        if (
            any(token_key == value for value in approved_compact)
            if reject_unapproved
            else any(token_key in value or value in token_key for value in approved_compact)
        ):
            continue
        # 사용자가 승인한 장면 내레이션에 실제로 있는 비수치 용어는 생성 모델이
        # 그대로 써도 된다. 번역·파생어·일련번호까지 느슨하게 허용하지 않도록
        # NFKC 정규화 후 완전한 부분 문자열일 때만 통과시킨다. 금융 수치는 계속
        # screen_texts/결정론 렌더러 계약만 허용한다.
        if (
            not reject_unapproved
            and
            not contains_financial_number(token)
            and len(token_key) >= 2
            and token_key in narration_compact
        ):
            narration_grounded.append(token)
            continue
        # OCR만으로는 PRESS·OUTLOOK 같은 정상적인 장면 역할 표기와 오탈자·
        # 이탈자를 구분할 수 없다. 숫자는 승인 사실과 정확히 맞아야 하므로
        # 여기서 차단하고, 비수치 문구는 멀티모달 의미·철자 검수로 넘긴다.
        if contains_financial_number(token):
            review_required_numeric.append(token)
        else:
            review_required_nonnumeric.append(token)
    if reject_unapproved:
        unexpected = _dedupe([
            *review_required_nonnumeric,
            *review_required_numeric,
        ])
    planned_counts: dict[str, int] = {}
    for item in contract.get("surface_plan") or []:
        key = _compact(item.get("text") or "")
        if key:
            planned_counts[key] = planned_counts.get(key, 0) + 1
    duplicate_texts: list[str] = []
    occurrence_counts: dict[str, int] = {}
    for value, value_key in zip(approved, approved_compact):
        count = sum(1 for token in raw_detected if _compact(token) == value_key)
        occurrence_counts[value] = count
        allowed_count = max(1, planned_counts.get(value_key, 0))
        if count > allowed_count:
            duplicate_texts.append(value)
    return {
        **contract,
        "detected_texts": detected,
        "narration_grounded_texts": narration_grounded,
        "review_required_nonnumeric_texts": review_required_nonnumeric,
        "review_required_numeric_texts": review_required_numeric,
        "occurrence_counts": occurrence_counts,
        "duplicate_texts": duplicate_texts,
        "unexpected_texts": unexpected,
        "passed": not unexpected and not duplicate_texts,
    }


def detected_deterministic_texts(
    visible_tokens: Iterable[str],
    scene: dict[str, Any] | None,
) -> list[str]:
    """기본 래스터에 이미지 모델이 직접 그린 승인 금융 수치를 찾는다."""
    contract = build_scene_text_contract(scene)
    token_keys = [_compact(value) for value in visible_tokens if len(_compact(value)) >= 3]
    detected: list[str] = []
    for expected in contract["deterministic_texts"]:
        expected_key = _compact(expected)
        if expected_key and any(
            expected_key in token_key or token_key in expected_key
            for token_key in token_keys
        ):
            detected.append(expected)
    return detected

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
    # 값의 첫 글자만 소비하면 ``8888.11``을 지운 뒤 ``.11``이 남아 모델에
    # 새로운 숫자처럼 전달된다. 숫자·대문자 라벨·한국어 낱말을 하나의 완전한
    # 토큰으로 소비하고, 앞부분의 탐욕 매칭이 토큰 중간에서 시작하지 못하게
    # 경계를 둔다.
    r"[^.;\n]{0,80}(?:"
    r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?(?![\w.])|"
    r"(?<![A-Za-z0-9])(?-i:[A-Z][A-Z0-9 _&/-]{1,40})(?![A-Za-z0-9])|"
    r"(?<![가-힣])[가-힣]{2,40}(?![가-힣])"
    r")",
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

# 이미지 모델에 전달되는 시각 지시 복사본에서만 금융 수치를 제거한다.
# ``2D``·``16:9`` 같은 제작 규격을 보존하면서 금액·비율·배수·지수 수준만
# 차단하려고 단위가 있는 숫자에 한정한다. 승인 내레이션 원문은 수정하지 않는다.
_VISUAL_FINANCIAL_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9가-힣])"
    r"[+-]?\d[\d,.]*(?:\.\d+)?\s*"
    r"(?:%|퍼센트|포인트|pt|배|x|×|조(?:\s*원)?|억(?:\s*원)?|만(?:\s*원)?|원|달러|"
    r"percent|percentage|points?|times?|trillion(?:\s+won)?|billion(?:\s+won)?|"
    r"million(?:\s+won)?|won|dollars?)"
    # 한국어 조사(입니다/이고/에서)가 단위 바로 뒤에 붙는 정상 문장을
    # 허용하되 영문·숫자 식별자 내부의 일부는 매치하지 않는다.
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_BLANK_SURFACE = "an unlettered scene-integrated visual surface with non-linguistic shapes"
# 여러 정규식 치환이 긴 최종 문구를 다시 문자 지시로 오인하지 않도록 모든
# 판정이 끝날 때까지 의미 없는 소문자 표식으로 보존한다.
_TEXT_SLOT = "scenetextplaceholder"
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


def _financial_placeholder(value: str, *, korean: bool) -> str:
    lowered = str(value or "").casefold()
    if any(token in lowered for token in ("%", "퍼센트", "percent")):
        return "검증된 비율" if korean else "verified financial rate"
    if any(token in lowered for token in ("포인트", "point", "pt")):
        return "검증된 지수 수준" if korean else "verified market level"
    if any(token in lowered for token in ("배", "×", "times")) or re.search(r"\d\s*x\b", lowered):
        return "검증된 배수" if korean else "verified financial multiple"
    return "검증된 금액" if korean else "verified financial magnitude"


def redact_financial_values_for_visual_direction(value: str) -> str:
    """승인 내레이션을 바꾸지 않고 시각 연출용 복사본의 수치만 가린다."""
    return _VISUAL_FINANCIAL_VALUE_RE.sub(
        lambda match: _financial_placeholder(match.group(0), korean=True),
        str(value or ""),
    )


def redact_financial_values_from_model_prompt(
    prompt: str,
    *,
    deterministic_values: Iterable[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Gemini 경계에서 승인 결정론 수치와 번역된 금융 수치를 제거한다."""
    source = str(prompt or "")
    cleaned = source
    exact_redactions: list[str] = []
    for raw in _dedupe(deterministic_values or []):
        if raw and re.search(re.escape(raw), cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(
                re.escape(raw),
                _financial_placeholder(raw, korean=False),
                cleaned,
                flags=re.IGNORECASE,
            )
            exact_redactions.append(raw)
    translated_redactions = [match.group(0) for match in _VISUAL_FINANCIAL_VALUE_RE.finditer(cleaned)]
    cleaned = _VISUAL_FINANCIAL_VALUE_RE.sub(
        lambda match: _financial_placeholder(match.group(0), korean=False),
        cleaned,
    )
    return cleaned, {
        "version": "gemini-financial-value-redaction-v1",
        "changed": cleaned != source,
        "exact_deterministic_values_redacted": exact_redactions,
        "translated_financial_values_redacted": translated_redactions,
    }


def redact_unapproved_entity_literals_from_model_prompt(
    prompt: str,
    *,
    core_entities: Iterable[str] | None = None,
    allowed_texts: Iterable[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """의미용 엔티티가 이미지의 무단 라벨로 복제되지 않게 이름만 중립화한다."""
    from app.utils.entity_english_map import all_entity_infos, get_entity_english_name

    cleaned = str(prompt or "")
    allowed_keys = {_compact(value) for value in (allowed_texts or []) if _compact(value)}
    redacted: list[str] = []
    candidates: list[str] = []
    for entity in _dedupe(core_entities or []):
        mapped, confidence = get_entity_english_name(entity)
        candidates.append(entity)
        if confidence != "uncertain" and mapped:
            candidates.append(mapped)
    # 과거 저장 프롬프트에는 현재 내레이션과 무관한 KOSPI·PER·회사명이
    # 그대로 남아 있을 수 있다. 기업·지수·금융용어 레지스트리의 정확한
    # 이름도 검사하되, gold/silver 같은 일반 재료 단어가 필요한 장면은
    # 훼손하지 않도록 원자재 범주는 전역 정리에 포함하지 않는다.
    for info in all_entity_infos():
        if info.category == "macro_commodity":
            continue
        candidates.extend((info.korean, info.english_official, info.fictional_label))
    for literal in sorted(_dedupe(candidates), key=len, reverse=True):
        if _compact(literal) in allowed_keys:
            continue
        # Goldie/golden처럼 다른 단어에 포함된 짧은 원자재 이름은 건드리지 않는다.
        boundary = rf"(?<![A-Za-z0-9가-힣]){re.escape(literal)}(?![A-Za-z0-9가-힣])"
        if re.search(boundary, cleaned, flags=0):
            cleaned = re.sub(boundary, "the relevant scene entity", cleaned, flags=0)
            redacted.append(literal)
    return cleaned, {
        "version": "gemini-unapproved-entity-literal-redaction-v1",
        "changed": cleaned != str(prompt or ""),
        "redacted_literals": redacted,
    }


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
            surface_id = str(item.get("surface_id") or item.get("surface") or "").strip()
            if not surface_id:
                raise ValueError("각 승인 문구에는 장면 사물의 물리 표면 ID가 필요합니다.")
            item["surface"] = surface_id
            item["surface_id"] = surface_id
            item["semantic_object_id"] = str(
                item.get("semantic_object_id") or surface_id
            ).strip()

        # 여러 문구가 같은 모니터·보드에 들어가는 것은 정상이다. 다만 과거
        # scene07처럼 서로 다른 네 문구를 모두 ``main`` 하나로 뭉쳐 모델과
        # 렌더러가 위치를 추측하게 두지 않는다. 공유 표면은 각 문구의 상대
        # 영역을 명시하고 서로 겹치지 않을 때만 허용한다.
        by_surface: dict[str, list[dict[str, Any]]] = {}
        for item in plan:
            by_surface.setdefault(item["surface_id"], []).append(item)
        for surface_id, items in by_surface.items():
            if len(items) < 2:
                continue
            regions: list[tuple[float, float, float, float]] = []
            for item in items:
                region = item.get("region")
                if not isinstance(region, (list, tuple)) or len(region) != 4:
                    raise ValueError(
                        f"공유 표면 {surface_id}의 각 문구에는 비중첩 상대 영역이 필요합니다."
                    )
                x, y, width, height = (float(value) for value in region)
                if not (
                    0 <= x < 1 and 0 <= y < 1 and width > 0 and height > 0
                    and x + width <= 1 and y + height <= 1
                ):
                    raise ValueError(f"공유 표면 {surface_id}의 문구 영역이 범위를 벗어났습니다.")
                regions.append((x, y, x + width, y + height))
            for index, first in enumerate(regions):
                for second in regions[index + 1:]:
                    if (
                        max(first[0], second[0]) < min(first[2], second[2])
                        and max(first[1], second[1]) < min(first[3], second[3])
                    ):
                        raise ValueError(f"공유 표면 {surface_id}의 문구 영역이 서로 겹칩니다.")
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
    # 따옴표 안의 고유명사도 이미지 모델에는 그대로 쓸 문자 지시가 된다.
    # 혼합 대소문자 회사명(Samsung Electronics 등)을 예외로 두지 않는다.
    return bool(candidate and re.search(r"[A-Za-z가-힣]|\d", candidate))


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
            return _TEXT_SLOT
        return match.group(0)

    cleaned = _QUOTED_TEXT_RE.sub(replace_quoted, source)
    # ``Labeled containers marked <문구> and <문구>``처럼 문자와 장면 소품이
    # 한 절에 섞인 경우에는 라벨만 제거하고 컨테이너와 제외 동작을 보존한다.
    def replace_labeled_objects(match: re.Match[str]) -> str:
        label_count = match.group("labels").count(_TEXT_SLOT)
        quantity = {2: "two ", 3: "three "}.get(label_count, "multiple " if label_count > 3 else "")
        replacement = f"{quantity}unlettered {match.group('object').strip()}"
        return replacement[:1].upper() + replacement[1:] if match.group(0)[:1].isupper() else replacement

    cleaned = re.sub(
        rf"\b(?:labeled|labelled)\s+(?P<object>[^,.;\n\"']{{1,60}}?)\s+"
        rf"(?:marked|printed|stamped|reading|saying)\s+"
        rf"(?P<labels>{_TEXT_SLOT}(?:\s+(?:and|or)\s+{_TEXT_SLOT})*)",
        replace_labeled_objects,
        cleaned,
        flags=re.IGNORECASE,
    )
    # 따옴표 문자열 뒤에 붙었던 의미 없는 글자 장식 표현까지 중립 표면에
    # 달라붙으면 ``typographylow`` 같은 새 의사 문구가 생긴다. 문자열을
    # 제거한 경우에만 그 장식 꼬리를 함께 정리한다.
    cleaned = re.sub(
        rf"{re.escape(_TEXT_SLOT)}\s+(?:expectation|warning|headline|caption|label)\s+"
        r"(?:glow|text|sign|lettering)?",
        _TEXT_SLOT,
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        rf"{re.escape(_TEXT_SLOT)}\s+in\s+(?:(?:bold|large|bright|glowing)\s+)*"
        r"(?:digits|letters|text|typography)",
        _TEXT_SLOT,
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        rf"\b(?:label(?:ed|led)?|reading|saying|titled|captioned|"
        rf"stamped|printed|write|written|spelled)\b\s*(?:as|with|:)?\s*"
        rf"(?={re.escape(_TEXT_SLOT)})",
        "with ",
        cleaned,
        flags=re.IGNORECASE,
    )

    def replace_unquoted(match: re.Match[str]) -> str:
        if any(_compact(value) in _compact(match.group(0)) for value in allowed):
            return match.group(0)
        return f"with {_TEXT_SLOT}"

    cleaned = _UNQUOTED_TEXT_CLAUSE_RE.sub(replace_unquoted, cleaned)

    def replace_exact(match: re.Match[str]) -> str:
        if any(_compact(value) in _compact(match.group(0)) for value in allowed):
            return match.group(0)
        return _TEXT_SLOT

    cleaned = _EXACT_VALUE_RE.sub(replace_exact, cleaned)

    def replace_display(match: re.Match[str]) -> str:
        if any(_compact(value) in _compact(match.group(0)) for value in allowed):
            return match.group(0)
        return _replace_display_value_instruction(match).replace(_BLANK_SURFACE, _TEXT_SLOT)

    cleaned = _DISPLAY_VALUE_RE.sub(replace_display, cleaned)
    cleaned = cleaned.replace(_TEXT_SLOT, _BLANK_SURFACE)
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
    *,
    occurrence_counts: dict[str, int] | None = None,
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
    # 비수치 문구는 일반 레인에서 후단 멀티모달 검수로 넘길 수 있지만,
    # 숫자는 이미지 모델이 직접 만들 수 없는 전역 계약이다. 따라서 엄격
    # 문자 레인 여부와 무관하게 승인 목록에 없는 숫자는 항상 즉시 거절한다.
    # 이 경계가 없으면 OCR이 ``0000.000``·임의 연도·가짜 계기값을 읽고도
    # review_required에만 남긴 채 기본 래스터를 통과시킬 수 있었다.
    unexpected = _dedupe(review_required_numeric)
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
    measured_occurrences = occurrence_counts if isinstance(occurrence_counts, dict) else {}
    resolved_occurrence_counts: dict[str, int] = {}
    for value, value_key in zip(approved, approved_compact):
        token_count = sum(1 for token in raw_detected if _compact(token) == value_key)
        count = max(token_count, int(measured_occurrences.get(value, 0) or 0))
        resolved_occurrence_counts[value] = count
        allowed_count = max(1, planned_counts.get(value_key, 0))
        if count > allowed_count:
            duplicate_texts.append(value)
    return {
        **contract,
        "detected_texts": detected,
        "narration_grounded_texts": narration_grounded,
        "review_required_nonnumeric_texts": review_required_nonnumeric,
        "review_required_numeric_texts": review_required_numeric,
        "occurrence_counts": resolved_occurrence_counts,
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

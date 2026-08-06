"""검증 수치가 이미지 모델 프롬프트로 새지 않게 막는 최종 게이트."""
from __future__ import annotations

import re
from typing import Any


class PromptContainsVerifiedDataError(ValueError):
    """검증 사실의 수치가 최종 이미지 프롬프트에 포함된 경우 발생한다."""


_NUMBER_TOKEN = re.compile(r"(?<![\w.])\d+(?:[,.]\d+)*(?:\s*[%％]|\s*(?:원|달러|USD|KRW|배|만|억))?(?![\w.])", re.IGNORECASE)


def _normalized_number_tokens(value: object) -> set[str]:
    return {
        re.sub(r"[\s,]", "", token).replace("％", "%").lower()
        for token in _NUMBER_TOKEN.findall(str(value or ""))
    }


def assert_prompt_has_no_verified_numbers(prompt: str, scene: dict[str, Any]) -> None:
    """검증된 figure의 숫자 토큰이 최종 프롬프트에 있으면 요청 전에 실패한다."""
    facts = scene.get("verified_facts") or scene.get("facts") or []
    if not isinstance(facts, list):
        return
    verified: set[str] = set()
    for fact in facts:
        if isinstance(fact, dict):
            verified.update(_normalized_number_tokens(fact.get("figure")))
            verified.update(_normalized_number_tokens(fact.get("value")))
    if not verified:
        return
    # 선 두께 같은 화풍 규격은 검증된 금융 수치가 아니다. 이 표현을
    # 제거한 뒤에만 사실 수치와의 중복을 검사한다.
    factual_prompt = re.sub(
        r"\(?\s*\d+\s*-\s*\d+\s*px(?:\s+equivalent)?\s*\)?", "", prompt, flags=re.IGNORECASE
    )
    factual_prompt = re.sub(
        r"1\s*/\s*3", "", factual_prompt, flags=re.IGNORECASE
    )
    prompt_tokens = _normalized_number_tokens(factual_prompt)
    overlap = sorted(verified & prompt_tokens)
    if overlap:
        scene_id = scene.get("scene_id") or scene.get("id") or "unknown"
        raise PromptContainsVerifiedDataError(
            f"검증 수치가 이미지 프롬프트에 포함되어 요청을 중단합니다: scene={scene_id}, tokens={', '.join(overlap)}"
        )

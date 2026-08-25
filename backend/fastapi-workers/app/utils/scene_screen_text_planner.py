"""승인 대본에서 장면 로컬 화면 문구만 결정론적으로 고른다.

이미지의 모든 문자를 없애는 대신, 승인 내레이션에 실제로 있는 회사명·지수명·
핵심 금융 용어와 수치 표현만 씬 단위 허용 목록으로 만든다. 숫자는 이후
Pillow/FFmpeg 표면 렌더러가 담당하며 이미지 모델에는 직접 쓰게 하지 않는다.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


_QUOTED_PHRASE_RE = re.compile(r"['\"“”‘’](?P<text>[^'\"“”‘’\n]{2,32})['\"“”‘’]")
_NUMBER = r"[+-]?\d[\d,]*(?:\.\d+)?"
_RANGE_JOIN = r"(?:에서|~|∼|〜|–|—|-)"
_FINANCIAL_VALUE_RE = re.compile(
    r"(?:"
    + _NUMBER + r"\s*조\s*" + _RANGE_JOIN + r"\s*" + _NUMBER + r"\s*조\s*원?"
    r"|" + _NUMBER + r"\s*" + _RANGE_JOIN + r"\s*" + _NUMBER + r"\s*(?:퍼센트포인트|퍼센트|포인트|%p|%)"
    r"|" + _NUMBER + r"\s*만\s*" + _NUMBER + r"\s*원"
    r"|" + _NUMBER + r"\s*조(?:\s*" + _NUMBER + r"\s*억)?(?:\s*" + _NUMBER + r"\s*만)?\s*원?"
    r"|" + _NUMBER + r"\s*억(?:\s*" + _NUMBER + r"\s*만)?\s*(?:원|주)?"
    r"|" + _NUMBER + r"\s*(?:퍼센트포인트|퍼센트|포인트|%p|%|만\s*원|원|배)"
    r")"
)

# 승인 대본에 실제로 등장할 때만 사용한다. 이 목록은 문구를 새로 만드는
# 사전이 아니라, 긴 내레이션에서 화면에 유용한 원문 토큰을 고르는 필터다.
_DISPLAY_TERMS = (
    "삼성전자",
    "SK하이닉스",
    "코스피",
    "코스닥",
    "주주환원",
    "원달러 환율",
    "외국인",
    "거래대금",
    "거래량",
    "반도체",
    "IR",
)


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", normalized)


def _scene_narration(scene: dict[str, Any]) -> str:
    return str(
        scene.get("text_for_tts")
        or scene.get("content")
        or scene.get("text")
        or scene.get("narration")
        or ""
    ).strip()


def derive_scene_screen_texts(scene: dict[str, Any], *, limit: int = 4) -> list[str]:
    """기존 명시 문구를 보존하고, 비어 있을 때만 승인 원문에서 최대 4개를 고른다."""
    existing = [str(value).strip() for value in (scene.get("screen_texts") or []) if str(value).strip()]
    if existing:
        return existing

    narration = _scene_narration(scene)
    if not narration:
        return []

    candidates: list[tuple[int, int, str]] = []
    for match in _QUOTED_PHRASE_RE.finditer(narration):
        candidates.append((0, match.start(), match.group("text").strip()))
    for term in _DISPLAY_TERMS:
        start = narration.find(term)
        if start >= 0:
            candidates.append((1, start, term))
    for match in _FINANCIAL_VALUE_RE.finditer(narration):
        candidates.append((2, match.start(), match.group(0).strip()))

    selected: list[str] = []
    for _priority, _position, value in sorted(candidates, key=lambda item: (item[0], item[1])):
        key = _compact(value)
        if not key:
            continue
        # 인용구가 "10퍼센트 족쇄"를 이미 포함하면 "10퍼센트"를 또 쓰지 않는다.
        if any(key in _compact(item) or _compact(item) in key for item in selected):
            continue
        selected.append(value)
        if len(selected) >= max(0, int(limit)):
            break
    return selected


def attach_scene_screen_texts(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """장면 순서와 승인 내레이션을 바꾸지 않고 화면 문구 계약만 보완한다."""
    planned: list[dict[str, Any]] = []
    for source in scenes or []:
        scene = dict(source)
        previous_source = str(source.get("screen_text_source") or "")
        if previous_source.startswith("approved_narration_exact_extract_"):
            # 자동 추출 규칙이 개선된 경우 과거 v1의 잘린 복합 수치(예:
            # ``25만 7000원`` → ``7000원``)를 명시 계약처럼 고정하지 않는다.
            # 사람이 작성한 explicit_scene_contract는 계속 그대로 보존한다.
            scene["screen_texts"] = []
        scene["screen_texts"] = derive_scene_screen_texts(scene)
        scene["screen_text_source"] = (
            "explicit_scene_contract"
            if source.get("screen_texts") and not previous_source.startswith("approved_narration_exact_extract_")
            else "approved_narration_exact_extract_v2"
        )
        planned.append(scene)
    return planned

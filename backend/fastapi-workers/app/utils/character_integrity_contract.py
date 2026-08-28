"""창작 연출을 고정하지 않고 명백한 캐릭터 결함만 경계한다."""
from __future__ import annotations

import re
from typing import Any


_CROSSED_ARMS_RE = re.compile(
    r"(?:,?\s*)?(?:with\s+)?(?:both\s+)?arms?\s+crossed(?:\s+[^,.;]{0,28})?",
    re.IGNORECASE,
)
_ACTIVE_ARM_ACTION_RE = re.compile(
    r"\b(?:point(?:ing|s|ed)?|hold(?:ing|s)?|rais(?:ing|es|ed)|waving|"
    r"gestur(?:ing|es|ed)|press(?:ing|es|ed)|grabb(?:ing|s|ed)|"
    r"carry(?:ing|ies|ied)|present(?:ing|s|ed))\b",
    re.IGNORECASE,
)
_BUBBLE_RE = re.compile(
    r"\b(?:speech|thought|comic)\s+(?:bubble|balloon)|\b(?:bubble|balloon)\s+(?:reading|saying|with)\b",
    re.IGNORECASE,
)
_POSITIVE_BUBBLE_CLAUSE_RE = re.compile(
    r"\b(?:beside|with|holding|pointing\s+to)?\s*(?:an?\s+)?"
    r"(?:speech|thought|comic)\s+(?:bubble|balloon)\b[^,.;\n]{0,120}",
    re.IGNORECASE,
)


COIN_SILHOUETTE_CONTRACT = (
    "The same round coin disc remains the dominant unified head-and-upper-body silhouette. "
    "A scene-specific costume may wrap around and extend modestly below the coin rim, as it does in the approved channel examples; "
    "do not reject that accepted costume extension as a separate torso. The costume must not become a narrow-necked independent human trunk "
    "or displace the coin as the dominant body identity. Attach exactly two short compact arms at the side rim and exactly two short compact legs "
    "with small feet at the lower rim. Keep each visible leg roughly half of the coin diameter or shorter, compact, and rounded; "
    "never hang long human legs from a coin head. "
)


def resolve_pose_conflicts(prompt: str) -> tuple[str, list[str]]:
    """`가리키기+팔짱`처럼 동시에 수행할 수 없는 보조 자세를 제거한다."""
    source = str(prompt or "")
    reasons: list[str] = []
    cleaned = source
    if _CROSSED_ARMS_RE.search(source) and _ACTIVE_ARM_ACTION_RE.search(source):
        cleaned = _CROSSED_ARMS_RE.sub("", cleaned)
        reasons.append("removed_conflicting_arms_crossed_action")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned).strip()
    return cleaned, reasons


def apply_character_integrity_contract(
    prompt: str,
    scene: dict[str, Any] | None = None,
    *,
    retry_reasons: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """표정·의상·구도는 장면에 맡기고 포즈 충돌과 해부학 오류만 제한한다."""
    source = scene or {}
    cleaned, changes = resolve_pose_conflicts(prompt)
    text_contract = source.get("image_text_contract") or {}
    bubble_policy = str(text_contract.get("bubble_policy") or "unplanned").strip().lower()
    bubble_allowed = bubble_policy in {"allowed", "required"} or bool(text_contract.get("bubble_allowed"))
    if not bubble_allowed and _POSITIVE_BUBBLE_CLAUSE_RE.search(cleaned):
        cleaned = _POSITIVE_BUBBLE_CLAUSE_RE.sub(" beside an in-world scene prop", cleaned)
        changes.append("removed_unplanned_bubble_instruction")

    direction = source.get("art_direction") or {}
    render_contract = source.get("v5_render_contract") or {}
    directed_spec = source.get("scene_spec") or {}
    wardrobe = str(
        directed_spec.get("character_costume")
        or direction.get("wardrobe")
        or render_contract.get("scene_wardrobe")
        or ""
    ).strip()
    suffix = (
        " FINAL CHARACTER QUALITY BOUNDARY: keep the figure recognizably in the same round gold-coin mascot design family and 2D drawing language as the channel references. "
        "Preserve the approved face construction while expression and acting change: large readable eyes with visible white sclera, warm brown pupil or iris detail, "
        "layered white catchlights, a soft forehead reflection highlight, and gently curved eyebrows rather than sharply angled or deeply furrowed eyebrows. "
        "Costume, headwear, pose, mouth shape, scale, and framing remain scene-specific; do not force one outfit or one neutral expression. "
        "Reject a different character species, incompatible face language, or an accidental featureless emoji. "
        + COIN_SILHOUETTE_CONTRACT
        + "Use natural connected anatomy with no extra, duplicated, detached, or fused limb or hand. Resolve the pose as one physically coherent action. "
    )
    if wardrobe:
        suffix += f"The scene-specific costume direction is: {wardrobe}. Do not replace it with a generic finance-presenter uniform. "
        if "police" not in wardrobe.casefold() and "law enforcement" not in wardrobe.casefold():
            suffix += "Do not replace it with an unrelated police or law-enforcement costume. "
    if bubble_allowed:
        suffix += "A bubble may appear only in the form and wording explicitly planned by this scene. "
    elif bubble_policy == "forbidden":
        suffix += "This storyboard explicitly forbids a speech or thought bubble in this scene. "
    if retry_reasons:
        suffix += (
            "This is a targeted integrity correction. Keep the same setting, economic metaphor, camera, palette, "
            "background density, and approved text surfaces; correct only: "
            + ", ".join(str(value) for value in retry_reasons[:8])
            + ". "
        )
    return cleaned + suffix, {
        "version": "character-integrity-v6-dominant-coin-silhouette",
        "changes": changes,
        "scene_wardrobe": wardrobe,
        "bubble_policy": bubble_policy,
        "bubble_allowed": bubble_allowed,
    }

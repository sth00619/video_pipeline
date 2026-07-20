"""Style/TTS metadata derived from approved narration without rewriting facts.

This module is deliberately post-generation: it does not modify wording,
numbers, dates, entities, or source facts.  It only supplies production cues
used by the image editor, TTS tag mapper, and Gate 3 review UI.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.utils.sentence_splitter import split_sentences

PHASES = (
    ("hook", "Hook & Question", 0.08),
    ("context", "Context & Escalation", 0.55),
    ("twist", "Twist & Insight", 0.85),
    ("resolution", "Resolution & CTA", 1.00),
)
EMOTIONS = ("neutral", "highlight", "surprised", "worried", "happy")
FORBIDDEN_PATTERNS = ("무조건", "확실합니다", "무조건 수익", "지금 사야", "반드시 오릅니다")


def default_style_mix(category: str, is_shorts: bool = False) -> dict[str, float]:
    """Return the channel's delivery ratio for every supported content category.

    The ratio controls presentation only (storytelling rhythm versus explanatory
    delivery).  It must never change the verified facts, figures, or source
    context supplied to the script worker.
    """
    category = (category or "CUSTOM").upper()
    longform_mix = {
        "KOSPI": (0.70, 0.30),
        "KOSDAQ": (0.75, 0.25),
        "US_STOCKS": (0.60, 0.40),
        "INDIVIDUAL_STOCK": (0.65, 0.35),
        "ASSOCIATED_STOCKS": (0.65, 0.35),
        "GLOBAL_MACRO": (0.50, 0.50),
        "CRYPTO": (0.65, 0.35),
        "CUSTOM": (0.60, 0.40),
    }
    shorts_mix = {
        "KOSPI": (0.80, 0.20),
        "KOSDAQ": (0.80, 0.20),
        "US_STOCKS": (0.70, 0.30),
        "INDIVIDUAL_STOCK": (0.75, 0.25),
        "ASSOCIATED_STOCKS": (0.75, 0.25),
        "GLOBAL_MACRO": (0.60, 0.40),
        "CRYPTO": (0.75, 0.25),
        "CUSTOM": (0.70, 0.30),
    }
    storytelling, knowledge = (shorts_mix if is_shorts else longform_mix).get(
        category,
        (shorts_mix if is_shorts else longform_mix)["CUSTOM"],
    )
    return {"economic_hunter": storytelling, "knowledge_bite": knowledge}


def _phase(index: int, total: int) -> tuple[str, str]:
    position = (index + 1) / max(total, 1)
    for key, label, boundary in PHASES:
        if position <= boundary:
            return key, label
    return PHASES[-1][0], PHASES[-1][1]


def _emotion(text: str, phase: str, pose: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ("급락", "하락", "위험", "불확실", "우려", "리스크")):
        return "worried"
    if any(token in lower for token in ("반전", "그런데", "뜻밖", "의외", "왜")):
        return "surprised"
    if any(token in lower for token in ("상승", "개선", "기회", "회복")):
        return "happy"
    if any(char.isdigit() for char in text) or pose in {"pointing", "explaining"}:
        return "highlight"
    return "surprised" if phase == "hook" else "neutral"


def _action(pose: str, emotion: str) -> str:
    if pose == "pointing" or emotion == "highlight":
        return "pointer_up"
    if pose in {"thinking", "worried"} or emotion == "worried":
        return "arms_crossed"
    if pose in {"explaining", "surprised"} or emotion == "surprised":
        return "hands_open"
    return "neutral"


def _edit_marker(text: str, emotion: str) -> str:
    if any(char.isdigit() for char in text):
        return "data_overlay"
    if emotion in {"surprised", "highlight"}:
        return "emphasis_zoom"
    return "scene_change"


def annotate_sections(sections: list[dict[str, Any]], target_seconds: int) -> list[dict[str, Any]]:
    """Add only metadata; existing section content stays byte-for-byte intact."""
    total_chars = sum(len(re.sub(r"\s+", "", str(item.get("content") or item.get("text") or ""))) for item in sections) or 1
    elapsed = 0.0
    output: list[dict[str, Any]] = []
    for index, source in enumerate(sections):
        item = dict(source)
        text = str(item.get("content") or item.get("text") or "").strip()
        phase, phase_name = _phase(index, len(sections))
        seconds = max(0.5, target_seconds * len(re.sub(r"\s+", "", text)) / total_chars)
        emotion = _emotion(text, phase, str(item.get("pose") or ""))
        item.update({
            "phase": phase, "phase_name": phase_name,
            "start_seconds": round(elapsed, 2), "end_seconds": round(elapsed + seconds, 2),
            "emotion_tag": emotion, "character_action": _action(str(item.get("pose") or ""), emotion),
            "edit_marker": _edit_marker(text, emotion), "text_for_tts": text,
        })
        item["sentences"] = [{
            "sentence_id": f"s{index + 1:03d}_{sentence_index + 1}", "text": sentence,
            "text_for_tts": sentence, "emotion_tag": _emotion(sentence, phase, str(item.get("pose") or "")),
            "character_action": item["character_action"], "edit_marker": _edit_marker(sentence, emotion),
            "estimated_seconds": round(seconds * len(sentence) / max(len(text), 1), 2),
            # References are attached only when a fact-bundle ID exists; we
            # intentionally never invent a citation merely because text has a number.
            "fact_refs": [], "market_data_refs": [],
        } for sentence_index, sentence in enumerate(split_sentences(text))]
        elapsed += seconds
        output.append(item)
    return output


def validate_delivery(sections: list[dict[str, Any]]) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    tags: list[str] = []
    for scene in sections:
        text = str(scene.get("content") or scene.get("text") or "")
        for forbidden in FORBIDDEN_PATTERNS:
            if forbidden in text:
                violations.append({"type": "FORBIDDEN_PHRASE", "scene": str(scene.get("title", "")), "value": forbidden})
        tags.append(str(scene.get("emotion_tag") or "neutral"))
        for sentence in scene.get("sentences") or []:
            if re.search(r"\d+(?:\.\d+)?%", str(sentence.get("text_for_tts") or "")):
                violations.append({"type": "RAW_PERCENT_FOR_TTS", "scene": str(scene.get("title", "")), "value": sentence["text_for_tts"]})
    max_run = 0
    current = 0
    previous = None
    for tag in tags:
        current = current + 1 if tag == previous else 1
        previous = tag
        max_run = max(max_run, current)
    if max_run >= 5:
        violations.append({"type": "LOW_EMOTION_DIVERSITY", "scene": "sequence", "value": str(max_run)})
    phase_counts = Counter(str(scene.get("phase") or "") for scene in sections)
    return {"passed": not violations, "violations": violations, "phase_counts": dict(phase_counts), "emotion_counts": dict(Counter(tags))}

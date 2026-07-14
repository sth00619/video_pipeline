"""Optional multimodal review for whether an image serves its finance-video scene."""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _review_priority(scene: dict[str, Any]) -> int:
    profile = scene.get("image_profile") or {}
    direction = scene.get("art_direction") or {}
    if profile.get("tier") == "pro":
        return 100
    if direction.get("overlay_strategy") in {"market_chart", "headline_card"}:
        return 80
    return 10


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (TypeError, json.JSONDecodeError):
        return None


def assess_visual_alignment(scenes: list[dict[str, Any]], *, enabled: bool, max_scenes: int) -> dict[str, Any]:
    """Use a compact vision review only on the editorial anchor scenes.

    This is deliberately post-generation. It never silently spends more money
    on retries; it marks a scene for the existing user-controlled regeneration
    action instead.
    """
    report: dict[str, Any] = {"enabled": enabled, "reviewed": [], "skipped": [], "warnings": []}
    if not enabled:
        report["warnings"].append("visual_qa_disabled")
        return report
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        report["warnings"].append("visual_qa_no_gemini_key")
        return report

    eligible = [scene for scene in scenes if Path(str(scene.get("image_path") or "")).exists()]
    eligible.sort(key=_review_priority, reverse=True)
    for scene in eligible[: max(0, int(max_scenes))]:
        index = int(scene.get("index", 0))
        try:
            image_path = Path(str(scene["image_path"]))
            encoded = base64.b64encode(image_path.read_bytes()).decode()
            direction = scene.get("art_direction") or {}
            instruction = (
                "You are the visual quality editor for a Korean finance explainer. "
                "Score this generated image against the narration and visual brief. "
                "Reject generic gold/rocket/fire imagery when it is not specifically justified. "
                "Require original 2D editorial-comic treatment: variable black ink outlines, cel shading, colorful layered context; "
                "flag glossy 3D/toy, empty dark studio, or generic mascot treatment. "
                "Return JSON only: {scene_match:0-100, finance_specificity:0-100, composition:0-100, "
                "style_adherence:0-100, repetition_risk:0-100, decision:'accept'|'review', reason:'short Korean text'}.\n\n"
                f"Narration: {scene.get('text') or ''}\n"
                f"Scene family: {direction.get('family') or ''}\n"
                f"Required setting: {direction.get('setting') or ''}\n"
                f"Required props: {', '.join(direction.get('props') or [])}\n"
                f"Character required: {direction.get('character_required')}"
            )
            payload = {
                "contents": [{"parts": [
                    {"text": instruction},
                    {"inlineData": {"mimeType": "image/png", "data": encoded}},
                ]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
            }
            response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                params={"key": api_key}, json=payload, timeout=45,
            )
            if response.status_code != 200:
                report["warnings"].append(f"visual_qa_http_{response.status_code}")
                continue
            parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts") or []
            verdict = _parse_json(next((part.get("text") for part in parts if part.get("text")), ""))
            if not verdict:
                report["warnings"].append(f"visual_qa_invalid_json:{index}")
                continue
            scores = [float(verdict.get(key, 0)) for key in ("scene_match", "finance_specificity", "composition", "style_adherence")]
            score = round(sum(scores) / len(scores))
            retry = score < 72 or str(verdict.get("decision", "")).lower() == "review"
            report["reviewed"].append({
                "index": index,
                "score": score,
                "retry_recommended": retry,
                "reason": str(verdict.get("reason") or ""),
                "raw": verdict,
            })
        except Exception as exc:
            logger.warning("visual QA failed for scene %s: %s", index, exc)
            report["warnings"].append(f"visual_qa_error:{index}")

    reviewed_indices = {item["index"] for item in report["reviewed"]}
    report["skipped"] = [int(scene.get("index", 0)) for scene in eligible if int(scene.get("index", 0)) not in reviewed_indices]
    report["score"] = round(sum(item["score"] for item in report["reviewed"]) / len(report["reviewed"])) if report["reviewed"] else None
    return report

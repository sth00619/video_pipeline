"""Deterministic quality gates for the generated-video pipeline.

The gates intentionally do not depend on another LLM.  They make failures
visible in job metadata and keep generation prompts, narration and timing
within a predictable production-safe contract.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


PROMPT_ARTIFACT_RE = re.compile(
    r"\b(?:3d\s+render|render|vibrant(?:\s+colors?)?|cinematic|"
    r"anime\s+cartoon|8k|4k|negative\s+prompt|aspect\s+ratio|"
    r"high\s+detail|smooth\s+shading)\b",
    re.IGNORECASE,
)
PROMPT_LABEL_RE = re.compile(r"\[\s*(?:visual|image|prompt|비주얼|이미지|프롬프트)[^\]]*\]", re.IGNORECASE)

SECTION_VISUALS = {
    "intro": ("character_hero", "hero character establishes the topic"),
    "background": ("news_context", "newsroom or real-world business context"),
    "data": ("data_visual", "chart-shaped data visual with no generated text"),
    "scenario": ("character_explainer", "character explains a causal scenario"),
    "action": ("comparison", "clear comparison of two outcomes or choices"),
    "conclusion": ("takeaway", "calm conclusion with a memorable takeaway"),
}


def extract_narration(text: str) -> str:
    """Return only the spoken narration from a rich production script."""
    if not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    dialogue_label = re.compile(r"^\s*\[\s*(?:대사|내레이션|narration|dialogue)\s*\]\s*(.*)$", re.I)
    non_narration_label = re.compile(
        r"^\s*\[\s*(?:비주얼|이미지|프롬프트|감정|visual|image|prompt|emotion|"
        r"추천\s*제목|추천\s*썸네일|더보기\s*설명|쇼츠\s*대본)[^\]]*\].*$",
        re.I,
    )
    has_dialogue_labels = any(dialogue_label.match(line) for line in lines)
    spoken: list[str] = []
    collecting = False

    for raw_line in lines:
        line = raw_line.strip()
        match = dialogue_label.match(line)
        if match:
            collecting = True
            inline = match.group(1).strip()
            if inline:
                spoken.append(inline)
            continue
        if non_narration_label.match(line):
            collecting = False
            continue

        if has_dialogue_labels:
            if collecting and line and not line.startswith("#") and not re.fullmatch(r"[-─—]{3,}", line):
                spoken.append(line)
            continue

        if not line or line.startswith("#") or re.fullmatch(r"[-─—]{3,}", line):
            continue
        if re.match(r"^(?:주제|씬\s*\d+|scene\s*\d+)\s*[:：]", line, re.I):
            continue
        spoken.append(line)

    narration = re.sub(r"\s+", " ", " ".join(spoken)).strip()
    return sanitize_narration(narration)


def sanitize_narration(text: str) -> str:
    """Remove image-prompt residue before it can reach TTS or subtitles."""
    if not text:
        return ""
    text = PROMPT_LABEL_RE.sub("", text)
    text = PROMPT_ARTIFACT_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s*[,;/|]\s*(?=$|[,.!?])", "", text)
    return text.strip(" \t\r\n,;|-")


def enrich_scene_plan(scene: dict[str, Any], index: int, total: int) -> dict[str, Any]:
    """Attach a renderable visual plan without changing the public scene contract."""
    result = dict(scene)
    section = str(result.get("section") or "scenario").lower()
    visual_type, objective = SECTION_VISUALS.get(
        section, SECTION_VISUALS["scenario"]
    )
    narration = sanitize_narration(result.get("content") or result.get("text") or "")
    result["content"] = narration
    result["text"] = narration
    result["visual_type"] = result.get("visual_type") or visual_type
    result["visual_plan"] = {
        "objective": objective,
        "visual_type": result["visual_type"],
        "character_required": result["visual_type"] in {
            "character_hero", "character_explainer", "takeaway"
        },
        "overlay_type": "fact_card" if result["visual_type"] == "data_visual" else None,
        "no_generated_text": True,
        "source_scene_index": index,
        "source_scene_count": total,
    }
    return result


def enrich_scene_plans(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_scene_plan(scene, i, len(scenes)) for i, scene in enumerate(scenes)]


def build_image_prompt(scene: dict[str, Any], base_prompt: str) -> str:
    """Make the generated image serve the narration and avoid fake AI text."""
    plan = scene.get("visual_plan") or {}
    visual_type = scene.get("visual_type") or plan.get("visual_type") or "character_explainer"
    instructions = {
        "character_hero": "single fixed mascot hero, expressive pose, premium Korean finance channel key art",
        "news_context": "business-news context with relevant objects, documentary editorial composition",
        "data_visual": "clean financial data visualization, chart shapes, icons and empty panels only",
        "character_explainer": "fixed mascot explains the specific financial cause and effect with meaningful props",
        "comparison": "clear left-versus-right comparison composition with contrasting financial outcomes",
        "takeaway": "fixed mascot in a calm credible conclusion scene with one relevant takeaway prop",
    }.get(visual_type, "specific editorial finance illustration")
    prompt = (base_prompt or scene.get("prompt_ko") or scene.get("content") or "").strip()
    return (
        f"{prompt}. Visual role: {instructions}. "
        "The image must directly depict the narration, not a generic coin or gold scene. "
        "No readable letters, no words, no numbers, no captions, no watermark, no logo. "
        "Keep safe negative space at the bottom for separately rendered Korean subtitles."
    )


def assess_scene_plan(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    visual_types = [str(s.get("visual_type") or "") for s in scenes]
    if len(scenes) >= 4 and len(set(visual_types)) < 3:
        warnings.append("low_visual_type_diversity")
    empty_narration = [i for i, s in enumerate(scenes) if not (s.get("content") or s.get("text"))]
    if empty_narration:
        warnings.append(f"empty_scene_narration:{','.join(map(str, empty_narration))}")
    artifacts = [i for i, s in enumerate(scenes) if PROMPT_ARTIFACT_RE.search(str(s.get("content") or s.get("text") or ""))]
    if artifacts:
        warnings.append(f"prompt_artifact_in_narration:{','.join(map(str, artifacts))}")
    score = max(0, 100 - 20 * len(warnings))
    return {"score": score, "warnings": warnings, "scene_count": len(scenes), "visual_types": visual_types}


def assess_subtitles(chunks: list[dict[str, Any]], audio_duration: float, max_chars: int) -> dict[str, Any]:
    warnings: list[str] = []
    if not chunks:
        return {"score": 0, "warnings": ["missing_subtitles"], "cue_count": 0, "coverage": 0.0}
    last_end = 0.0
    long_cues = 0
    large_gaps = 0
    bad_durations = 0
    for chunk in chunks:
        start = float(chunk.get("start", 0.0) or 0.0)
        duration = float(chunk.get("duration", 0.0) or 0.0)
        end = start + duration
        text = str(chunk.get("text", "")).strip()
        if len(re.sub(r"\s+", "", text)) > max_chars * 2:
            long_cues += 1
        if duration < 0.45 or duration > 3.5:
            bad_durations += 1
        if start - last_end > 0.5:
            large_gaps += 1
        last_end = max(last_end, end)
    coverage = min(1.0, last_end / audio_duration) if audio_duration else 0.0
    if coverage < 0.985:
        warnings.append(f"subtitle_coverage:{coverage:.3f}")
    if long_cues:
        warnings.append(f"long_subtitle_cues:{long_cues}")
    if large_gaps:
        warnings.append(f"subtitle_gaps_over_500ms:{large_gaps}")
    if bad_durations:
        warnings.append(f"subtitle_duration_outliers:{bad_durations}")
    score = max(0, 100 - 20 * len(warnings))
    return {"score": score, "warnings": warnings, "cue_count": len(chunks), "coverage": round(coverage, 4)}


def _image_metrics(path: Path) -> dict[str, Any]:
    """Measure technical image quality without an extra paid vision-model call."""
    from PIL import Image, ImageStat

    with Image.open(path) as source:
        image = source.convert("RGB")
        width, height = image.size
        sample = image.copy()
        sample.thumbnail((160, 160))
        stat = ImageStat.Stat(sample)
        means = stat.mean
        deviations = stat.stddev
        luminance = sum(means) / 3
        contrast = sum(deviations) / 3

        pixels = list(sample.getdata())
        saturation = (sum(max(pixel) - min(pixel) for pixel in pixels) / len(pixels)) if pixels else 0
        mono = sample.convert("L").resize((16, 16))
        threshold = sum(mono.getdata()) / 256
        perceptual_hash = "".join("1" if value >= threshold else "0" for value in mono.getdata())

    warnings: list[str] = []
    aspect = width / height if height else 0
    if width < 960 or height < 540:
        warnings.append("low_resolution")
    if abs(aspect - (16 / 9)) > 0.08:
        warnings.append("unexpected_aspect_ratio")
    if contrast < 8:
        warnings.append("near_blank_image")
    if luminance < 10 or luminance > 246:
        warnings.append("extreme_brightness")
    if saturation < 7:
        warnings.append("very_low_color_variation")

    score = max(0, 100 - (25 * len(warnings)))
    return {
        "score": score,
        "warnings": warnings,
        "width": width,
        "height": height,
        "aspect_ratio": round(aspect, 4),
        "brightness": round(luminance, 1),
        "contrast": round(contrast, 1),
        "color_variation": round(saturation, 1),
        "perceptual_hash": perceptual_hash,
    }


def _hamming_distance(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right))


def assess_images(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    """Report technical defects and near-duplicates per scene for targeted review."""
    warnings: list[str] = []
    fingerprints: dict[str, list[int]] = {}
    scene_metrics: list[dict[str, Any]] = []
    hashes: list[tuple[int, str]] = []

    for i, scene in enumerate(scenes):
        scene_index = int(scene.get("index", i))
        path = Path(str(scene.get("image_path") or ""))
        metric: dict[str, Any] = {"index": scene_index}
        if not path.exists() or path.stat().st_size < 15_000:
            metric.update({"score": 0, "warnings": ["missing_or_small_image"]})
        else:
            try:
                metric.update(_image_metrics(path))
                with path.open("rb") as f:
                    fingerprint = hashlib.sha256(f.read(128_000)).hexdigest()
                fingerprints.setdefault(fingerprint, []).append(scene_index)
                hashes.append((scene_index, metric["perceptual_hash"]))
            except Exception as exc:
                metric.update({"score": 0, "warnings": [f"unreadable_image:{type(exc).__name__}"]})
        metric["retry_recommended"] = metric["score"] < 75
        scene_metrics.append(metric)

    duplicate_sets = [indices for indices in fingerprints.values() if len(indices) > 1]
    near_duplicates: list[tuple[int, int]] = []
    for offset, (left_index, left_hash) in enumerate(hashes):
        for right_index, right_hash in hashes[offset + 1:]:
            if _hamming_distance(left_hash, right_hash) <= 4:
                near_duplicates.append((left_index, right_index))
                for metric in scene_metrics:
                    if metric["index"] in (left_index, right_index):
                        metric["warnings"].append("near_duplicate_image")
                        metric["score"] = min(metric["score"], 70)
                        metric["retry_recommended"] = True

    if duplicate_sets:
        warnings.append("duplicate_images:" + ";".join(",".join(map(str, group)) for group in duplicate_sets))
    if near_duplicates:
        warnings.append("near_duplicate_images:" + ";".join(f"{left},{right}" for left, right in near_duplicates))
    failed = [metric["index"] for metric in scene_metrics if metric["retry_recommended"]]
    if failed:
        warnings.append("review_or_regenerate:" + ",".join(map(str, failed)))
    score = round(sum(metric["score"] for metric in scene_metrics) / len(scene_metrics)) if scene_metrics else 0
    return {
        "score": score,
        "warnings": warnings,
        "image_count": len(scenes),
        "scene_metrics": scene_metrics,
        "retry_recommended_indices": failed,
    }


def persist_quality_report(job_id: int, stage: str, report: dict[str, Any]) -> str:
    directory = Path(f"/app/data/jobs/{job_id}/quality")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stage}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return str(path)

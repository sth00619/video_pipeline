"""Durable Gemini Pro Image Batch API support for quality-first scene rendering."""
from __future__ import annotations

import base64
import json
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from app.utils.quality_gate import assess_images, persist_quality_report
from app.utils.art_direction import assess_art_diversity

logger = logging.getLogger(__name__)
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
MANIFEST_NAME = "gemini_pro_batch.json"


def _key() -> str:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return key


def _contents(prompt: str, character_paths: list[str] | None, character_required: bool) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"text": prompt}]
    reference_paths = [path for path in (character_paths or []) if path and Path(path).exists()][:2]
    if character_required and reference_paths:
        for character_path in reversed(reference_paths):
            raw = Path(character_path).read_bytes()
            mime = "image/png" if character_path.lower().endswith(".png") else "image/jpeg"
            parts.insert(0, {"inlineData": {"mimeType": mime, "data": base64.b64encode(raw).decode()}})
        parts[-1]["text"] = (
            "Use the supplied reference sheet(s) as one fixed channel mascot. Preserve its face, silhouette, "
            "palette and line language; do not add a second mascot.\n\n" + prompt
        )
    return [{"role": "user", "parts": parts}]


def submit(
    job_id: int,
    scenes: list[dict[str, Any]],
    character_paths: list[str] | None,
    completed_scenes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Submit queued Pro scenes and preserve any already-rendered direct scenes."""
    requests_payload = []
    manifest_scenes = []
    for scene in scenes:
        direction = scene.get("art_direction") or {}
        prompt = scene["prompt_en"]
        requests_payload.append({
            "request": {
                "contents": _contents(prompt, character_paths, bool(direction.get("character_required"))),
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {"aspectRatio": "16:9", "imageSize": "2K"},
                },
            },
            "metadata": {"key": f"scene-{scene['index']}"},
        })
        manifest_scenes.append(scene)

    payload = {"batch": {"displayName": f"video-pipeline-job-{job_id}-pro-2k", "inputConfig": {
        "requests": {"requests": requests_payload}
    }}}
    response = requests.post(
        f"{API_ROOT}/models/gemini-3-pro-image:batchGenerateContent",
        headers={"x-goog-api-key": _key(), "Content-Type": "application/json"},
        json=payload, timeout=90,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Gemini Pro Batch submission failed ({response.status_code}): {response.text[:500]}")
    body = response.json()
    metadata = body.get("metadata") or body
    batch_name = metadata.get("name") or body.get("name")
    if not batch_name:
        raise RuntimeError("Gemini Pro Batch response did not include a batch name")
    job_dir = Path(f"/app/data/jobs/{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "job_id": job_id,
        "batch_name": batch_name,
        "state": metadata.get("state", "BATCH_STATE_PENDING"),
        "scenes": manifest_scenes,
        "completed_scenes": completed_scenes or [],
    }
    (job_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return {"status": "BATCH_PENDING", "job_id": job_id, "batch_job_name": batch_name, "batch_state": manifest["state"], "scene_count": len(scenes), "gifs": [], "gif_count": 0, "scenes": []}


def _output_image(response: dict[str, Any]) -> bytes | None:
    for candidate in response.get("candidates") or []:
        for part in ((candidate.get("content") or {}).get("parts") or []):
            data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if data:
                return base64.b64decode(data)
    return None


def poll(job_id: int) -> dict[str, Any]:
    manifest_path = Path(f"/app/data/jobs/{job_id}") / MANIFEST_NAME
    if not manifest_path.exists():
        raise RuntimeError("Gemini Pro Batch manifest not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    response = requests.get(f"{API_ROOT}/{manifest['batch_name']}", headers={"x-goog-api-key": _key()}, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"Gemini Pro Batch status failed ({response.status_code}): {response.text[:500]}")
    body = response.json()
    metadata = body.get("metadata") or body
    state = metadata.get("state", "BATCH_STATE_PENDING")
    manifest["state"] = state
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    if state in {"BATCH_STATE_PENDING", "BATCH_STATE_RUNNING"}:
        return {"status": "BATCH_PENDING", "job_id": job_id, "batch_job_name": manifest["batch_name"], "batch_state": state, "scene_count": len(manifest["scenes"]), "gifs": [], "gif_count": 0, "scenes": []}
    if state != "BATCH_STATE_SUCCEEDED":
        return {"status": "BATCH_FAILED", "job_id": job_id, "batch_job_name": manifest["batch_name"], "batch_state": state, "error": str(metadata.get("error") or "Gemini Pro Batch failed"), "scene_count": 0, "gifs": [], "gif_count": 0, "scenes": []}

    inline = ((metadata.get("dest") or {}).get("inlinedResponses") or (metadata.get("dest") or {}).get("inlined_responses") or [])
    if len(inline) != len(manifest["scenes"]):
        raise RuntimeError(f"Gemini Pro Batch returned {len(inline)} responses for {len(manifest['scenes'])} scenes")
    image_dir = Path(f"/app/data/jobs/{job_id}/images")
    image_dir.mkdir(parents=True, exist_ok=True)
    completed = list(manifest.get("completed_scenes") or [])
    for scene, item in zip(manifest["scenes"], inline):
        output = item.get("response") or {}
        raw = _output_image(output)
        if not raw:
            raise RuntimeError(f"Gemini Pro Batch scene {scene['index']} returned no image: {item.get('error')}")
        path = image_dir / f"scene_{scene['index']:03d}.png"
        try:
            from PIL import Image
            Image.open(BytesIO(raw)).convert("RGB").save(path, "PNG")
        except Exception:
            path.write_bytes(raw)
        scene = dict(scene)
        scene.update({"image_path": str(path), "generation_method": "gemini_pro_batch_2k", "quality_score": 90, "batch_job_name": manifest["batch_name"]})
        raw_path = image_dir / f"scene_{scene['index']:03d}_raw.png"
        try:
            from app.postprocess.text_overlay import add_headline
            path.replace(raw_path)
            add_headline(str(raw_path), str(path), str(scene.get("headline") or ""), str(scene.get("headline_mood") or "neutral"))
        except Exception as exc:
            logger.warning("Batch headline overlay skipped for scene %s: %s", scene["index"], exc)
            if raw_path.exists() and not path.exists():
                raw_path.replace(path)
        completed.append(scene)
    completed.sort(key=lambda scene: scene.get("index", 0))
    manifest["state"] = "BATCH_STATE_SUCCEEDED"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    quality = assess_images(completed)
    metrics = {item["index"]: item for item in quality.get("scene_metrics", [])}
    for scene in completed:
        metric = metrics.get(scene["index"], {})
        scene["quality_score"] = metric.get("score", scene["quality_score"])
        scene["quality_flags"] = metric.get("warnings", [])
        scene["retry_recommended"] = metric.get("retry_recommended", False)
    quality["art_direction"] = assess_art_diversity(completed)
    persist_quality_report(job_id, "images", quality)
    return {"status": "BATCH_COMPLETE", "job_id": job_id, "batch_job_name": manifest["batch_name"], "batch_state": state, "scene_count": len(completed), "gifs": [], "gif_count": 0, "scenes": completed, "quality_report": {"images": quality}}

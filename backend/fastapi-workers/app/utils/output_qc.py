"""Deterministic final-output contract checks for long-form delivery."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _ffprobe(path: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        return {"error": completed.stderr.strip()}
    try:
        return json.loads(completed.stdout)
    except (ValueError, TypeError):
        return {"error": "invalid_ffprobe_json"}


def _leading_silence_seconds(audio_path: str) -> float:
    completed = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", audio_path, "-t", "0.35",
            "-af", "silencedetect=n=-45dB:d=0.10", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    match = re.search(r"silence_end:\s*([0-9.]+)", completed.stderr)
    return float(match.group(1)) if match else 0.0


def _frame_signature(video_path: str, position: float) -> bytes:
    completed = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(position),
            "-i", video_path, "-frames:v", "1", "-vf", "scale=96:54,format=gray",
            "-f", "rawvideo", "-",
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else b""


def _intro_frame_difference(video_path: str) -> float:
    first = _frame_signature(video_path, 0.05)
    later = _frame_signature(video_path, 1.50)
    if not first or len(first) != len(later):
        return 0.0
    return round(sum(abs(left - right) for left, right in zip(first, later)) / (len(first) * 255), 5)


def build_output_qc_report(
    *,
    job_id: int,
    output_path: str,
    audio_path: str,
    tts_meta: dict[str, Any],
    scenes: list[dict[str, Any]],
    expected_data_cards: int,
    rendered_data_cards: int,
    expected_market_charts: int,
    rendered_market_charts: int,
    planned_kling: int,
    actual_kling: int,
    fal_failures: dict[int, str],
) -> dict[str, Any]:
    probe = _ffprobe(output_path)
    video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), {})
    job_dir = Path(f"/app/data/jobs/{job_id}")
    bg_files = sorted(str(path) for path in job_dir.rglob("*_bg.png")) if job_dir.exists() else []
    request_meta = tts_meta.get("provider_request") or {}
    chunks = tts_meta.get("chunks") if isinstance(tts_meta.get("chunks"), list) else []
    first_chunk_text = ""
    if chunks and isinstance(chunks[0], dict):
        first_chunk_text = str(chunks[0].get("text") or "").strip()
    first_sentence = request_meta.get("first_sentence") or first_chunk_text
    request_provenance = "provider_request" if request_meta else "persisted_tts_chunks"
    leading = _leading_silence_seconds(audio_path) if Path(audio_path).exists() else 0.0
    frame_difference = _intro_frame_difference(output_path)
    styles = sorted({str(scene.get("style_profile")) for scene in scenes if scene.get("style_profile")})

    checks = {
        "verified_overlays": {
            "passed": expected_data_cards == rendered_data_cards
            and expected_market_charts == rendered_market_charts,
            "data_cards": {"expected": expected_data_cards, "rendered": rendered_data_cards},
            "market_charts": {"expected": expected_market_charts, "rendered": rendered_market_charts},
        },
        "fal_delivery": {
            "passed": actual_kling >= (0 if planned_kling == 0 else max(1, (planned_kling * 3 + 3) // 4)),
            "planned": planned_kling,
            "actual": actual_kling,
            "failures": fal_failures,
        },
        "tts_opening": {
            "passed": bool(first_sentence) and bool(tts_meta.get("voice_id")) and leading >= 0.15,
            "first_sentence_sent": first_sentence,
            "voice_id": tts_meta.get("voice_id"),
            "model_id": request_meta.get("model_id") or tts_meta.get("model_id"),
            "mode": request_meta.get("mode") or tts_meta.get("mode"),
            "has_audio_tag": request_meta.get("has_audio_tag", tts_meta.get("has_audio_tag")),
            "metadata_provenance": request_provenance,
            "measured_leading_silence_seconds": round(leading, 3),
        },
        "integrated_generation": {
            "passed": not bg_files,
            "legacy_bg_files": bg_files,
        },
        "style_contract": {
            "passed": len(styles) <= 1,
            "style_profiles": styles,
        },
        "media_contract": {
            "passed": video.get("width") == 1920
            and video.get("height") == 1080
            and video.get("avg_frame_rate") == "30/1"
            and str(audio.get("sample_rate")) == "44100"
            and int(audio.get("channels") or 0) == 2,
            "width": video.get("width"),
            "height": video.get("height"),
            "frame_rate": video.get("avg_frame_rate"),
            "audio_sample_rate": audio.get("sample_rate"),
            "audio_channels": audio.get("channels"),
        },
        "intro_motion_frame_diff": {
            "passed": planned_kling == 0 or frame_difference >= 0.002,
            "normalized_difference": frame_difference,
        },
    }
    passed_count = sum(bool(check.get("passed")) for check in checks.values())
    return {
        "passed": passed_count == len(checks),
        "score": round(100 * passed_count / len(checks)),
        "checks": checks,
    }

"""One length contract shared by script generation and ElevenLabs TTS.

The product measures Korean narration in *spoken* characters (spaces and
editorial markup excluded).  Visual prompts, section headings and subtitle
splits must never change the requested video duration.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


CALIBRATION_PATH = Path(os.getenv("TTS_CPS_CALIBRATION_PATH", "/app/data/tts_cps_calibration.json"))
TOLERANCE = 0.08


def spoken_char_count(text: str) -> int:
    """Count only characters that are actually narrated by the voice."""
    return len(re.sub(r"\s+", "", text or ""))


def _key(voice_id: str | None, model_id: str | None, speed: float) -> str:
    return f"{voice_id or 'default'}|{model_id or 'default'}|{float(speed):.2f}"


def _read_calibrations() -> dict[str, Any]:
    try:
        with CALIBRATION_PATH.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_calibrations(value: dict[str, Any]) -> None:
    try:
        CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=CALIBRATION_PATH.parent) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(CALIBRATION_PATH)
    except OSError:
        # Calibration improves future estimates, but must never fail a job.
        return


def resolve_cpm(default_cpm: float, voice_id: str | None, model_id: str | None, speed: float) -> tuple[float, int]:
    """Return a calibrated CPM when at least two comparable samples exist."""
    row = _read_calibrations().get(_key(voice_id, model_id, speed), {})
    samples = int(row.get("samples", 0) or 0)
    measured = float(row.get("cpm", 0) or 0)
    if samples >= 2 and measured > 0:
        return measured, samples
    return float(default_cpm), samples


def make_length_contract(
    target_minutes: int,
    base_cpm: float,
    speed: float,
    voice_id: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Calculate an explicit target before prose is generated.

    CPM is the normal-speed rate.  A 1.05x requested voice therefore fits 5%
    more spoken characters into the same requested duration.
    """
    safe_minutes = max(1, int(target_minutes or 1))
    safe_speed = max(0.5, min(float(speed or 1.0), 1.5))
    calibrated_cpm, samples = resolve_cpm(base_cpm, voice_id, model_id, safe_speed)
    effective_cpm = calibrated_cpm * safe_speed
    # Avoid banker's rounding: a half-character budget should round up so the
    # displayed target is intuitive to operators.
    target_chars = int(safe_minutes * effective_cpm + 0.5)
    return {
        "target_seconds": safe_minutes * 60,
        "base_cpm": round(calibrated_cpm, 2),
        "effective_cpm": round(effective_cpm, 2),
        "tts_speed": safe_speed,
        "target_chars": target_chars,
        "min_chars": round(target_chars * (1 - TOLERANCE)),
        "max_chars": round(target_chars * (1 + TOLERANCE)),
        "tolerance_pct": round(TOLERANCE * 100),
        "calibration_samples": samples,
        "voice_id": voice_id or "default",
        "model_id": model_id or "default",
    }


def update_calibration(
    narration: str,
    actual_duration_seconds: float,
    voice_id: str | None,
    model_id: str | None,
    speed: float,
) -> dict[str, Any] | None:
    """Store a bounded moving average from completed ElevenLabs audio."""
    spoken = spoken_char_count(narration)
    if spoken < 40 or actual_duration_seconds <= 0:
        return None
    observed_cpm = spoken / actual_duration_seconds * 60
    if not 80 <= observed_cpm <= 900:
        return None
    data = _read_calibrations()
    key = _key(voice_id, model_id, speed)
    existing = data.get(key, {})
    samples = int(existing.get("samples", 0) or 0)
    previous = float(existing.get("cpm", observed_cpm) or observed_cpm)
    # Preserve 80% history and add one bounded observation.  This avoids a
    # single unusually pause-heavy narration changing every future job.
    cpm = observed_cpm if samples == 0 else previous * 0.8 + observed_cpm * 0.2
    data[key] = {"cpm": round(cpm, 2), "samples": samples + 1}
    _write_calibrations(data)
    return {"observed_cpm": round(observed_cpm, 2), "calibrated_cpm": round(cpm, 2), "samples": samples + 1}

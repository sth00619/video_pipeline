"""Redis-backed per-job lock preventing duplicate image fan-out."""
from __future__ import annotations

import secrets

from app.utils.process_manager import _get_redis

LOCK_TTL_SECONDS = 60 * 60


class ImageJobAlreadyRunningError(RuntimeError):
    pass


def acquire_image_job_lock(job_id: int) -> str:
    client = _get_redis()
    if client is None:
        raise RuntimeError("Redis is unavailable; image generation is locked to prevent duplicate execution")

    key = f"job:{int(job_id)}:images:lock"
    token = secrets.token_urlsafe(24)
    if not client.set(key, token, nx=True, ex=LOCK_TTL_SECONDS):
        raise ImageJobAlreadyRunningError(f"Image generation is already running for job {job_id}")
    return token


def release_image_job_lock(job_id: int, token: str) -> None:
    client = _get_redis()
    if client is None:
        return
    key = f"job:{int(job_id)}:images:lock"
    # Do not delete a later run's lock if this run exceeded its TTL.
    try:
        if client.get(key) == token:
            client.delete(key)
    except Exception:
        # TTL remains as a final safeguard; never mask the original job error.
        pass

"""Read Fal account credit status before scheduling optional Kling motion.

Gemini Pro owns scene-image generation. Fal is used only to animate completed
Pro images when the account billing API reports usable credit.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


def get_fal_credit_status() -> dict[str, Any]:
    key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
    base = {
        "configured": bool(key),
        "available": False,
        "balance": None,
        "currency": None,
        "reason": "fal_key_missing" if not key else "unknown",
    }
    if not key:
        return base
    try:
        response = requests.get(
            "https://api.fal.ai/v1/account/billing",
            params={"expand": "credits"},
            headers={"Authorization": f"Key {key}"},
            timeout=15,
        )
        if response.status_code != 200:
            logger.warning("Fal billing check unavailable: HTTP %s", response.status_code)
            return {**base, "reason": f"billing_http_{response.status_code}"}
        credits = response.json().get("credits") or {}
        balance = float(credits.get("current_balance") or 0)
        return {
            **base,
            "available": balance > 0,
            "balance": balance,
            "currency": credits.get("currency") or "USD",
            "reason": "credit_available" if balance > 0 else "credit_empty",
        }
    except Exception as exc:
        logger.warning("Fal billing check failed: %s", exc)
        return {**base, "reason": "billing_check_failed"}

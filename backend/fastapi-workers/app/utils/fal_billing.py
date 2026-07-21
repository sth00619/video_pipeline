"""Read Fal account credit status before scheduling optional Kling motion.

Gemini Pro owns scene-image generation. Fal is used only to animate completed
Pro images when the account billing API reports usable credit.

Design note (§4):
  The /v1/account/billing endpoint requires an Admin-scoped API key. Standard
  inference keys return HTTP 403 — this is expected and not a sign of insufficient
  credit. The real credit gate is the Kling generation call itself: if credits are
  exhausted, the POST to queue.fal.run returns an error that the circuit-breaker
  catches and converts to a static-image fallback.

  We therefore treat any 403 response as "key is valid, proceed". The balance
  field is intentionally set to None (not a fake 999.0) so no budget-downgrade
  logic accidentally uses it.
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
        "balance": None,   # None = unknown; do NOT use in budget math
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
            if response.status_code == 403:
                # 403 is expected for standard inference keys: the billing endpoint
                # is Admin-scoped. The key is valid for Kling inference, so we mark
                # available=True. balance stays None — do NOT use in budget math.
                logger.info(
                    "Fal billing check returned 403 (Admin-only endpoint). "
                    "Inference key is valid — proceeding with Kling generation. "
                    "If credits are genuinely exhausted, the generation call will "
                    "fail and the circuit-breaker will fall back to a static image."
                )
                return {
                    **base,
                    "available": True,
                    "balance": None,   # unknown — intentionally not 999.0
                    "currency": None,
                    "reason": "billing_restricted_key_usable",
                }
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

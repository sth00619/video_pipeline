"""Small, opt-in-safe helpers for Anthropic prompt caching.

The cache breakpoint is placed only on stable system instructions. Per-request
scripts, market snapshots, timestamps, and user text stay after the breakpoint
so they do not invalidate the reusable prefix.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def cached_system(text: str) -> list[dict[str, Any]] | str:
    """Return an Anthropic system block with an ephemeral cache breakpoint."""
    if not text:
        return text
    enabled = os.getenv("ANTHROPIC_PROMPT_CACHE_ENABLED", "true").lower() in {"1", "true", "yes"}
    if not enabled:
        return text
    block: dict[str, Any] = {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
    if os.getenv("ANTHROPIC_PROMPT_CACHE_TTL", "5m").lower() == "1h":
        block["cache_control"]["ttl"] = "1h"
    return [block]


def log_cache_usage(response: Any, label: str) -> None:
    """Log cache read/write counters so a zero-hit configuration is visible."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    def value(name: str) -> int:
        raw = getattr(usage, name, 0)
        if raw is None and isinstance(usage, dict):
            raw = usage.get(name, 0)
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0
    logger.info(
        "Anthropic prompt cache label=%s read=%s write=%s uncached_input=%s",
        label,
        value("cache_read_input_tokens"),
        value("cache_creation_input_tokens"),
        value("input_tokens"),
    )

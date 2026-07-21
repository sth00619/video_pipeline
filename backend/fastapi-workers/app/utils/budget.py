"""Per-video cost preflight and durable local ledger.

The ledger records configured billable calls, not secrets or provider keys.
It deliberately estimates conservatively with a retry buffer before a job
starts, then records successful calls as it runs.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import runtime_config

_LOCK = threading.Lock()


def _krw(usd: float, rate: float) -> int:
    return round(usd * rate)


def _estimate(scene_count: int, pro_count: int, kling_count: int, cfg: dict[str, Any]) -> int:
    flash_count = max(0, scene_count - pro_count)
    usd = (
        flash_count * float(cfg["img_cost_flash_1k_usd"])
        + pro_count * float(cfg["img_cost_pro_2k_usd"])
        + kling_count * float(cfg["kling_cost_per_clip_usd"])
    )
    return round(_krw(usd, float(cfg["usd_krw"])) * (1 + float(cfg["budget_retry_buffer_pct"]) / 100))


def plan_preflight(scene_count: int, quality_tier: str, requested_pro: int, requested_kling: int) -> dict[str, Any]:
    """Plan a complete video below the ceiling, degrading expensive tiers first."""
    cfg = runtime_config.get()
    max_budget = int(cfg["max_budget_per_video_krw"])
    pro_count = scene_count if quality_tier == "pro" else (0 if quality_tier == "flash" else min(scene_count, max(0, requested_pro)))
    pro_count += 1  # [TASK 5] 썸네일 1장은 항상 Pro 2K로 고정 렌더링되므로 예산 견적에 +1 반영
    kling_count = max(0, requested_kling)
    actions: list[str] = []
    estimated = _estimate(scene_count, pro_count, kling_count, cfg)

    # Upgrade quality is optional. Calculate the highest number of Pro scenes
    # affordable while preserving Flash coverage for every scene and the intro.
    if estimated > max_budget and pro_count:
        baseline = _estimate(scene_count, 0, kling_count, cfg)
        unit_delta = _krw(float(cfg["img_cost_pro_2k_usd"]) - float(cfg["img_cost_flash_1k_usd"]), float(cfg["usd_krw"]))
        buffered_delta = max(1, round(unit_delta * (1 + float(cfg["budget_retry_buffer_pct"]) / 100)))
        affordable_pro = max(0, min(pro_count, (max_budget - baseline) // buffered_delta))
        if affordable_pro < pro_count:
            actions.append(f"pro_scenes:{pro_count}->{affordable_pro}")
            pro_count = affordable_pro
            estimated = _estimate(scene_count, pro_count, kling_count, cfg)

    # Motion is optional as well. Never reduce below three when it was
    # requested; below that, deterministic static-image rendering remains the
    # completion-safe fallback.
    if estimated > max_budget and kling_count:
        minimum = min(3, kling_count)
        while kling_count > minimum and estimated > max_budget:
            kling_count -= 1
            estimated = _estimate(scene_count, pro_count, kling_count, cfg)
        if kling_count != requested_kling:
            actions.append(f"kling_clips:{requested_kling}->{kling_count}")

    allowed = estimated <= max_budget
    return {
        "planned_at": datetime.now(timezone.utc).isoformat(), "scene_count": scene_count,
        "quality_tier": quality_tier, "pro_scene_count": pro_count, "flash_scene_count": max(0, scene_count - pro_count),
        "kling_clip_count": kling_count, "estimated_cost_krw": estimated, "budget_limit_krw": max_budget,
        "retry_buffer_pct": float(cfg["budget_retry_buffer_pct"]), "allowed": allowed,
        "actions": actions, "reason": None if allowed else "minimum_complete_plan_exceeds_budget",
        "rates": {key: cfg[key] for key in ("img_cost_flash_1k_usd", "img_cost_pro_2k_usd", "kling_cost_per_clip_usd", "usd_krw")},
    }


def _job_path(job_id: int, name: str) -> Path:
    path = Path(f"/app/data/jobs/{job_id}")
    path.mkdir(parents=True, exist_ok=True)
    return path / name


def write_preflight(job_id: int, plan: dict[str, Any]) -> None:
    path = _job_path(job_id, "budget_preflight.json")
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(staged, path)


def load_preflight(job_id: int) -> dict[str, Any] | None:
    try:
        return json.loads(_job_path(job_id, "budget_preflight.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def record_cost(job_id: int, kind: str, count: int = 1) -> dict[str, Any]:
    """Record successful external requests. Overrun warns but does not abandon a video."""
    rates = runtime_config.get()
    unit_usd = {
        "flash": float(rates["img_cost_flash_1k_usd"]), "pro": float(rates["img_cost_pro_2k_usd"]),
        "kling": float(rates["kling_cost_per_clip_usd"]),
    }.get(kind, 0.0)
    amount = _krw(unit_usd * count, float(rates["usd_krw"]))
    path = _job_path(job_id, "cost_ledger.json")
    with _LOCK:
        try: ledger = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError): ledger = {"items": [], "total_krw": 0}
        ledger["items"].append({"kind": kind, "count": count, "amount_krw": amount, "at": datetime.now(timezone.utc).isoformat()})
        ledger["total_krw"] = int(ledger.get("total_krw", 0)) + amount
        limit = int(rates["max_budget_per_video_krw"])
        ledger["budget_overrun_krw"] = max(0, ledger["total_krw"] - limit)
        staged = path.with_suffix(".tmp"); staged.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"); os.replace(staged, path)
    return ledger

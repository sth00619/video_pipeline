"""Per-video cost preflight and durable local ledger.

The ledger records configured billable calls, not secrets or provider keys.
It deliberately estimates conservatively with a retry buffer before a job
starts, then records successful calls as it runs.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import runtime_config

_LOCK = threading.Lock()

_GEMINI_IMAGE_RATE_KEYS = {
    "gemini-3-pro-image": "img_cost_pro_2k_usd",
    "gemini-3.1-flash-image": "img_cost_flash_2k_usd",
}


class ProviderRequestBudgetExceeded(RuntimeError):
    """외부 이미지 요청 한 건을 예약할 수 없을 때 발생한다."""


class ProviderRequestAudit:
    """Gemini HTTP 시도 단위의 영속 예산 게이트와 감사 원장.

    공급자 재시도는 이미지 한 장의 부수 작업이 아니라 별도 과금 가능성이 있는
    외부 요청이다. 따라서 ``before_attempt``는 POST 직전에 비용을 점유하고
    디스크에 기록한다. 프로세스가 응답 대기 중 종료돼도 예약 기록은 남는다.
    """

    def __init__(
        self,
        *,
        path: Path,
        scene_key: str,
        provider: str,
        model: str,
        request_kind: str,
        unit_usd: float,
        usd_krw: float,
        budget_limit_krw: int,
        request_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._path = path
        self._scene_key = scene_key
        self._provider = provider
        self._model = model
        self._request_kind = request_kind
        self._unit_usd = float(unit_usd)
        self._usd_krw = float(usd_krw)
        self._budget_limit_krw = int(budget_limit_krw)
        self._request_metadata = dict(request_metadata or {})

    @classmethod
    def for_job(cls, *, job_id: int, scene_key: str, model: str) -> "ProviderRequestAudit":
        """V4 공용 비용 원장에 Gemini 시도를 기록한다."""
        rate_key = _GEMINI_IMAGE_RATE_KEYS.get(model)
        if rate_key is None:
            raise ValueError(f"지원하지 않는 Gemini 이미지 생성 모델입니다: {model}")
        rates = runtime_config.get()
        preflight = load_preflight(job_id) or {}
        return cls(
            path=_job_path(job_id, "cost_ledger.json"),
            scene_key=scene_key,
            provider="gemini",
            model=model,
            request_kind=(
                "gemini_pro_request"
                if model == "gemini-3-pro-image"
                else "gemini_flash_image_request"
            ),
            unit_usd=float(rates[rate_key]),
            usd_krw=float(rates["usd_krw"]),
            budget_limit_krw=int(preflight.get("budget_limit_krw") or rates["max_budget_per_video_krw"]),
            request_metadata={"policy_version": preflight.get("policy_version", "runtime-default")},
        )

    @classmethod
    def for_path(
        cls,
        *,
        path: Path,
        scene_key: str,
        model: str,
        unit_usd: float,
        usd_krw: float,
        budget_limit_krw: int,
        request_metadata: dict[str, Any] | None = None,
    ) -> "ProviderRequestAudit":
        """V5처럼 작업 디렉터리가 다른 실행에도 같은 게이트를 사용한다."""
        if model not in _GEMINI_IMAGE_RATE_KEYS:
            raise ValueError(f"지원하지 않는 Gemini 이미지 생성 모델입니다: {model}")
        return cls(
            path=path,
            scene_key=scene_key,
            provider="gemini",
            model=model,
            request_kind=(
                "gemini_pro_request"
                if model == "gemini-3-pro-image"
                else "gemini_flash_image_request"
            ),
            unit_usd=unit_usd,
            usd_krw=usd_krw,
            budget_limit_krw=budget_limit_krw,
            request_metadata=request_metadata,
        )

    @classmethod
    def for_kling(cls, *, job_id: int, scene_key: str) -> "ProviderRequestAudit":
        """Kling image-to-video 요청도 네트워크 호출 전에 비용을 예약한다."""
        rates = runtime_config.get()
        preflight = load_preflight(job_id) or {}
        return cls(
            path=_job_path(job_id, "cost_ledger.json"),
            scene_key=scene_key,
            provider="fal",
            model="kling_image_to_video",
            request_kind="kling_request",
            unit_usd=float(rates["kling_cost_per_clip_usd"]),
            usd_krw=float(rates["usd_krw"]),
            budget_limit_krw=int(preflight.get("budget_limit_krw") or rates["max_budget_per_video_krw"]),
            request_metadata={"policy_version": preflight.get("policy_version", "runtime-default")},
        )

    def before_attempt(self, *, attempt: int, model: str | None = None) -> str:
        """POST 직전에 예약을 영속화하고, 초과 시 네트워크 호출을 막는다."""
        amount_krw = _krw(self._unit_usd, self._usd_krw)
        token = uuid.uuid4().hex
        with _LOCK:
            ledger = _load_ledger(self._path)
            projected = int(ledger.get("total_krw", 0)) + amount_krw
            if projected > self._budget_limit_krw:
                raise ProviderRequestBudgetExceeded(
                    f"이미지 요청 예산 초과: 예약 {amount_krw}원, "
                    f"누적 예정 {projected}원, 상한 {self._budget_limit_krw}원"
                )
            item = {
                "kind": self._request_kind,
                "provider": self._provider,
                "model": model or self._model,
                "scene_key": self._scene_key,
                "attempt": int(attempt),
                "attempt_id": token,
                "estimated_usd": self._unit_usd,
                "amount_krw": amount_krw,
                "cost_status": "unverified_until_console_reconciliation",
                "status": "reserved",
                "reserved_at": datetime.now(timezone.utc).isoformat(),
            }
            if self._request_metadata:
                item["request_metadata"] = self._request_metadata
            ledger["items"].append(item)
            ledger["total_krw"] = projected
            ledger["budget_overrun_krw"] = max(0, projected - self._budget_limit_krw)
            _write_ledger(self._path, ledger)
        return token

    def after_attempt(
        self,
        token: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        outcome: str,
    ) -> None:
        """응답 결과를 기록한다. 실패한 시도는 비용을 0원으로 감액하고 총액을 재계산한다."""
        with _LOCK:
            ledger = _load_ledger(self._path)
            for item in reversed(ledger["items"]):
                if item.get("attempt_id") != token:
                    continue
                item["status"] = outcome
                item["completed_at"] = datetime.now(timezone.utc).isoformat()
                if status_code is not None:
                    item["status_code"] = int(status_code)
                if request_id:
                    item["request_id"] = str(request_id)[:256]

                # 실패한 시도(network_error, http_500, failed 등)는 과금액을 0원으로 처리하여 이중 청구 방지
                is_success = outcome in ("http_200", "succeeded", "http_201") or (status_code is not None and 200 <= status_code < 300)
                if not is_success:
                    item["amount_krw"] = 0
                    item["cost_status"] = "cancelled_due_to_failure"
                break

            # 성공(http_200) 또는 아직 진행 중(reserved)인 요청의 amount_krw만 합산하여 total_krw 재계산
            recalculated_total = sum(
                int(i.get("amount_krw", 0))
                for i in ledger.get("items", [])
                if isinstance(i, dict) and i.get("status") in ("reserved", "http_200", "succeeded", "http_201")
            )
            ledger["total_krw"] = recalculated_total
            limit = self._budget_limit_krw
            ledger["budget_overrun_krw"] = max(0, recalculated_total - limit)
            _write_ledger(self._path, ledger)

    def summary(self) -> dict[str, Any]:
        with _LOCK:
            ledger = _load_ledger(self._path)
            entries = [
                item for item in ledger["items"]
                if item.get("provider") == self._provider and item.get("scene_key") == self._scene_key
            ]
        return {"attempt_count": len(entries), "entries": entries}


def _krw(usd: float, rate: float) -> int:
    return round(usd * rate)


def _estimate(pro_count: int, kling_count: int, cfg: dict[str, Any]) -> int:
    usd = (
        pro_count * float(cfg["img_cost_pro_2k_usd"])
        + kling_count * float(cfg["kling_cost_per_clip_usd"])
    )
    return round(_krw(usd, float(cfg["usd_krw"])) * (1 + float(cfg["budget_retry_buffer_pct"]) / 100))


def plan_preflight(
    scene_count: int,
    quality_tier: str,
    requested_pro: int,
    requested_kling: int,
    *,
    template_scene_count: int = 0,
    include_thumbnail: bool = True,
    budget_limit_krw: int | None = None,
    policy_version: str | None = None,
) -> dict[str, Any]:
    """모든 Pro 요청을 사전 예약 가능한지 확인하고 초과 시 즉시 거절한다."""
    if str(quality_tier or "pro").lower() != "pro":
        raise ValueError("이미지 품질 tier는 pro만 허용합니다.")
    cfg = runtime_config.get()
    configured_max = int(cfg["max_budget_per_video_krw"])
    max_budget = configured_max if budget_limit_krw is None else int(budget_limit_krw)
    if max_budget <= 0 or max_budget > configured_max:
        raise ValueError(f"작업별 예산 상한은 1~{configured_max}원 범위여야 합니다.")
    pro_count = max(0, scene_count)
    pro_count += 1  # [TASK 5] 썸네일 1장은 항상 Pro 2K로 고정 렌더링되므로 예산 견적에 +1 반영
    if not include_thumbnail:
        pro_count -= 1
    kling_count = max(0, requested_kling)
    estimated = _estimate(pro_count, kling_count, cfg)

    # 템플릿 장면은 보드 검출 실패 시 한 번만 재생성할 수 있으므로,
    # 해당 장면 tier 비용의 25%를 사전 예비비로 잡는다.
    retry_unit = float(cfg["img_cost_pro_2k_usd"])
    template_retry_reserve = round(_krw(template_scene_count * retry_unit * .25, float(cfg["usd_krw"])))
    estimated_with_reserve = estimated + template_retry_reserve
    allowed = estimated_with_reserve <= max_budget
    regen_enabled = allowed
    return {
        "planned_at": datetime.now(timezone.utc).isoformat(), "scene_count": scene_count,
        "quality_tier": "pro", "pro_scene_count": pro_count, "flash_scene_count": 0,
        "kling_clip_count": kling_count, "estimated_cost_krw": estimated_with_reserve, "budget_limit_krw": max_budget,
        "retry_buffer_pct": float(cfg["budget_retry_buffer_pct"]), "allowed": allowed,
        "policy_version": str(policy_version or "runtime-default"),
        "actions": [], "reason": None if allowed else "pro_only_plan_exceeds_budget",
        "template_scene_count": template_scene_count, "template_retry_reserve_krw": template_retry_reserve,
        "template_regeneration_enabled": regen_enabled,
        "rates": {key: cfg[key] for key in ("img_cost_pro_2k_usd", "kling_cost_per_clip_usd", "usd_krw")},
    }


def _job_path(job_id: int, name: str) -> Path:
    path = Path(f"/app/data/jobs/{job_id}")
    path.mkdir(parents=True, exist_ok=True)
    return path / name


def _load_ledger(path: Path) -> dict[str, Any]:
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        ledger = {"items": [], "total_krw": 0}
    if not isinstance(ledger.get("items"), list):
        ledger["items"] = []
    ledger["total_krw"] = int(ledger.get("total_krw", 0))
    return ledger


def _write_ledger(path: Path, ledger: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(staged, path)


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


def load_cost_ledger_summary(job_id: int) -> dict[str, Any]:
    """Spring/UI가 읽을 수 있는 작업별 비용 원장 스냅샷을 반환한다.

    이미지·Kling처럼 FastAPI가 실제 provider 요청을 보낸 비용의 기준값은 이
    파일이다. 성공했거나 진행 중인 예약 상태만 합계에 포함한다.
    """
    cfg = runtime_config.get()
    path = _job_path(job_id, "cost_ledger.json")
    with _LOCK:
        ledger = _load_ledger(path)
        items = [dict(item) for item in ledger["items"] if isinstance(item, dict)]
    
    # 실패/취소된 시도를 제외하고 실제 유효한 과금액만 합산
    total = sum(
        int(item.get("amount_krw", 0))
        for item in items
        if item.get("status") in ("reserved", "http_200", "succeeded", "http_201")
    )
    limit = int(cfg["max_budget_per_video_krw"])
    return {
        "job_id": int(job_id),
        "currency": "KRW",
        "total_krw": total,
        "budget_limit_krw": limit,
        "remaining_krw": max(0, limit - total),
        "budget_overrun_krw": max(0, total - limit),
        "items": list(reversed(items[-100:])),
    }


def can_charge_overlay_vision(job_id: int, scene_key: str) -> bool:
    """Reserve vision fallback for at most one attempt per data scene.

    The detector is fail-closed: when this returns false callers use the
    cloud/anchored overlay path rather than making an unbudgeted vision call.
    """
    rate = float(os.getenv("OVERLAY_VISION_COST_USD", "0.03"))
    cfg = runtime_config.get()
    path = _job_path(job_id, "cost_ledger.json")
    with _LOCK:
        ledger = _load_ledger(path)
        duplicate = any(
            item.get("kind") == "overlay_vision" and item.get("scene_key") == scene_key
            for item in ledger.get("items", []) if isinstance(item, dict)
        )
        projected = int(ledger.get("total_krw", 0)) + _krw(rate, float(cfg["usd_krw"]))
        return not duplicate and projected <= int(cfg["max_budget_per_video_krw"])


def record_cost(job_id: int, kind: str, count: int = 1, *, scene_key: str | None = None) -> dict[str, Any]:
    """비-Gemini 요청의 비용을 기록한다.

    Gemini는 POST 직전 ``ProviderRequestAudit``가 이미 비용을 점유한다.
    그 뒤 성공 처리에서 다시 기록하면 재시도와 성공 요청이 이중 청구되므로,
    같은 장면 키의 Gemini 시도가 있으면 이 함수는 기존 원장을 그대로 반환한다.
    """
    rates = runtime_config.get()
    if kind == "flash":
        raise ValueError("Flash 비용 기록은 Pro-only 이미지 정책에서 허용되지 않습니다.")
    unit_usd = {
        "pro": float(rates["img_cost_pro_2k_usd"]),
        "kling": float(rates["kling_cost_per_clip_usd"]),
        "overlay_vision": float(os.getenv("OVERLAY_VISION_COST_USD", "0.03")),
    }.get(kind, 0.0)
    amount = _krw(unit_usd * count, float(rates["usd_krw"]))
    path = _job_path(job_id, "cost_ledger.json")
    with _LOCK:
        ledger = _load_ledger(path)
        provider_by_kind = {"pro": "gemini", "kling": "fal"}
        if scene_key and provider_by_kind.get(kind) and any(
            item.get("provider") == provider_by_kind[kind]
            and item.get("scene_key") == scene_key
            for item in ledger["items"]
            if isinstance(item, dict)
        ):
            return ledger
        item = {"kind": kind, "count": count, "amount_krw": amount, "at": datetime.now(timezone.utc).isoformat()}
        if scene_key:
            item["scene_key"] = scene_key
        ledger["items"].append(item)
        ledger["total_krw"] = int(ledger.get("total_krw", 0)) + amount
        limit = int(rates["max_budget_per_video_krw"])
        ledger["budget_overrun_krw"] = max(0, ledger["total_krw"] - limit)
        _write_ledger(path, ledger)
    return ledger

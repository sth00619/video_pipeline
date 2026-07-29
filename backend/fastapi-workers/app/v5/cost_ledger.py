"""V5 비용 원장과 예산 버킷 검증용 walking skeleton 구현."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class Bucket(str, Enum):
    IMAGE_DRAFT = "image_draft"
    IMAGE_FINAL = "image_final"
    IMAGE_EDIT = "image_edit"
    MOTION = "motion"
    TTS = "tts"
    RETRY = "retry"


# P0 walking skeleton 검증 상한이다. 서비스 연결 단계(P1)에서 Spring의
# PricingConfig.java 계약값을 런타임 설정으로 주입하도록 확장한다.
BUCKET_LIMITS_KRW = {
    Bucket.IMAGE_DRAFT: 3000,
    Bucket.IMAGE_FINAL: 7000,
    Bucket.IMAGE_EDIT: 2000,
    Bucket.MOTION: 15000,
    Bucket.TTS: 5000,
    Bucket.RETRY: 8000,
}
TOTAL_CEILING_KRW = 40000


class BudgetExceeded(Exception):
    """버킷 또는 총 예산을 초과했음을 알리는 예외."""


class FxUnavailable(Exception):
    """승인된 환율 값을 가져오지 못했음을 알리는 예외."""


class FxProvider:
    """USD→KRW 환율 제공자.

    P0에서는 테스트 전용 환경변수로만 주입한다. 프로덕션에서는 승인된 환율
    공급자와 캐시로 교체해야 하며, 값이 없으면 보수적으로 요청을 중단한다.
    """

    def __init__(self, conservative_buffer: float = 1.10) -> None:
        self._buffer = conservative_buffer
        self._cache: Optional[tuple[date, float]] = None

    def usd_to_krw(self) -> float:
        today = date.today()
        if self._cache and self._cache[0] == today:
            return self._cache[1]
        raw_rate = self._fetch()
        self._cache = (today, raw_rate * self._buffer)
        return self._cache[1]

    @staticmethod
    def _fetch() -> float:
        raw = os.environ.get("FX_USD_KRW", "").strip()
        if raw:
            try:
                return float(raw)
            except ValueError:
                pass
        raise FxUnavailable(
            "환율 소스가 없습니다. P0 검증에서는 FX_USD_KRW를 명시하고, "
            "프로덕션에서는 승인된 환율 API를 연결하세요."
        )


@dataclass
class LedgerEntry:
    scene_id: str
    provider: str
    model: str
    request_kind: str
    bucket: str
    estimated_cost_usd: float
    actual_cost_usd: Optional[float]
    currency_rate_snapshot: float
    estimated_cost_krw: int
    actual_cost_krw: Optional[int]
    budget_committed_krw: int
    status: str
    cost_status: str = "verified"
    metadata: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class CostLedger:
    """P0 인메모리 원장. 실제 비용이 발생하면 항상 한 줄을 기록한다."""

    def __init__(self, video_id: str, fx: Optional[FxProvider] = None) -> None:
        self.video_id = video_id
        self._fx = fx or FxProvider()
        self._entries: list[LedgerEntry] = []
        self._bucket_spent_krw = {bucket: 0 for bucket in Bucket}

    def can_afford(self, bucket: Bucket, estimated_usd: float) -> tuple[bool, int, float]:
        rate = self._fx.usd_to_krw()
        estimated_krw = round(estimated_usd * rate)
        within_bucket = self._bucket_spent_krw[bucket] + estimated_krw <= BUCKET_LIMITS_KRW[bucket]
        within_total = self.total_spent_krw() + estimated_krw <= TOTAL_CEILING_KRW
        return within_bucket and within_total, estimated_krw, rate

    def guard(self, bucket: Bucket, estimated_usd: float) -> tuple[int, float]:
        allowed, estimated_krw, rate = self.can_afford(bucket, estimated_usd)
        if not allowed:
            raise BudgetExceeded(
                f"버킷 {bucket.value} 또는 총액 상한 초과: 예상 ₩{estimated_krw}, "
                f"버킷 잔여 ₩{self.bucket_remaining_krw(bucket)}, "
                f"총 잔여 ₩{TOTAL_CEILING_KRW - self.total_spent_krw()}"
            )
        return estimated_krw, rate

    def record(
        self, *, scene_id: str, provider: str, model: str, request_kind: str,
        bucket: Bucket, estimated_usd: float, actual_usd: Optional[float], rate: float, status: str,
        cost_status: str = "verified", metadata: Optional[dict] = None,
    ) -> LedgerEntry:
        actual_krw = round(actual_usd * rate) if actual_usd is not None else None
        # API가 실비를 돌려주지 않는 공급자는 승인된 추정치 전체를 즉시 예산에
        # 예약한다. 실비 0원으로 적재하거나 다음 요청에 재사용하지 않는다.
        committed_krw = actual_krw if actual_krw is not None else round(estimated_usd * rate)
        entry = LedgerEntry(
            scene_id=scene_id, provider=provider, model=model, request_kind=request_kind,
            bucket=bucket.value, estimated_cost_usd=round(estimated_usd, 6),
            actual_cost_usd=round(actual_usd, 6) if actual_usd is not None else None,
            currency_rate_snapshot=round(rate, 4), estimated_cost_krw=round(estimated_usd * rate),
            actual_cost_krw=actual_krw, budget_committed_krw=committed_krw, status=status,
            cost_status=cost_status, metadata=metadata or {},
        )
        self._entries.append(entry)
        self._bucket_spent_krw[bucket] += entry.budget_committed_krw
        print(f"[LEDGER] {json.dumps(asdict(entry), ensure_ascii=False)}")
        return entry

    def total_spent_krw(self) -> int:
        return sum(self._bucket_spent_krw.values())

    def bucket_remaining_krw(self, bucket: Bucket) -> int:
        return BUCKET_LIMITS_KRW[bucket] - self._bucket_spent_krw[bucket]

    def summary(self) -> dict:
        return {
            "video_id": self.video_id,
            "total_spent_krw": self.total_spent_krw(),
            "total_ceiling_krw": TOTAL_CEILING_KRW,
            "buckets": {bucket.value: self._bucket_spent_krw[bucket] for bucket in Bucket},
            "entries": [asdict(entry) for entry in self._entries],
        }

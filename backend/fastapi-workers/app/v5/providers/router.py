"""V5 벤치마크 결과에 근거한 이미지 프로바이더 라우터.

Gemini Pro는 최종 장면, BFL klein은 초안에만 사용한다. 벤치마크하지 않은
모델로 자동 하향하거나 무료 이미지를 조용히 만드는 경로는 두지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional

from app.v5.cost_ledger import Bucket, CostLedger
from app.v5.providers.bfl_flux_provider import ImageResult
from app.v5.scene.prompt_builder import SceneSpec
from app.v5.scene.quality_gate import QualityGate, ScoreCard


RenderTier = Literal["hero", "body", "draft"]
ProviderName = Literal["gemini_pro", "bfl_klein", "v4_cutaway"]

# 11개 archetype의 primary-surface 검증 통과로 최종 Gemini lane을 열었다.
# earnings_stage만은 화면형 보조 패널 QualityGate 재검증 전까지 생성 자체를 막는다.
RENDER_BLOCKED_ARCHETYPES = frozenset({"earnings_stage"})


class CutawayRequired(RuntimeError):
    """예산상 생성하면 안 되는 경우의 명시적 V4 cutaway 강등 신호."""


class FinalLaneApprovalRequired(RuntimeError):
    """오염 검증 전에는 최종 lane을 실비 렌더링에 쓰지 못하게 막는다."""


class ArchetypeApprovalRequired(RuntimeError):
    """아직 개별 검증이 끝나지 않은 archetype의 실비 생성을 막는다."""


class HumanRegenerationDecisionRequired(RuntimeError):
    """화면형 보조 소품은 자동 재생성하지 않고 사람 승인으로만 처리한다."""


@dataclass(frozen=True)
class RenderSpec:
    scene: SceneSpec
    prompt: str
    tier: RenderTier
    width: int = 2048
    height: int = 1152
    seed: Optional[int] = None
    reference_image_paths: tuple[str, ...] = ()
    request_audit: object | None = None

    def validate(self) -> None:
        self.scene.validate()
        if self.tier not in {"hero", "body", "draft"}:
            raise ValueError("V5 렌더 tier는 hero/body/draft만 허용합니다.")
        if not self.prompt.strip():
            raise ValueError("V5 이미지 프롬프트가 비어 있습니다.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("V5 이미지 크기는 양수여야 합니다.")


@dataclass(frozen=True)
class ProviderAdapter:
    """외부 API 구현을 감싼 테스트 가능한 프로바이더 계약."""

    name: ProviderName
    model: str
    bucket: Bucket
    estimate_cost_usd: Callable[[int, int], float]
    generate: Callable[[RenderSpec], ImageResult]


@dataclass(frozen=True)
class RouteDecision:
    provider: ProviderName
    model: str | None
    estimated_cost_usd: float | None
    reason: str


class ImageProviderRouter:
    """승인된 모델과 예산만으로 V5 생성 경로를 선택한다."""

    def __init__(
        self, *, gemini_pro: ProviderAdapter, bfl_klein: ProviderAdapter,
        final_lane_approved: bool = True,
    ) -> None:
        if gemini_pro.name != "gemini_pro" or bfl_klein.name != "bfl_klein":
            raise ValueError("Gemini Pro와 BFL klein 어댑터를 정확히 지정해야 합니다.")
        self._gemini_pro = gemini_pro
        self._bfl_klein = bfl_klein
        self._final_lane_approved = final_lane_approved

    def decide(self, spec: RenderSpec, ledger: CostLedger) -> RouteDecision:
        spec.validate()
        candidates = self._candidates(spec.tier)
        for adapter, reason in candidates:
            estimated = adapter.estimate_cost_usd(spec.width, spec.height)
            allowed, _, _ = ledger.can_afford(adapter.bucket, estimated)
            if allowed:
                return RouteDecision(adapter.name, adapter.model, estimated, reason)
        return RouteDecision("v4_cutaway", None, None, "승인된 V5 이미지 예산 부족: V4 cutaway로 명시적 강등")

    def render(self, spec: RenderSpec, ledger: CostLedger) -> ImageResult:
        """한 장을 렌더하고 같은 비용 원장에 결과를 기록한다."""
        if spec.tier in {"hero", "body"} and not self._final_lane_approved:
            raise FinalLaneApprovalRequired(
                "Gemini Pro는 오염 수정 검증이 끝난 뒤에만 최종 lane으로 사용할 수 있습니다."
            )
        if spec.tier in {"hero", "body"} and spec.scene.archetype in RENDER_BLOCKED_ARCHETYPES:
            raise ArchetypeApprovalRequired(
                f"{spec.scene.archetype}는 화면형 보조 소품 QualityGate 재검증 전까지 실비 생성이 차단됩니다."
            )
        decision = self.decide(spec, ledger)
        if decision.provider == "v4_cutaway":
            raise CutawayRequired(decision.reason)
        adapter = self._gemini_pro if decision.provider == "gemini_pro" else self._bfl_klein
        estimated, rate = ledger.guard(adapter.bucket, float(decision.estimated_cost_usd))
        try:
            result = adapter.generate(spec)
        except Exception as exc:
            ledger.record(
                scene_id=spec.scene.scene_id, provider=adapter.name, model=adapter.model,
                request_kind="generate", bucket=adapter.bucket, estimated_usd=float(decision.estimated_cost_usd),
                actual_usd=None, rate=rate, status=f"failed:{type(exc).__name__}",
                cost_status="unverified_until_console_reconciliation",
                metadata={"route_reason": decision.reason, "reserved_krw": estimated},
            )
            raise
        ledger.record(
            scene_id=spec.scene.scene_id, provider=adapter.name, model=result.model,
            request_kind="generate", bucket=adapter.bucket, estimated_usd=float(decision.estimated_cost_usd),
            actual_usd=result.actual_cost_usd, rate=rate, status="ok",
            cost_status="verified" if result.actual_cost_usd is not None else "unverified_until_console_reconciliation",
            metadata={"route_reason": decision.reason, **result.meta},
        )
        return result

    def render_checked(
        self, spec: RenderSpec, ledger: CostLedger, *, retry_budget_available: bool,
    ) -> tuple[ImageResult, ScoreCard]:
        """품질 미달 장면만 한 번 재생성하고, 재실패는 명시적으로 강등한다.

        각 ``render`` 호출은 독립된 비용 원장 항목을 만들므로 재시도가 무료로
        숨겨지지 않는다. 호출자는 요청 단위 감사 원장도 씬별로 전달해야 한다.
        """
        result = self.render(spec, ledger)
        card = QualityGate.score(result.image_bytes, spec.scene)
        action = QualityGate.next_action(card, generation_attempt=0, retry_budget_available=retry_budget_available)
        if action == "pass":
            return result, card
        if action == "manual_review_required":
            raise HumanRegenerationDecisionRequired(
                "QualityGate가 primary 밖 화면형 보조 소품을 감지했습니다: "
                "자동 재생성은 차단되며 사람의 재생성 결정을 기다립니다."
            )
        if action == "retry_once":
            retried = self.render(spec, ledger)
            retry_card = QualityGate.score(retried.image_bytes, spec.scene)
            if QualityGate.next_action(retry_card, generation_attempt=1, retry_budget_available=False) == "pass":
                return retried, retry_card
            raise CutawayRequired("QualityGate 재생성 1회 후에도 미달: V4 cutaway로 명시적 강등")
        raise CutawayRequired("QualityGate 미달이며 재생성 예산이 없음: V4 cutaway로 명시적 강등")

    def _candidates(self, tier: RenderTier) -> tuple[tuple[ProviderAdapter, str], ...]:
        if tier == "draft":
            return ((self._bfl_klein, "초안 tier는 klein으로 제한"),)
        # P1 벤치마크에서 Gemini Pro가 캐릭터 일관성·무대 다양성·정보 밀도에서
        # 우위였다. Flash는 동일 조건에서 평가하지 않았으므로 자동 선택하지 않는다.
        return (
            (self._gemini_pro, "P1 벤치마크 우위: Gemini Pro 최종 후보 lane"),
            (self._bfl_klein, "Gemini Pro 예산 부족 시 승인된 저비용 초안 lane"),
        )

"""V5 Gemini 3 Pro Image 어댑터.

기존 워커의 검증된 Gemini HTTP 경로를 재사용한다. Gemini 응답에는 청구 실비가
포함되지 않으므로, 생성 직후 이를 실비로 가장해 비용 원장에 적재하지 않는다.
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from .bfl_flux_provider import ImageResult


class GeminiModel(str, Enum):
    PRO = "gemini-3-pro-image"
    FLASH = "gemini-3.1-flash-image"


class GeminiProviderError(RuntimeError):
    """Gemini 생성 또는 비용 계약 준비 실패."""


class GeminiProvider:
    """기존 실사용 Gemini 전송 경로를 V5 ImageResult 계약으로 감싼다."""

    def __init__(self, api_key: Optional[str] = None, *, use_batch: bool = False) -> None:
        self._key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._use_batch = use_batch

    def estimate_cost_usd(self, model: GeminiModel, width: int, height: int, *, is_edit: bool = False) -> float:
        """승인자가 주입한 모델별 예상 비용만 사용한다.

        Gemini가 응답으로 실비를 주지 않으므로 기본값을 코드에 숨기지 않는다.
        P1-b 실행 전 현재 계약 단가를 환경변수로 명시해야 한다.
        """
        name = "V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD" if model == GeminiModel.PRO else "V5_GEMINI_FLASH_IMAGE_2K_ESTIMATE_USD"
        raw = os.environ.get(name, "").strip()
        if not raw:
            raise GeminiProviderError(f"{name}가 필요합니다. 승인된 현재 계약 단가를 설정하세요.")
        try:
            value = float(raw)
        except ValueError as exc:
            raise GeminiProviderError(f"{name}는 양의 숫자여야 합니다.") from exc
        if value <= 0:
            raise GeminiProviderError(f"{name}는 양의 숫자여야 합니다.")
        return value

    def generate(
        self, prompt: str, *, model: GeminiModel = GeminiModel.PRO, width: int = 2048,
        height: int = 1152, seed: Optional[int] = None, reference_image_paths: Optional[list[str]] = None,
        request_audit=None,
    ) -> ImageResult:
        if not self._key:
            raise GeminiProviderError("GEMINI_API_KEY 미설정")
        if self._use_batch:
            raise GeminiProviderError("V5 Gemini batch 생성은 P1-b 비교 범위 밖입니다.")

        # 기존 이미지 프로바이더는 image_provider=gemini + Pro 조합에서 FAL/Pollinations
        # 하향 폴백을 거부한다. 따라서 비교 결과의 공급자가 섞이지 않는다.
        from app.providers.real.image import NanaBananaProvider

        prompt = (
            "Reference image order is fixed: image 1 is the channel mascot identity; "
            "image 2 is the approved line, palette, and cel-shading style. "
            "Preserve the mascot identity from image 1 exactly: one round gold-coin silhouette, the same face proportions, "
            "eye shape, iris treatment, rim thickness, and dark outline weight in every scene. Wardrobe and expression may change, "
            "but never redesign or restyle the mascot. Use image 2 only as visual style. "
            "Render one continuous full-bleed scene, never a split screen, comic panel, inset image, or internal frame. "
            "Follow the placement instructions in the written prompt; do not invent framing guides. "
            "Do not reproduce marks from any reference image.\n\n" + prompt
        )
        with TemporaryDirectory(prefix="v5_gemini_") as temporary_dir:
            output_path = Path(temporary_dir) / "generated.png"
            try:
                NanaBananaProvider().generate(
                    prompt=prompt,
                    output_path=str(output_path),
                    image_provider="gemini",
                    gemini_model=model.value,
                    gemini_image_size="2K",
                    gemini_service_tier="standard",
                    # P1 비교는 승인된 장면 수와 실제 HTTP 요청 수가 같아야 한다.
                    # 재시도는 상위 승인 절차가 별도로 새 요청을 예약할 때만 허용한다.
                    gemini_max_attempts=1,
                    gemini_request_audit=request_audit,
                    gemini_reference_contract_declared=True,
                    character_image_paths=reference_image_paths or [],
                    # V5 SceneSpec과 참조 시트가 캐릭터·스타일 계약의 단일 출처다.
                    # 공용 V4의 청록 카드 마스코트와 빈 패널 금지문을 덧붙이지 않는다.
                    character_style_prompt="none",
                    suppress_legacy_style_lock=True,
                    style_locked=True,
                )
            except Exception as exc:
                raise GeminiProviderError(f"Gemini Pro 이미지 생성 실패: {type(exc).__name__}") from exc
            if not output_path.exists() or not output_path.read_bytes():
                raise GeminiProviderError("Gemini Pro가 이미지 파일을 반환하지 않았습니다.")
            image_bytes = output_path.read_bytes()

        return ImageResult(
            image_bytes=image_bytes,
            model=model.value,
            width=width,
            height=height,
            seed=seed,
            actual_cost_usd=None,
            request_id="gemini-billing-not-returned",
            meta={
                "cost_status": "unverified_until_console_reconciliation",
                "reference_image_count": len(reference_image_paths or []),
            },
        )

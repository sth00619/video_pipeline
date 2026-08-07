"""V5 Gemini 3 Pro Image 어댑터.

기존 워커의 검증된 Gemini HTTP 경로를 재사용한다. Gemini 응답에는 청구 실비가
포함되지 않으므로, 생성 직후 이를 실비로 가장해 비용 원장에 적재하지 않는다.
"""
from __future__ import annotations

import hashlib
import logging
import os
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from .bfl_flux_provider import ImageResult

logger = logging.getLogger(__name__)


class GeminiModel(str, Enum):
    PRO = "gemini-3-pro-image"


class GeminiProviderError(RuntimeError):
    """Gemini 생성 또는 비용 계약 준비 실패."""


class ReferenceAssetMissingError(GeminiProviderError):
    """V5 화풍 계약에 필요한 승인 참조 자산이 없을 때 발생한다."""


# 씬 스타일 예시 파일명 순서 — 이 목록이 Gemini에 전송되는 참조 자산의 단일 출처다.
_SCENE_STYLE_REF_NAMES = [
    "style_scene_ref_01_port.png",
    "style_scene_ref_02_split.png",
    "style_scene_ref_03_retail.png",
    "style_scene_ref_04_weather.png",
    "style_scene_ref_05_weather_v2.png",
]


def _load_default_references() -> list[str]:
    """캐릭터·화풍 승인 참조를 고정 순서로 반환한다.

    반환 순서:
      [0] character_reference_v4_identity_clean.png  — 캐릭터 정체성 고정
      [1] style_reference_v4_medium_clean.png        — 선 두께·팔레트·셀 쉐이딩
      [2..6] style_scene_ref_01~05.png               — 확립된 씬 스타일 예시 5개
    """
    root = Path(__file__).resolve().parents[3] / "out" / "references"
    paths = [
        root / "character_reference_v4_identity_clean.png",
        root / "style_reference_v4_medium_clean.png",
        *[root / name for name in _SCENE_STYLE_REF_NAMES],
    ]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise ReferenceAssetMissingError(
            "V5 승인 참조 자산 없음:\n" + "\n".join(f"  {p}" for p in missing)
        )
    return [str(p) for p in paths]


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
        if model != GeminiModel.PRO:
            raise GeminiProviderError("V5 이미지는 gemini-3-pro-image만 허용합니다.")
        name = "V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD"
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
        if reference_image_paths is None:
            reference_image_paths = _load_default_references()

        # 기존 이미지 프로바이더는 image_provider=gemini + Pro 조합에서 FAL/Pollinations
        # 하향 폴백을 거부한다. 따라서 비교 결과의 공급자가 섞이지 않는다.
        from app.providers.real.image import NanaBananaProvider

        reference_names = [Path(path).name.lower() for path in reference_image_paths or []]
        character_indices = [index + 1 for index, name in enumerate(reference_names) if "character_reference" in name]
        style_indices = [index + 1 for index, name in enumerate(reference_names) if "style_reference" in name]
        if character_indices:
            character_index = character_indices[0]
            reference_contract = (
                f"Reference image {character_index} is the authoritative channel mascot identity model sheet. "
                f"Preserve the mascot identity from image {character_index} exactly: one round gold-coin silhouette, the same face proportions, "
                "eye shape, iris treatment, rim thickness, and dark outline weight. "
                "Goldie (the gold coin mascot) MUST ALWAYS wear scene-appropriate full clothing (e.g. business suit, vest, jacket, coat, safety vest) and headwear/hat (e.g. fedora hat, safety helmet, reporter hat, cap). "
                "NEVER depict Goldie bare without clothing or headwear. Goldie MUST stand prominent in the foreground taking up 50% to 65% of total frame height; "
                "expression, hat/outfit style, and arm pose may vary by scene archetype, but never redesign or restyle the core mascot face identity. "
            )
        elif len(reference_names) == 1 and not style_indices:
            # 기존 단일 캐릭터 참조 호출과의 호환성이다. 파일명이 명확한 스타일
            # 참조인 경우에는 이 분기로 들어오지 않는다.
            reference_contract = (
                "Reference image 1 is the authoritative channel mascot identity model sheet. "
                "Preserve the mascot identity from image 1 exactly: one round gold-coin silhouette, the same face proportions, "
                "eye shape, iris treatment, rim thickness, and dark outline weight. "
                "Goldie MUST ALWAYS wear full scene-appropriate clothing and headwear/hat, standing prominent taking up 50% to 65% of frame height. "
            )
        else:
            reference_contract = (
                "No mascot identity reference is supplied. Do not invent or add a mascot unless the written prompt explicitly requires one. "
            )
        if style_indices:
            reference_contract += (
                f"Reference image {style_indices[0]} is visual style only: use its line weight, palette, and cel shading, "
                "but do not treat it as a character identity and do not reproduce its individual marks. "
            )
        prompt = (
            reference_contract
            + "Render one continuous full-bleed scene, never a split screen, comic panel, inset image, or internal frame. "
            "Follow the placement instructions in the written prompt; do not invent framing guides. "
            "Do not reproduce marks from any reference image.\n\n" + prompt
        )
        # ──────────────────────────────────────────────────────────────────
        # [전송 전 강제 검증 로그] 매 Gemini API 호출마다 실제 전송 파일을 기록한다.
        # 이 로그 없이는 "코드는 맞다"는 보고가 검증 불가 — 반드시 출력돼야 한다.
        # ──────────────────────────────────────────────────────────────────
        logger.info("[GEMINI_REF_AUDIT] === Gemini API 호출 직전 참조 자산 검증 ===")
        logger.info("[GEMINI_REF_AUDIT] 전송 참조 이미지 수: %d", len(reference_image_paths))
        for idx, ref_path in enumerate(reference_image_paths, start=1):
            p = Path(ref_path)
            if p.is_file():
                sha = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                size_kb = p.stat().st_size // 1024
                logger.info(
                    "[GEMINI_REF_AUDIT]   [%d] %s  sha256=%s...  %dKB",
                    idx, p.name, sha, size_kb,
                )
            else:
                logger.error(
                    "[GEMINI_REF_AUDIT]   [%d] MISSING: %s", idx, ref_path
                )
        logger.info("[GEMINI_REF_AUDIT] 프롬프트 첫 200자: %s", prompt[:200])
        logger.info("[GEMINI_REF_AUDIT] ================================================")

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

"""Black Forest Labs FLUX.2 API 어댑터.

키는 BFL_API_KEY 환경변수에서만 읽으며, 로그 또는 예외에 키 값을 포함하지 않는다.
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import requests


class BflError(Exception):
    """BFL 요청 실패의 기반 예외."""


class BflAuthError(BflError):
    """키 누락, 인증 실패 또는 크레딧 부족."""


class BflTimeoutError(BflError):
    """생성 폴링이 제한 시간을 초과함."""


class BflRequestError(BflError):
    """BFL API 또는 다운로드 요청 실패."""


class BflRateLimitError(BflError):
    """BFL 동시 요청 제한 초과."""


class BflModel(str, Enum):
    KLEIN_9B = "flux-2-klein-9b"
    KLEIN_9B_PREVIEW = "flux-2-klein-9b-preview"
    PRO = "flux-2-pro"
    PRO_PREVIEW = "flux-2-pro-preview"
    MAX = "flux-2-max"


# P0.5 한 장만 위한 보수적 사전 추정값이다. 실제 청구 확인·모델 라우팅은
# P1에서 PricingConfig.java 기반의 중앙 비용 계약으로 연결한다.
_FIRST_MP_USD = {
    BflModel.KLEIN_9B: 0.015,
    BflModel.KLEIN_9B_PREVIEW: 0.015,
    BflModel.PRO: 0.03,
    BflModel.PRO_PREVIEW: 0.03,
    BflModel.MAX: 0.07,
}
_EXTRA_MP_USD = {
    BflModel.KLEIN_9B: 0.001,
    BflModel.KLEIN_9B_PREVIEW: 0.001,
    BflModel.PRO: 0.015,
    BflModel.PRO_PREVIEW: 0.015,
    BflModel.MAX: 0.035,
}
_EDIT_SURCHARGE_USD = {
    BflModel.PRO: 0.045,
    BflModel.PRO_PREVIEW: 0.045,
    BflModel.MAX: 0.07,
}


@dataclass
class ImageResult:
    image_bytes: bytes
    model: str
    width: int
    height: int
    seed: Optional[int]
    actual_cost_usd: Optional[float]
    request_id: str
    is_edit: bool = False
    meta: dict = field(default_factory=dict)


class BflFluxProvider:
    BASE = "https://api.bfl.ai/v1"

    def __init__(
        self, api_key: Optional[str] = None, *, poll_interval_s: float = 1.5,
        poll_timeout_s: float = 120.0, session: Optional[requests.Session] = None,
    ) -> None:
        key = api_key or os.environ.get("BFL_API_KEY", "")
        if not key:
            raise BflAuthError("BFL_API_KEY 미설정. .env를 확인하세요.")
        self._key = key
        self._poll_interval = poll_interval_s
        self._poll_timeout = poll_timeout_s
        self._session = session or requests.Session()

    def estimate_cost_usd(self, model: BflModel, width: int, height: int, *, is_edit: bool = False) -> float:
        megapixels = max(1, math.ceil(width * height / 1_000_000))
        first = _EDIT_SURCHARGE_USD.get(model, _FIRST_MP_USD[model]) if is_edit else _FIRST_MP_USD[model]
        return round(first + _EXTRA_MP_USD[model] * (megapixels - 1), 6)

    def generate(
        self, prompt: str, *, model: BflModel = BflModel.KLEIN_9B, width: int = 1024,
        height: int = 1024, seed: Optional[int] = None, input_image_b64: Optional[str] = None,
        extra_payload: Optional[dict] = None,
    ) -> ImageResult:
        payload: dict = {"prompt": prompt, "width": width, "height": height}
        if seed is not None:
            payload["seed"] = seed
        if input_image_b64:
            payload["input_image"] = input_image_b64
        if extra_payload:
            payload.update(extra_payload)
        submitted = self._post(f"{self.BASE}/{model.value}", payload)
        polling_url = submitted.get("polling_url")
        if not polling_url:
            raise BflRequestError("BFL 응답에 polling_url이 없습니다.")
        completed = self._poll(polling_url)
        sample_url = completed.get("result", {}).get("sample")
        if not sample_url:
            raise BflRequestError("BFL 완료 응답에 결과 이미지 주소가 없습니다.")
        return ImageResult(
            image_bytes=self._download(sample_url), model=model.value, width=width, height=height,
            seed=completed.get("result", {}).get("seed", seed),
            actual_cost_usd=self.estimate_cost_usd(model, width, height, is_edit=input_image_b64 is not None),
            request_id=submitted.get("id", ""), is_edit=input_image_b64 is not None,
            meta={"polling_url": polling_url},
        )

    def _headers(self) -> dict:
        return {"x-key": self._key, "Content-Type": "application/json", "accept": "application/json"}

    def _post(self, url: str, payload: dict) -> dict:
        try:
            response = self._session.post(url, headers=self._headers(), json=payload, timeout=30)
        except requests.RequestException as exc:
            raise BflRequestError(f"BFL 생성 요청 실패: {type(exc).__name__}") from exc
        self._raise_for_status(response)
        return response.json()

    def _poll(self, polling_url: str) -> dict:
        deadline = time.monotonic() + self._poll_timeout
        while time.monotonic() < deadline:
            try:
                response = self._session.get(polling_url, headers=self._headers(), timeout=30)
            except requests.RequestException as exc:
                raise BflRequestError(f"BFL 폴링 요청 실패: {type(exc).__name__}") from exc
            self._raise_for_status(response)
            payload = response.json()
            status = payload.get("status")
            if status == "Ready":
                return payload
            if status in {"Error", "Failed", "Content Moderated", "Request Moderated"}:
                raise BflRequestError(f"BFL 생성이 실패했습니다: status={status}")
            time.sleep(self._poll_interval)
        raise BflTimeoutError(f"BFL 폴링이 {self._poll_timeout:.0f}초를 초과했습니다.")

    def _download(self, url: str) -> bytes:
        try:
            response = self._session.get(url, timeout=60)
        except requests.RequestException as exc:
            raise BflRequestError(f"결과 이미지 다운로드 실패: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise BflRequestError(f"결과 이미지 다운로드 실패: HTTP {response.status_code}")
        return response.content

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        if response.status_code == 402:
            raise BflAuthError("BFL 크레딧이 부족합니다. 잔액을 확인하세요.")
        if response.status_code in {401, 403}:
            raise BflAuthError(f"BFL 인증 또는 권한 오류: HTTP {response.status_code}")
        if response.status_code == 429:
            raise BflRateLimitError("BFL 요청 제한에 도달했습니다. 잠시 후 재시도하세요.")
        if response.status_code >= 400:
            raise BflRequestError(f"BFL API 오류: HTTP {response.status_code}")

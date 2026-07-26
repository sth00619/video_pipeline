"""Phase B 제공자. 비활성 기본 플래그가 켜질 때만 인스턴스를 생성한다."""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np

from app import runtime_config


@dataclass
class ProviderResult:
    image_bgr: np.ndarray
    latency_ms: int
    cost_estimate_krw: float


def _data_uri(image_bgr: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image_bgr)
    if not ok: raise RuntimeError("PNG 인코딩에 실패했습니다")
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode()


class FalCannyProvider:
    ENDPOINT = "https://fal.run/fal-ai/flux-control-lora-canny/image-to-image"
    USD_PER_MEGAPIXEL = .04
    def __init__(self, api_key: str | None = None, timeout_s: float = 120):
        self.api_key = api_key or os.getenv("FAL_KEY")
        if not self.api_key: raise RuntimeError("FAL_KEY가 설정되지 않았습니다")
        self.timeout_s = timeout_s
    def stylize(self, crop_bgr: np.ndarray, style_prompt: str, strength: float) -> ProviderResult:
        import httpx
        started = time.monotonic()
        canny = cv2.cvtColor(cv2.Canny(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY), 60, 160), cv2.COLOR_GRAY2BGR)
        response = httpx.post(self.ENDPOINT, json={"prompt": style_prompt, "image_url": _data_uri(crop_bgr), "control_lora_image_url": _data_uri(canny), "strength": strength, "num_inference_steps": 28, "enable_safety_checker": True}, headers={"Authorization": f"Key {self.api_key}"}, timeout=self.timeout_s)
        response.raise_for_status()
        raw = httpx.get(response.json()["images"][0]["url"], timeout=self.timeout_s).content
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None: raise RuntimeError("제공자 이미지 디코딩에 실패했습니다")
        if image.shape[:2] != crop_bgr.shape[:2]: image = cv2.resize(image, (crop_bgr.shape[1], crop_bgr.shape[0]), interpolation=cv2.INTER_CUBIC)
        # 환율은 런타임 중앙 설정을 사용해 비용 원장의 단일 기준을 유지한다.
        cost = crop_bgr.shape[0] * crop_bgr.shape[1] / 1e6 * self.USD_PER_MEGAPIXEL * float(runtime_config.value("usd_krw"))
        return ProviderResult(image, int((time.monotonic() - started) * 1000), cost)


class GeminiEditProvider:
    MODEL = "gemini-3.1-flash-image"
    def __init__(self, api_key: str | None = None, timeout_s: float = 120):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key: raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다")
        self.timeout_s = timeout_s
    def stylize(self, crop_bgr: np.ndarray, style_prompt: str, strength: float) -> ProviderResult:
        import httpx
        started = time.monotonic(); ok, encoded = cv2.imencode(".png", crop_bgr)
        if not ok: raise RuntimeError("PNG 인코딩에 실패했습니다")
        instruction = f"재질 질감만 다시 칠하세요. 모든 글리프, 숫자, 막대 높이, 선 위치와 레이아웃은 정확히 동일하게 유지하세요. 스타일: {style_prompt}"
        response = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.MODEL}:generateContent", json={"contents": [{"parts": [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(encoded.tobytes()).decode()}}, {"text": instruction}]}], "generationConfig": {"responseModalities": ["IMAGE"]}}, headers={"x-goog-api-key": self.api_key}, timeout=self.timeout_s)
        response.raise_for_status(); data = response.json(); payload = None
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inline_data") or part.get("inlineData")
                if inline and inline.get("data"): payload = inline["data"]
        if not payload: raise RuntimeError("제공자가 이미지를 반환하지 않았습니다")
        image = cv2.imdecode(np.frombuffer(base64.b64decode(payload), np.uint8), cv2.IMREAD_COLOR)
        if image is None: raise RuntimeError("제공자 이미지 디코딩에 실패했습니다")
        if image.shape[:2] != crop_bgr.shape[:2]: image = cv2.resize(image, (crop_bgr.shape[1], crop_bgr.shape[0]), interpolation=cv2.INTER_CUBIC)
        return ProviderResult(image, int((time.monotonic() - started) * 1000), 0.0)


class IdentityProvider:
    """비용 없는 dry-run 제공자이며, dry-run에서는 실제 API 클래스를 호출하지 않는다."""
    def stylize(self, crop_bgr: np.ndarray, style_prompt: str, strength: float) -> ProviderResult:
        noise = np.random.default_rng(0).normal(0, 2, crop_bgr.shape).astype(np.int16)
        return ProviderResult(np.clip(crop_bgr.astype(np.int16) + noise, 0, 255).astype(np.uint8), 1, 0.0)

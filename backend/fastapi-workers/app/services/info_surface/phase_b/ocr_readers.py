"""Injected readers for Phase B's text-integrity gate."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile

import cv2
import numpy as np


class MockReader:
    def __init__(self, texts: list[str]): self.texts = texts
    def read_texts(self, image_bgr: np.ndarray) -> list[str]: return list(self.texts)


class TesseractReader:
    def __init__(self, langs: str = "kor+eng", psm: int = 11):
        if shutil.which("tesseract") is None:
            raise RuntimeError("tesseract is not installed")
        self.langs, self.psm = langs, psm

    def read_texts(self, image_bgr: np.ndarray) -> list[str]:
        upscaled = cv2.resize(image_bgr, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.normalize(cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY), None, 0, 255, cv2.NORM_MINMAX)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            cv2.imwrite(handle.name, gray); path = handle.name
        try:
            output = subprocess.run(["tesseract", path, "stdout", "-l", self.langs, "--psm", str(self.psm)], capture_output=True, text=True, timeout=30, check=False)
            return [line for line in output.stdout.splitlines() if line.strip()]
        finally:
            os.unlink(path)


class GeminiVisionReader:
    PROMPT = "List every legible text string in this image, one per line. Return exact characters only."

    def __init__(self, api_key: str | None = None, model: str = "gemini-3.1-flash-image", timeout_s: float = 30):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key: raise RuntimeError("GEMINI_API_KEY is not configured")
        self.model, self.timeout_s = model, timeout_s

    def read_texts(self, image_bgr: np.ndarray) -> list[str]:
        import httpx
        ok, buffer = cv2.imencode(".png", image_bgr)
        if not ok: raise RuntimeError("PNG encode failed")
        response = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent", json={"contents": [{"parts": [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(buffer.tobytes()).decode()}}, {"text": self.PROMPT}]}]}, headers={"x-goog-api-key": self.api_key}, timeout=self.timeout_s)
        response.raise_for_status()
        return [part["text"] for candidate in response.json().get("candidates", []) for part in candidate.get("content", {}).get("parts", []) if "text" in part]

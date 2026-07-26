"""Crop-only, one-attempt Phase B orchestration with mandatory fallback."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .contracts import HarmonizeRequest, HarmonizeResult
from .gates import TextReader, run_all_gates

CROP_MARGIN_PX = 12


def _crop_with_margin(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    x, y, width, height = bbox
    frame_h, frame_w = frame.shape[:2]
    x0, y0 = max(0, x - CROP_MARGIN_PX), max(0, y - CROP_MARGIN_PX)
    x1, y1 = min(frame_w, x + width + CROP_MARGIN_PX), min(frame_h, y + height + CROP_MARGIN_PX)
    return frame[y0:y1, x0:x1].copy(), (x0, y0, x1, y1)


def harmonize_surface(request: HarmonizeRequest, frame_bgr: np.ndarray, provider, reader: TextReader, composite_mask_full: np.ndarray | None = None, output_path: str | None = None) -> tuple[HarmonizeResult, np.ndarray]:
    """Never retries; any provider/gate failure returns the untouched Phase A frame."""
    crop, (x0, y0, x1, y1) = _crop_with_margin(frame_bgr, request.crop_bbox_in_frame)
    try:
        provider_result = provider.stylize(crop, request.style_prompt, request.strength)
    except Exception as exc:
        return HarmonizeResult(scene_id=request.scene_id, provider=request.provider, accepted=False, gates=[], fallback_reason=f"provider_error: {exc}"), frame_bgr
    gates = run_all_gates(crop, provider_result.image_bgr, expected_texts=request.expected_texts, bars=request.bars, palette_rgb=request.palette_rgb, reader=reader)
    if not all(gate.passed for gate in gates):
        return HarmonizeResult(scene_id=request.scene_id, provider=request.provider, accepted=False, gates=gates, fallback_reason=";".join(f"{gate.name}:{gate.detail}" for gate in gates if not gate.passed), latency_ms=provider_result.latency_ms, cost_estimate_krw=provider_result.cost_estimate_krw), frame_bgr
    final = frame_bgr.copy()
    if composite_mask_full is None:
        final[y0:y1, x0:x1] = provider_result.image_bgr
    else:
        mask = composite_mask_full[y0:y1, x0:x1]
        region = final[y0:y1, x0:x1]
        region[mask.astype(bool)] = provider_result.image_bgr[mask.astype(bool)]
        final[y0:y1, x0:x1] = region
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(output_path, final)
    return HarmonizeResult(scene_id=request.scene_id, provider=request.provider, accepted=True, gates=gates, latency_ms=provider_result.latency_ms, cost_estimate_krw=provider_result.cost_estimate_krw, output_path=output_path), final

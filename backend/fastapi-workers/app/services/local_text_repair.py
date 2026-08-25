"""비승인·훼손 문자열 영역만 찾아 원본 프레임의 다른 픽셀을 보존하며 지운다."""
from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import requests

from app.utils.budget import can_charge_overlay_vision, record_cost
from app.utils.visual_qa import VISUAL_QA_MODEL, _encode_review_image, _post_visual_review


@dataclass(frozen=True)
class TextRegion:
    text: str
    bbox: tuple[float, float, float, float]
    confidence: float


TextRegionResolver = Callable[[str, list[str]], list[TextRegion]]


def _single_provider_region_is_safe(region: TextRegion) -> bool:
    """단일 비전 좌표는 고신뢰·소영역일 때만 후보로 허용한다."""
    return region.confidence >= .95 and region.bbox[2] * region.bbox[3] <= .02


def assess_deterministic_inpaint_surface(
    image_path: str,
    regions: list[TextRegion],
    *,
    minimum_dominant_surface_ratio: float = .52,
) -> dict:
    """평평한 종이·패널이 아닌 복잡한 그라데이션에는 인페인팅을 금지한다.

    문자 상자의 중앙색과 가까운 픽셀이 절반보다 적으면 글자 외에 게이지,
    일러스트, 직인 같은 시각 정보가 섞인 영역으로 본다. 이 경우 좌표가 맞아도
    OpenCV가 주변 색을 진흙처럼 번지게 만들 수 있으므로 비전 국소 편집으로
    넘긴다.
    """
    source = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if source is None:
        return {"passed": False, "reason": "image_unreadable", "regions": []}
    height, width = source.shape[:2]
    reports = []
    for region in regions:
        x, y, box_width, box_height = region.bbox
        left = max(0, round(x * width))
        top = max(0, round(y * height))
        right = min(width, round((x + box_width) * width))
        bottom = min(height, round((y + box_height) * height))
        if left >= right or top >= bottom:
            reports.append({"text": region.text, "passed": False, "reason": "empty_bbox"})
            continue
        crop = source[top:bottom, left:right]
        median = np.median(crop.reshape(-1, 3), axis=0)
        distance = np.linalg.norm(
            crop.astype(np.float32) - median.astype(np.float32), axis=2,
        )
        dominant_ratio = float(np.mean(distance <= 45.0))
        reports.append({
            "text": region.text,
            "dominant_surface_ratio": round(dominant_ratio, 4),
            "passed": dominant_ratio >= minimum_dominant_surface_ratio,
            "pixel_bbox": [left, top, right, bottom],
        })
    passed = bool(reports) and all(bool(item.get("passed")) for item in reports)
    return {
        "passed": passed,
        "reason": "flat_surface" if passed else "complex_surface_requires_visual_edit",
        "minimum_dominant_surface_ratio": minimum_dominant_surface_ratio,
        "regions": reports,
    }


def text_regions_from_visual_review(
    review: dict,
    target_texts: list[str],
) -> list[TextRegion]:
    """동일 QA 응답에 포함된 고신뢰 오류 문자열 좌표를 안전 형식으로 변환한다."""
    targets = {str(value).strip() for value in target_texts if str(value).strip()}
    regions: list[TextRegion] = []
    for item in review.get("unexpected_text_regions") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        bbox = item.get("bbox")
        confidence = float(item.get("confidence") or 0)
        if text not in targets or not isinstance(bbox, list) or len(bbox) != 4 or confidence < .85:
            continue
        x, y, width, height = (float(value) for value in bbox)
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            continue
        if width * height > .08:
            continue
        regions.append(TextRegion(text, (x, y, width, height), confidence))
    return regions


def _gemini_text_regions(image_path: str, target_texts: list[str]) -> list[TextRegion]:
    """Gemini에는 0~1000 정수 좌표로 동일 문자열 위치를 독립 요청한다."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return []
    path = Path(image_path)
    instruction = (
        "Locate only the visible malformed glyph clusters cited in Targets. A cited target may be an approximate visual-QA transcription "
        "(for example 3005 when the stylized glyphs look like 7005). In that case locate the visually corresponding cluster, but copy the cited "
        "target string verbatim into the text field so it can be audited. Return JSON only as "
        '{"regions":[{"text":string,"box_2d":[ymin,xmin,ymax,xmax],"confidence":0-1}]}. '
        "box_2d uses integer coordinates 0..1000 relative to the full image and must tightly enclose only the glyphs. "
        "Do not include correct Korean text, people, blank paper, borders, signatures, seals, or icons. "
        "If a target is not visible, omit it. Targets: " + json.dumps(target_texts, ensure_ascii=False)
    )
    payload = {
        "contents": [{"parts": [
            {"text": instruction},
            {"inlineData": {"mimeType": "image/jpeg", "data": _encode_review_image(path)}},
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }
    try:
        response = _post_visual_review(payload, api_key)
    except (requests.Timeout, requests.ConnectionError):
        return []
    if response is None or response.status_code != 200:
        return []
    parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    raw = next((part.get("text") for part in parts if part.get("text")), "")
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    targets = {str(value).strip() for value in target_texts if str(value).strip()}
    regions: list[TextRegion] = []
    for item in payload.get("regions") or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("text") or "").strip()
        box = item.get("box_2d")
        confidence = float(item.get("confidence") or 0)
        if value not in targets or not isinstance(box, list) or len(box) != 4 or confidence < .7:
            continue
        ymin, xmin, ymax, xmax = (float(number) / 1000.0 for number in box)
        if xmin < 0 or ymin < 0 or xmax > 1 or ymax > 1 or xmin >= xmax or ymin >= ymax:
            continue
        if (xmax - xmin) * (ymax - ymin) > .08:
            continue
        regions.append(TextRegion(value, (xmin, ymin, xmax - xmin, ymax - ymin), confidence))
    return regions


def _claude_text_regions(image_path: str, target_texts: list[str]) -> list[TextRegion]:
    """Claude에는 수정 권한 없이 잘못된 문자열의 좌표만 요청한다."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return []
    import anthropic

    path = Path(image_path)
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    prompt = (
        "Locate only the visible malformed glyph clusters cited below. A cited target can be an approximate visual-QA transcription; "
        "for example, target 3005 may correspond to stylized glyphs that look like 7005. Locate that corresponding cluster, but copy the cited "
        "target string verbatim into the text field for audit matching. Do not locate correct text, decorative lines, signatures, seals, or icons. "
        "Return JSON only as {\"regions\":[{\"text\":string,\"bbox\":[x,y,width,height],\"confidence\":0-1}]}. "
        "All bbox coordinates are normalized 0..1 relative to the full image and must tightly enclose only the glyphs. "
        "Return an empty regions array if a target is not actually visible.\nTargets: "
        + json.dumps(target_texts, ensure_ascii=False)
    )
    response = anthropic.Anthropic(api_key=api_key).messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": encoded}},
            {"type": "text", "text": prompt},
        ]}],
    )
    text = "".join(getattr(block, "text", "") for block in response.content)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    payload = json.loads(text[start:end + 1])
    target_set = {str(value).strip() for value in target_texts if str(value).strip()}
    regions: list[TextRegion] = []
    for item in payload.get("regions") or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("text") or "").strip()
        bbox = item.get("bbox")
        confidence = float(item.get("confidence") or 0)
        if value not in target_set or not isinstance(bbox, list) or len(bbox) != 4 or confidence < .7:
            continue
        x, y, width, height = (float(number) for number in bbox)
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            continue
        if width * height > .08:
            continue
        regions.append(TextRegion(value, (x, y, width, height), confidence))
    return regions


def locate_malformed_text_regions(
    image_path: str,
    target_texts: list[str],
    *,
    job_id: int | None = None,
    scene_key: str = "",
    resolver: TextRegionResolver | None = None,
) -> list[TextRegion]:
    """비용 게이트를 통과한 경우에만 문자 위치 비전 호출을 실행한다."""
    targets = list(dict.fromkeys(str(value).strip() for value in target_texts if str(value).strip()))
    if not targets or not Path(image_path).is_file():
        return []
    if resolver is None:
        if job_id is None or not scene_key or not can_charge_overlay_vision(job_id, scene_key):
            return []
        # 한 모델의 좌표 착시로 얼굴·소품을 지우지 않도록 두 비전 판독의
        # 동일 문자열 상자가 실제로 겹칠 때만 수정 좌표를 승인한다.
        gemini_regions = _gemini_text_regions(image_path, targets)
        claude_regions = _claude_text_regions(image_path, targets)
        regions = _intersection_consensus(gemini_regions, claude_regions)
        agreed_texts = {region.text for region in regions}
        # 두 번째 판독이 공급자 장애로 비었더라도 Gemini가 0.90 이상으로
        # 같은 실제 글자를 읽은 경우에는 후보 좌표로 허용한다. 이후 단계의
        # 원본-후보 비교 게이트가 잘못 짚은 비문자 영역 변경을 다시 차단한다.
        regions.extend(
            region for region in gemini_regions
            if region.text not in agreed_texts and region.confidence >= .90
        )
        agreed_texts = {region.text for region in regions}
        # Gemini 연결 장애가 열린 동안에도 Claude가 아주 작은 문자 군집을
        # 0.95 이상으로 특정하면 후보 좌표로 허용한다. 넓은 단일 판독 상자는
        # 캐릭터·소품을 침범할 위험이 있으므로 화면의 2% 이하로 한정한다.
        # 이후 원본-후보 보존 검수가 비문자 영역 변경을 다시 차단한다.
        regions.extend(
            region for region in claude_regions
            if (
                region.text not in agreed_texts
                and _single_provider_region_is_safe(region)
            )
        )
        if regions:
            record_cost(job_id, "overlay_vision", scene_key=scene_key)
        return regions
    return resolver(image_path, targets)


def _region_iou(first: TextRegion, second: TextRegion) -> float:
    ax, ay, aw, ah = first.bbox
    bx, by, bw, bh = second.bbox
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def _intersection_consensus(
    first: list[TextRegion],
    second: list[TextRegion],
    *,
    minimum_iou: float = .35,
) -> list[TextRegion]:
    agreed: list[TextRegion] = []
    for candidate in first:
        matches = [region for region in second if region.text == candidate.text]
        if not matches:
            continue
        best = max(matches, key=lambda region: _region_iou(candidate, region))
        if _region_iou(candidate, best) < minimum_iou:
            continue
        ax, ay, aw, ah = candidate.bbox
        bx, by, bw, bh = best.bbox
        left, top = min(ax, bx), min(ay, by)
        right, bottom = max(ax + aw, bx + bw), max(ay + ah, by + bh)
        agreed.append(TextRegion(
            candidate.text,
            (left, top, right - left, bottom - top),
            min(candidate.confidence, best.confidence),
        ))
    return agreed


def inpaint_text_regions(
    image_path: str,
    output_path: str,
    regions: list[TextRegion],
    *,
    padding_px: int = 4,
) -> dict:
    """마스크 내부만 OpenCV 인페인팅하고 마스크 밖 원본 픽셀은 그대로 복원한다."""
    source = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if source is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")
    height, width = source.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    pixel_regions = []
    for region in regions:
        x, y, box_width, box_height = region.bbox
        left = max(0, round(x * width) - padding_px)
        top = max(0, round(y * height) - padding_px)
        right = min(width, round((x + box_width) * width) + padding_px)
        bottom = min(height, round((y + box_height) * height) + padding_px)
        if left >= right or top >= bottom:
            continue
        crop = source[top:bottom, left:right]
        # 상자 전체를 흐리지 않고 주변 종이·패널의 중앙색에서 크게 벗어난
        # 글자 획만 마스크로 만든다. 인페인팅 후에도 테두리·직인·서명은 남는다.
        median = np.median(crop.reshape(-1, 3), axis=0)
        distance = np.linalg.norm(crop.astype(np.float32) - median.astype(np.float32), axis=2)
        threshold = max(28.0, float(np.percentile(distance, 68)))
        glyph_mask = np.where(distance >= threshold, 255, 0).astype(np.uint8)
        glyph_mask = cv2.dilate(glyph_mask, np.ones((3, 3), np.uint8), iterations=1)
        mask[top:bottom, left:right] = np.maximum(mask[top:bottom, left:right], glyph_mask)
        pixel_regions.append({**asdict(region), "pixel_bbox": [left, top, right, bottom]})
    if not pixel_regions:
        raise ValueError("인페인팅할 유효 문자 영역이 없습니다.")

    repaired = cv2.inpaint(source, mask, 5, cv2.INPAINT_TELEA)
    repaired[mask == 0] = source[mask == 0]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), repaired):
        raise RuntimeError(f"인페인팅 결과를 저장하지 못했습니다: {output}")
    outside_delta = cv2.absdiff(source, repaired)[mask == 0]
    return {
        "status": "completed",
        "output_path": str(output),
        "regions": pixel_regions,
        "mask_pixel_ratio": round(float(np.count_nonzero(mask)) / float(width * height), 8),
        "outside_mask_max_delta": int(outside_delta.max()) if outside_delta.size else 0,
        "pixel_preservation_passed": bool(not outside_delta.size or outside_delta.max() == 0),
    }

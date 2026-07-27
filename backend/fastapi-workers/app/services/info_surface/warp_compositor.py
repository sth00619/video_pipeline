"""Perspective, texture, and occlusion aware composition for factual overlays."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .channel_chart_style import render_chart_content, render_metric_summary
from .channel_typography import TEXT_ROLES, display_font, draw_display_text
from .contracts import InfoSurfacePlan
from .contracts import INFO_SURFACE_COMPOSITOR_VERSION
from .detector import QuadDetection
from .material_fx import apply_material_fx


COMPOSITOR_VERSION = INFO_SURFACE_COMPOSITOR_VERSION
MIN_SUPPORT_XHEIGHT_1080P = 24.0
MIN_SUPPORT_STROKE_1080P = 2.2
# INTER_CUBIC의 가장자리 손실을 보수적으로 반영하는 렌더 안전 여유다.
WARP_FONT_SAFETY = 1.20
WARP_STROKE_SAFETY = 1.40


def _inset_quad(quad: np.ndarray, ratio: float) -> np.ndarray:
    center = quad.mean(axis=0); return (center + (quad - center) * (1 - ratio)).astype(np.float32)


def _logical_support_metrics(text: str, px: int = 56) -> tuple[float, float]:
    """실제 번들 폰트에서 support 글자의 몸통 높이와 보수적 획폭을 잰다."""
    role = TEXT_ROLES["support"]
    scale = max(1.0, float(px) / role.minimum_px)
    font = display_font(round(role.minimum_px * scale))
    probe = Image.new("RGBA", (max(256, px * 8), max(128, px * 4)))
    draw = ImageDraw.Draw(probe)
    draw_display_text(probe, (probe.width // 2, px), text, role="support", fill="#071A3A", align="center", scale=scale)
    rgba = np.asarray(probe)
    dark = (np.all(rgba[:, :, :3] < np.array([90, 90, 110], dtype=np.uint8), axis=2) & (rgba[:, :, 3] > 0)).astype(np.uint8)
    ys, _ = np.where(dark)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=0)
    body_height = float(max(1, bbox[3] - bbox[1]))
    distance = cv2.distanceTransform(dark, cv2.DIST_L2, 3)
    positive = distance[distance > 0]
    # p50은 래스터화 뒤 실제로 읽히는 내부 획을 반영한다. p10은
    # 안티앨리어싱 경계 픽셀이 지배하므로 굵은 글자에서도 약 1px에
    # 고정되어 가독성 획 두께를 나타내지 못한다.
    visible_stroke = float(max(1.0, 2.0 * np.percentile(positive, 50))) if positive.size else float(role.outer_stroke_px)
    return body_height, visible_stroke


def diegetic_supersample_factor(
    logical_size: tuple[int, int],
    quad: np.ndarray,
    *,
    inset_ratio: float = .06,
    role: str = "support",
    text_candidates: tuple[str, ...] = ("수령",),
) -> dict:
    """quad 크기와 실제 폰트 메트릭에서 필요한 렌더 배율을 계산한다."""
    if role != "support":
        return {"factor": 1.0, "final_output_scale": 0.0, "reason": "role_not_supported"}
    target_quad = _inset_quad(np.asarray(quad, dtype=np.float32), inset_ratio)
    quad_diagonal = max(float(np.linalg.norm(target_quad[2] - target_quad[0])), float(np.linalg.norm(target_quad[3] - target_quad[1])))
    logical_diagonal = float(np.hypot(logical_size[0], logical_size[1]))
    final_output_scale = quad_diagonal / max(1.0, logical_diagonal)
    metrics = [_logical_support_metrics(text or "수령", 56) for text in text_candidates] or [_logical_support_metrics("수령", 56)]
    logical_xheight = min(item[0] for item in metrics)
    logical_stroke = min(item[1] for item in metrics)
    output_normalization = 1080.0 / max(1.0, float(logical_size[1]))
    predicted_xheight = logical_xheight * final_output_scale * output_normalization
    predicted_stroke = logical_stroke * final_output_scale * output_normalization
    font_scale = max(1.0, MIN_SUPPORT_XHEIGHT_1080P / max(.001, predicted_xheight)) * WARP_FONT_SAFETY
    stroke_scale = max(1.0, MIN_SUPPORT_STROKE_1080P / max(.001, predicted_stroke)) * WARP_STROKE_SAFETY
    # 슈퍼샘플 배수는 동일한 물리 하한에서 파생한다. 보간 품질은
    # 캔버스 확대가 담당하고, 두 타이포그래피 배율은 비례 확대만으로
    # 보존되지 않는 글리프 기하를 유지한다.
    factor = max(1.0, font_scale, stroke_scale)
    return {
        "factor": round(float(factor), 4),
        "final_output_scale": round(final_output_scale, 6),
        "logical_xheight_px": round(logical_xheight, 3),
        "logical_stroke_px": round(logical_stroke, 3),
        "predicted_xheight_1080p_px": round(predicted_xheight, 3),
        "predicted_stroke_1080p_px": round(predicted_stroke, 3),
        "support_font_scale": round(float(font_scale), 4),
        "support_stroke_scale": round(float(stroke_scale), 4),
        "predicted_after_typography_xheight_1080p_px": round(predicted_xheight * font_scale, 3),
        "predicted_after_typography_stroke_1080p_px": round(predicted_stroke * stroke_scale, 3),
        "min_xheight_1080p_px": MIN_SUPPORT_XHEIGHT_1080P,
        "min_stroke_1080p_px": MIN_SUPPORT_STROKE_1080P,
    }


def composite_planar(image: Image.Image, chart: dict, plan: InfoSurfacePlan, detection: QuadDetection, content_override: Image.Image | None = None) -> Image.Image:
    """Write transparent chart ink into a real prop while preserving its border and foreground."""
    if plan.surface is None:
        return image
    base = image.convert("RGBA"); bgr = cv2.cvtColor(np.asarray(base.convert("RGB")), cv2.COLOR_RGB2BGR)
    quad = _inset_quad(detection.quad, plan.surface.inset_ratio)
    width = max(96, int(max(np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3])) * 1.7))
    height = max(72, int(max(np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1])) * 1.7))
    render_chart = {**chart, "hero_stat": plan.hero_stat.model_dump() if plan.hero_stat else chart.get("hero_stat")}
    if content_override is None:
        rendered = render_chart_content(render_chart, (width, height), return_metadata=True)
        assert not isinstance(rendered, Image.Image)
        content = rendered.image
        bars = rendered.bars
    else:
        content = content_override
        bars = []
    # content_override는 worker가 quad 기반 슈퍼샘플로 만든 입력이다.
    # 큰 캔버스를 다시 줄이면 작은 한글 획을 먼저 잃으므로, 부족할 때만 확대한다.
    if content.size[0] < width or content.size[1] < height:
        content = content.resize((width, height), Image.Resampling.LANCZOS)
    # Rendering is the sole authority for these fields. The Phase B request
    # consumes them later; no LLM or detector infers bar height/value/color.
    plan.chart_render_metadata = {"bars": bars, "canvas_size": list(content.size)}
    content = apply_material_fx(content, plan.surface.surface_kind, render_chart.get("scene_seed") or plan.scene_id)
    content_width, content_height = content.size
    source = np.array([[0, 0], [content_width - 1, 0], [content_width - 1, content_height - 1], [0, content_height - 1]], dtype=np.float32)
    rgba = np.asarray(content)
    # 투명 보더는 OpenCV가 대상 버퍼의 기존 값을 보존할 수 있어, RGBA 픽셀의
    # RGB 채널에 임의 값이 남을 수 있다. 보드 밖은 항상 완전 투명 검정으로 초기화한다.
    warped = cv2.warpPerspective(
        rgba,
        cv2.getPerspectiveTransform(source, quad),
        (base.width, base.height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    alpha = warped[:, :, 3]
    # v4 템플릿 보드는 프롬프트와 계약에서 빈 물리 표면으로 제한된다.
    # 생성 모델의 조명 그라데이션을 가림 물체로 오인하면 결정론적 글자와
    # 도형이 조각나므로, 이 경로에서는 보드 내부 가림 마스크를 쓰지 않는다.
    occluder = (
        np.zeros_like(detection.occluder_mask)
        if plan.template_id
        else cv2.dilate(detection.occluder_mask, np.ones((5, 5), np.uint8))
    )
    alpha[(detection.surface_mask == 0) | (occluder > 0)] = 0
    warped[:, :, 3] = alpha
    # Put a little of the actual paper/metal grain back over the ink, avoiding
    # a clean UI sticker while never altering verified glyph geometry.
    texture = cv2.GaussianBlur(bgr, (0, 0), 2.0)
    highpass = cv2.subtract(bgr, texture)
    texture_alpha = (alpha.astype(np.float32) * (.06 if plan.template_id else .18)).astype(np.uint8)
    texture_rgba = np.dstack((cv2.cvtColor(highpass, cv2.COLOR_BGR2RGB), texture_alpha))
    result = Image.alpha_composite(base, Image.fromarray(warped, "RGBA"))
    return Image.alpha_composite(result, Image.fromarray(texture_rgba, "RGBA"))


def render_data_cutaway(
    chart: dict,
    size: tuple[int, int] = (1920, 1080),
    reference_image: Image.Image | None = None,
) -> Image.Image:
    """Render a full-frame chart insert while retaining the scene's visual family.

    This is an explicit one-to-one scene replacement, never a floating card.
    The blurred, darkened source palette keeps the insert connected to the
    preceding shot without exposing its unverified/generated lettering.
    """
    if reference_image is not None:
        backdrop = reference_image.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
        backdrop = backdrop.filter(ImageFilter.GaussianBlur(radius=max(8, size[0] // 100)))
        veil = Image.new("RGBA", size, (7, 26, 58, 210))
        canvas = Image.alpha_composite(backdrop, veil)
    else:
        canvas = Image.new("RGBA", size, "#102238")
    content = render_chart_content(chart, (int(size[0] * .74), int(size[1] * .62)))
    content = apply_material_fx(content, "paper", chart.get("scene_seed"))
    # A restrained paper-like central field is only for this explicit cutaway,
    # never an arbitrary fallback over a generated scene.
    paper_size = (int(size[0] * .80), int(size[1] * .70))
    paper = Image.new("RGBA", paper_size, "#EDE0C4")
    paper_draw = ImageDraw.Draw(paper)
    # Deterministic fibres avoid a sterile UI rectangle while remaining safely
    # independent from facts or generated text.
    for x in range(18, paper.width, 37):
        paper_draw.line((x, 0, max(0, x - paper.height // 8), paper.height), fill=(140, 110, 75, 20), width=1)
    paper_draw.rectangle((0, 0, paper.width - 1, paper.height - 1), outline="#071A3A", width=max(3, size[0] // 420))
    paper.alpha_composite(content, (int(size[0] * .03), int(size[1] * .04)))
    canvas.alpha_composite(paper, (int(size[0] * .10), int(size[1] * .12)))
    return canvas

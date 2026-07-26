"""수령의 워프 전/후 글리프를 측정한다. 합성·재워프는 수행하지 않는다."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from dataclasses import replace

from app.services.info_surface.channel_typography import display_font
from app.services.info_surface.contracts import plan_from_scene
from app.services.info_surface.narrative_diagrams import render_diagram
from app.workers.images_worker import _diagram_spec_from_scene

ROOT = Path("/app/data/jobs/94301")
MANIFEST = Path("/app/data/jobs/v4_live_validation_manifest.json")
PREWARP = ROOT / "debug" / "vault_stage_prewarp_canvas.png"
PRE_CROP = ROOT / "debug" / "vault_stage_prewarp_suryung_crop_2x.png"
FINAL = Path(os.environ.get("V4_TEXT_FINAL", str(ROOT / "debug" / "vault_stages_warped.png")))
REPORT = ROOT / "debug" / "vault_stage_text_metrics.json"

reports = json.loads(MANIFEST.read_text(encoding="utf-8"))
scene = reports[0]["scene"]
plan = plan_from_scene(scene)
if plan is None:
    raise RuntimeError("InfoSurfacePlan을 만들 수 없습니다")
diagram_spec = _diagram_spec_from_scene(scene, plan)
quad = np.float32([[1411.31, 332.93], [2240.38, 199.69], [2356.08, 919.59], [1527.01, 1052.84]])
horizontal = max(np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3]))
vertical = max(np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1]))
logical_size = (max(96, int(horizontal * 1.7)), max(72, int(vertical * 1.7)))
logical = render_diagram(diagram_spec, logical_size)
logical.save(PREWARP, "PNG")

# Production records the supersampled canvas and the derived typography
# scales. Reuse those values so the final crop measures the actual glyphs.
production_report = ROOT / "debug" / "production_path_revalidation.json"
production_meta = {}
if production_report.is_file():
    production_meta = json.loads(production_report.read_text(encoding="utf-8")).get("chart_render_metadata") or {}
diagram_render_size = tuple(production_meta.get("diagram_render_size") or logical_size)
supersample_meta = production_meta.get("diagram_supersample") or {}
measured_spec = replace(
    diagram_spec,
    support_font_scale=float(supersample_meta.get("support_font_scale", 1.0)),
    support_stroke_scale=float(supersample_meta.get("support_stroke_scale", 1.0)),
)
measured_canvas = render_diagram(measured_spec, diagram_render_size)

index = next((i for i, item in enumerate(diagram_spec.items) if item.label == "수령"), None)
if index is None:
    raise RuntimeError("DiagramSpec.items에 수령이 없습니다")
w, h = diagram_render_size
r = min(w, h) // 11
margin = .10
usable = w * (1 - 2 * margin)
cx = int(w * margin + usable * ((index % 2) * .5 + .25))
cy = int(h * ((index // 2) * .36 + .30))
label_anchor = (cx, cy + r * 2.55)
base_scale = max(1.0, (r // 2) / 30)
font_scale_multiplier = max(1.0, float(supersample_meta.get("support_font_scale", 1.0)))
stroke_scale_multiplier = max(1.0, float(supersample_meta.get("support_stroke_scale", 1.0)))
scale = base_scale * font_scale_multiplier
font_size = round(30 * scale)
font = display_font(font_size)
draw = ImageDraw.Draw(measured_canvas)
outer_stroke = max(1, round(3 * base_scale * font_scale_multiplier * stroke_scale_multiplier))
inner_stroke = max(1, round(1 * base_scale * font_scale_multiplier * stroke_scale_multiplier))
width = draw.textbbox((0, 0), "수령", font=font, stroke_width=outer_stroke)[2]
text_x = int(label_anchor[0] - width // 2)
text_bbox = draw.textbbox((text_x, label_anchor[1]), "수령", font=font, stroke_width=outer_stroke)
pad = 18
crop_box = (max(0, text_bbox[0] - pad), max(0, text_bbox[1] - pad), min(w, text_bbox[2] + pad), min(h, text_bbox[3] + pad))
measured_canvas.crop(crop_box).resize((int((crop_box[2] - crop_box[0]) * 2), int((crop_box[3] - crop_box[1]) * 2)), Image.Resampling.NEAREST).save(PRE_CROP, "PNG")

# 실제 production compositor와 같은 inset/콘텐츠 리사이즈를 사용해 최종 위치를 계산한다.
center = quad.mean(axis=0)
inset_quad = center + (quad - center) * (1 - .06)
content_size = tuple(production_meta.get("canvas_size") or (max(96, int(max(np.linalg.norm(inset_quad[1] - inset_quad[0]), np.linalg.norm(inset_quad[2] - inset_quad[3])) * 1.7)), max(72, int(max(np.linalg.norm(inset_quad[3] - inset_quad[0]), np.linalg.norm(inset_quad[2] - inset_quad[1])) * 1.7))))
scale_x, scale_y = content_size[0] / w, content_size[1] / h
corners = np.float32([[crop_box[0] * scale_x, crop_box[1] * scale_y], [crop_box[2] * scale_x, crop_box[1] * scale_y], [crop_box[2] * scale_x, crop_box[3] * scale_y], [crop_box[0] * scale_x, crop_box[3] * scale_y]])
source = np.float32([[0, 0], [content_size[0] - 1, 0], [content_size[0] - 1, content_size[1] - 1], [0, content_size[1] - 1]])
mapped = cv2.perspectiveTransform(corners[None, :, :], cv2.getPerspectiveTransform(source, inset_quad))[0]

final_metrics = None
if FINAL.is_file():
    frame = cv2.imread(str(FINAL), cv2.IMREAD_COLOR)
    x1, y1 = np.floor(mapped.min(axis=0)).astype(int)
    x2, y2 = np.ceil(mapped.max(axis=0)).astype(int)
    roi = frame[max(0, y1):min(frame.shape[0], y2 + 1), max(0, x1):min(frame.shape[1], x2 + 1)]
    dark = np.all(roi < np.array([90, 90, 110], dtype=np.uint8), axis=2)
    # The perspective-mapped crop is a quadrilateral; an axis-aligned ROI
    # would include neighbouring locks/arcs and inflate the text height.
    polygon = np.round(mapped - np.array([x1, y1], dtype=np.float32)).astype(np.int32)
    polygon_mask = np.zeros(dark.shape, dtype=np.uint8)
    cv2.fillConvexPoly(polygon_mask, polygon, 1)
    dark &= polygon_mask.astype(bool)
    ys, xs = np.where(dark)
    distance = cv2.distanceTransform(dark.astype(np.uint8), cv2.DIST_L2, 3)
    positive_distance = distance[distance > 0]
    stroke_width_p10_px = None if not len(positive_distance) else float(2 * np.percentile(positive_distance, 10))
    stroke_width_px = None if not len(positive_distance) else float(2 * np.percentile(positive_distance, 50))
    final_metrics = {
        "mapped_crop_bbox": [int(x1), int(y1), int(x2), int(y2)],
        "dark_pixel_bbox_in_crop": None if not len(xs) else [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
        "dark_pixel_height_px_at_output": 0 if not len(ys) else int(ys.max() - ys.min() + 1),
        "x_height_1080p_normalized_px": None if not len(ys) else round(float((ys.max() - ys.min() + 1) * 1080 / frame.shape[0]), 2),
        "boundary_stroke_width_px_at_output_p10": None if stroke_width_p10_px is None else round(stroke_width_p10_px, 2),
        "boundary_stroke_width_1080p_normalized_px": None if stroke_width_p10_px is None else round(float(stroke_width_p10_px * 1080 / frame.shape[0]), 2),
        "stroke_width_px_at_output_p50": None if stroke_width_px is None else round(stroke_width_px, 2),
        "stroke_width_1080p_normalized_px": None if stroke_width_px is None else round(float(stroke_width_px * 1080 / frame.shape[0]), 2),
    }

payload = {
    "reprocess_performed": False,
    "source_stage_items": scene.get("stage_items") or [],
    "diagram_spec_items": [item.label for item in diagram_spec.items],
    "target_label": "수령",
    "logical_canvas_size": list(logical_size),
    "logical_label_anchor": list(label_anchor),
    "logical_text_bbox": list(text_bbox),
    "logical_crop_box": list(crop_box),
    "draw_display_text_args": {"text": "수령", "role": "support", "px": r // 2, "scale": scale, "font_size_px": font_size, "outer_stroke_px": outer_stroke, "inner_stroke_px": inner_stroke, "align": "center", "stroke_measurement_percentile": 50},
    "content_size_used_by_compositor": list(content_size),
    "final_metrics": final_metrics,
    "v3_floor": {"minimum_stroke_px_at_1080p": 3, "minimum_x_height_px_at_1080p": 24},
}
REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))

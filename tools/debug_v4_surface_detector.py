"""실패한 v4 프레임의 마커·컨투어 검출 근거를 저장한다."""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
from app.services.info_surface.contracts import SurfaceContract
from app.services.info_surface.detector import _border_contrast_score, _lab_distance, _preferred_bbox

JOB = Path("/app/data/jobs/94301")
# source.png는 이전 무과금 replay가 덮어썼으므로, 제공자가 처음 반환한
# 변경 불가 원본(raw)을 진단 기준으로 사용한다.
SOURCE = JOB / "images" / "scene_000_raw.png"
OUT = JOB / "debug"
OUT.mkdir(parents=True, exist_ok=True)

# 최신 v4 vault 계약을 명시적으로 재구성한다. 실제 rerender는 하지 않는다.
contract = SurfaceContract(
    surface_kind="monitor", geometry="planar_quad", marker_rgb=(246, 244, 210), border_rgb=(7, 26, 58),
    preferred_side="right", preferred_region={"x": .53, "y": .08, "width": .42, "height": .70},
    area_ratio_min=.10, area_ratio_max=.55,
)
image = cv2.imread(str(SOURCE), cv2.IMREAD_COLOR)
if image is None: raise RuntimeError(f"원본을 읽을 수 없습니다: {SOURCE}")
h, w = image.shape[:2]
lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
distance = _lab_distance(lab, contract.marker_rgb)
heatmap = np.clip(distance / 80.0 * 255, 0, 255).astype(np.uint8)
cv2.imwrite(str(OUT / "delta_e_heatmap.png"), heatmap)

raw = (distance <= contract.marker_delta_e_max).astype(np.uint8) * 255
cleaned = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
overlay = image.copy()
preferred = _preferred_bbox(contract, w, h)
cv2.rectangle(overlay, preferred[:2], preferred[2:], (255, 255, 255), 2)
rng = np.random.default_rng(94301)
candidate_rows = []
for index, contour in enumerate(contours):
    color = tuple(int(v) for v in rng.integers(50, 255, size=3))
    area = float(cv2.contourArea(contour)); ratio = area / float(w * h)
    x, y, bw, bh = cv2.boundingRect(contour); bbox = (x, y, x + bw, y + bh)
    ix1, iy1 = max(x, preferred[0]), max(y, preferred[1]); ix2, iy2 = min(x + bw, preferred[2]), min(y + bh, preferred[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1); union = max(1, bw * bh + (preferred[2]-preferred[0])*(preferred[3]-preferred[1])-inter)
    position = inter / union
    mask = np.zeros((h, w), np.uint8); cv2.drawContours(mask, [contour], -1, 255, -1)
    inside = distance[mask > 0]; purity = float(np.mean(inside <= contract.marker_delta_e_max)) if inside.size else 0.0
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, .02 * perimeter, True)
    if len(approx) == 4:
        quad = approx.reshape(4, 2)
    else:
        quad = cv2.boxPoints(cv2.minAreaRect(contour))
    surface = np.zeros((h, w), np.uint8); cv2.fillConvexPoly(surface, quad.astype(np.int32), 255)
    border_match = _border_contrast_score(lab, surface, contract)
    outer = cv2.dilate(surface, np.ones((9, 9), np.uint8)); ring = (outer > 0) & (surface == 0)
    border_dist = _lab_distance(lab, contract.border_rgb)[ring] if contract.border_rgb else np.array([])
    border_hint_match = float(np.mean(border_dist <= contract.border_delta_e_max)) if border_dist.size else None
    target = (contract.area_ratio_min + contract.area_ratio_max) / 2
    area_score = max(0.0, 1.0 - abs(ratio-target) / target)
    score = .40*purity + .20*border_match + .25*position + .15*area_score
    accepted_geometry = contract.area_ratio_min <= ratio <= contract.area_ratio_max and position >= contract.candidate_iou_min
    cv2.drawContours(overlay, [contour], -1, color, 2)
    label = f"#{index} s={score:.2f} c={purity:.2f} b={border_match:.2f} p={position:.2f} a={ratio:.2f}"
    cv2.putText(overlay, label, (x, max(18, y-6)), cv2.FONT_HERSHEY_SIMPLEX, .42, color, 1, cv2.LINE_AA)
    candidate_rows.append({"index": index, "bbox": [x,y,bw,bh], "score": score, "color_purity": purity, "border_match": border_match, "border_rgb_hint_match": border_hint_match, "position": position, "area_ratio": ratio, "area_score": area_score, "passes_area_and_position": accepted_geometry})
cv2.imwrite(str(OUT / "contour_candidates.png"), overlay)

# 실제 보드는 우측 선호 영역 내의 밝은 무문자 매트 표면 중 최대 연결 성분으로 표본화한다.
region_mask = np.zeros((h,w), np.uint8); cv2.rectangle(region_mask, preferred[:2], preferred[2:], 255, -1)
bright = ((cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) >= 185) & (region_mask > 0)).astype(np.uint8) * 255
bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((17,17), np.uint8))
components, labels, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
component = max(range(1, components), key=lambda i: stats[i, cv2.CC_STAT_AREA], default=0)
board_mask = (labels == component).astype(np.uint8) * 255
interior = cv2.erode(board_mask, np.ones((15,15), np.uint8))
outer = cv2.dilate(board_mask, np.ones((19,19), np.uint8)); boundary = (outer > 0) & (board_mask == 0)
mean_bgr = cv2.mean(image, mask=interior)[:3]
mean_rgb = [round(float(mean_bgr[2]),2), round(float(mean_bgr[1]),2), round(float(mean_bgr[0]),2)]
boundary_bgr = cv2.mean(image, mask=boundary.astype(np.uint8)*255)[:3]
boundary_rgb = [round(float(boundary_bgr[2]),2), round(float(boundary_bgr[1]),2), round(float(boundary_bgr[0]),2)]
payload = {
    "source_png": str(SOURCE), "contract": contract.model_dump(), "marker_delta_e_summary": {"min": float(distance.min()), "mean": float(distance.mean()), "p05": float(np.percentile(distance,5)), "p50": float(np.percentile(distance,50))},
    "preferred_region_px": list(preferred), "actual_board_sampling": {"method": "brightest_connected_component_within_preferred_region", "bbox": stats[component, :4].tolist() if component else None, "area_px": int(stats[component, cv2.CC_STAT_AREA]) if component else 0, "mean_rgb": mean_rgb, "boundary_mean_rgb": boundary_rgb, "boundary_rgb_distance": round(float(np.linalg.norm(np.array(mean_rgb)-np.array(boundary_rgb))),2)},
    "contours": candidate_rows,
}
payload["actual_board_sampling"]["marker_delta_e_mean"] = round(float(_lab_distance(cv2.cvtColor(np.uint8([[mean_bgr]]), cv2.COLOR_BGR2LAB), contract.marker_rgb)[0,0]), 2)
(OUT / "contract_vs_actual.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(OUT)

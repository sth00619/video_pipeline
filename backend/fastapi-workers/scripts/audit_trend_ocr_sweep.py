"""추세선 렌더 글자 크기와 OCR 사본 파라미터를 실제 Tesseract로 측정한다."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import socket
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from app.services.fal_motion_safety import _read_tesseract_rows
from app.services.surface_text_manifest import validate_manifest
from app.v5.overlay import diegetic_fact_overlay as overlay


def _blocked(*args, **kwargs):
    raise RuntimeError("오프라인 OCR 스윕에서 네트워크 호출은 금지됩니다.")


def _scene(end_value: str = "2.75%") -> dict:
    return {
        "verified_facts": [{"figure": f"2.50% → {end_value} (+0.25%p)",
                            "fact": f"기준금리는 2.50%에서 {end_value}로 0.25%p 인상됐다."}],
        "v5_verified_overlays": [{"label": "인상폭", "value": "0.25%p", "start_value": "2.50%",
                                  "end_value": end_value, "visualization": "upward_trend", "source_ref": "facts[0]",
                                  "anchor": {"x": .1, "y": .1, "width": .8, "height": .8, "kind": "monitor"}}],
    }


def _render(font_scale: float, end_value: str = "2.75%"):
    base = io.BytesIO()
    Image.new("RGB", (1280, 720), "#20354d").save(base, "PNG")
    scene = _scene(end_value)
    original = overlay._fit_font

    def scaled(text, max_width, start_size):
        return original(text, max_width, max(12, round(start_size * font_scale)))

    overlay._fit_font = scaled
    try:
        data = overlay.apply_verified_scene_facts(base.getvalue(), scene)
        validate_manifest(scene, (1280, 720))
    finally:
        overlay._fit_font = original
    return data, scene


def _normalise(rows) -> str:
    return "".join(part for row in rows for part in str(row.get("text") or "").split())


def _prepare(source: Image.Image, cell: dict, *, margin: int, target_height: int,
             border: int, strategy: str) -> Image.Image:
    anchor = cell["anchor_bbox"]
    left, top, right, bottom = cell["bbox"]
    box = (max(anchor[0], left - margin), max(anchor[1], top - margin),
           min(anchor[2], right + margin), min(anchor[3], bottom + margin))
    crop = ImageOps.autocontrast(source.convert("L").crop(box))
    corners = sorted(crop.getpixel(point) for point in (
        (0, 0), (crop.width - 1, 0), (0, crop.height - 1), (crop.width - 1, crop.height - 1),
    ))
    if (corners[1] + corners[2]) / 2 < 128:
        crop = ImageOps.invert(crop)
    width = max(1, round(crop.width * target_height / crop.height))
    crop = crop.resize((width, target_height), Image.Resampling.LANCZOS)
    if strategy == "threshold160":
        crop = crop.point(lambda value: 255 if value >= 160 else 0)
    return ImageOps.expand(crop, border=border, fill=255)


def _ocr(image: Image.Image, psm: int):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = handle.name
    try:
        image.save(path, "PNG")
        status, rows = _read_tesseract_rows(path, psm=psm)
        return {"psm": psm, "status": status, "recognized": _normalise(rows), "rows": rows}
    finally:
        os.unlink(path)


def audit(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    render_sweep = []
    for scale in (.75, .85, 1.0, 1.15, 1.30):
        try:
            data, scene = _render(scale)
        except ValueError as exc:
            render_sweep.append({"font_scale": scale, "status": "invalid_layout", "reason": str(exc)})
            continue
        path = output / f"font-{scale:.2f}.png"
        path.write_bytes(data)
        from app.services.final_frame_text_integrity import inspect_final_frame_text_integrity
        report = inspect_final_frame_text_integrity(str(path), scene)
        render_sweep.append({"font_scale": scale, "status": "rendered", "image_sha256": hashlib.sha256(data).hexdigest(),
                             "font_sizes": {c["role"]: c["font_size"] for c in scene["surface_text_manifest"]["cells"]},
                             "passed": report["passed"], "comparisons": report.get("region_comparisons", [])})

    correct_data, correct_scene = _render(1.0)
    wrong_data, wrong_scene = _render(1.0, "2.85%")
    sources = {"correct": Image.open(io.BytesIO(correct_data)).convert("RGB"),
               "wrong_endpoint": Image.open(io.BytesIO(wrong_data)).convert("RGB")}
    # 오염 fixture도 승인 계약은 원래 2.75%로 유지해야 검출 여부를 측정할 수 있다.
    # 잘못 그린 2.85% 계약으로 기대값까지 바꾸면 자기 승인이 된다.
    contracts = {"correct": correct_scene, "wrong_endpoint": correct_scene}
    preprocess_sweep = []
    for target_height in (64, 80, 96):
        for margin in (6, 12):
            for border in (16, 32):
                for strategy in ("gray", "threshold160"):
                    config = {"target_height": target_height, "source_margin": margin,
                              "blank_border": border, "strategy": strategy}
                    cases = []
                    for case_name in ("correct", "wrong_endpoint"):
                        cells = contracts[case_name]["surface_text_manifest"]["cells"]
                        selected = cells if case_name == "correct" else [c for c in cells if c["role"] == "end_value"]
                        observations = []
                        for cell in selected:
                            prepared = _prepare(sources[case_name], cell, margin=margin, target_height=target_height,
                                                border=border, strategy=strategy)
                            attempts = [_ocr(prepared, psm) for psm in cell["psm_modes"]]
                            observations.append({"cell_id": cell["id"], "expected": cell["text"], "attempts": attempts,
                                                 "all_exact": all(a["status"] == "completed" and a["recognized"] == "".join(cell["text"].split()) for a in attempts)})
                        cases.append({"case": case_name, "observations": observations})
                    correct_ok = all(o["all_exact"] for o in cases[0]["observations"])
                    wrong_detected = all(not o["all_exact"] for o in cases[1]["observations"])
                    preprocess_sweep.append({"config": config, "correct_all_cells_exact": correct_ok,
                                             "wrong_endpoint_detected": wrong_detected, "cases": cases})
    valid = [item["config"] for item in preprocess_sweep
             if item["correct_all_cells_exact"] and item["wrong_endpoint_detected"]]
    result = {"scope": "synthetic_trend_real_local_tesseract_parameter_sweep", "paid_api_calls": 0,
              "font_scale_sweep": render_sweep, "preprocess_sweep": preprocess_sweep,
              "valid_configs": valid}
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = audit(Path(args.output))
    print(json.dumps({"font_scale": [{k: v for k, v in item.items() if k in {"font_scale", "status", "font_sizes", "passed"}}
                                      for item in result["font_scale_sweep"]],
                      "valid_config_count": len(result["valid_configs"]),
                      "valid_configs": result["valid_configs"]}, ensure_ascii=False, indent=2))

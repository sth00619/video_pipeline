"""합성 래스터를 실제 로컬 OCR로 판독한다. 외부 API/운영 자산은 사용하지 않는다."""
import argparse
import copy
import hashlib
import io
import json
import socket
from pathlib import Path

from PIL import Image, ImageDraw

from app.services.final_frame_text_integrity import inspect_final_frame_text_integrity
from app.services.surface_text_manifest import draw_text_cell, set_manifest, validate_manifest
from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts
from app.v5.overlay.korean_overlay import _load_font


def blocked(*args, **kwargs):
    raise RuntimeError("오프라인 감사에서 네트워크 호출은 금지됩니다.")


def audit(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    base = io.BytesIO()
    Image.new("RGB", (1280, 720), "#20354d").save(base, "PNG")
    scene = {
        "verified_facts": [{"figure": "2.50% → 2.75% (+0.25%p)",
                            "fact": "기준금리는 2.50%에서 2.75%로 0.25%p 인상됐다."}],
        "v5_verified_overlays": [{"label": "인상폭", "value": "0.25%p", "start_value": "2.50%",
                                  "end_value": "2.75%", "visualization": "upward_trend", "source_ref": "facts[0]",
                                  "anchor": {"x": .1, "y": .1, "width": .8, "height": .8, "kind": "monitor"}}],
    }
    cases = []

    def record(name, data, contract, should_pass):
        path = output / f"{name}.png"
        path.write_bytes(data)
        validate_manifest(contract, (1280, 720))
        cases.append({"fixture": name, "expected_pass": should_pass,
                      "image_sha256": hashlib.sha256(data).hexdigest(),
                      "scene": contract,
                      "report": inspect_final_frame_text_integrity(str(path), contract)})

    rendered = apply_verified_scene_facts(base.getvalue(), scene)
    record("trend_correct", rendered, copy.deepcopy(scene), True)
    altered = copy.deepcopy(scene)
    altered["verified_facts"][0]["figure"] = "2.50% → 2.85% (+0.25%p)"
    altered["v5_verified_overlays"][0]["end_value"] = "2.85%"
    wrong = apply_verified_scene_facts(base.getvalue(), altered)
    record("trend_wrong_endpoint", wrong, copy.deepcopy(scene), False)

    for swapped in (False, True):
        image = Image.open(io.BytesIO(base.getvalue())).convert("RGB")
        draw = ImageDraw.Draw(image)
        contract = {"text_render_policy": "semantic_roles_v1", "screen_texts": ["현재 전망", "수정 전망"],
                    "screen_text_validation": {"passed": True},
                    "screen_text_plan": [{"text": t, "surface": s, "purpose": "information"}
                                         for t, s in zip(("현재 전망", "수정 전망"), ("left", "right"))],
                    "surface_bindings": {"left": {"bbox": [0, 0, .5, 1]}, "right": {"bbox": [.5, 0, .5, 1]}}}
        cells = []
        for index, text in enumerate(contract["screen_texts"]):
            draw_text_cell(draw, (120 + 640 * index, 300), text, font=_load_font(70), cells=cells,
                           cell_id=f"plan:{index}:text", role="text", anchor_bbox=[640 * index, 0, 640 * (index + 1), 720],
                           fill="white", stroke_width=2, stroke_fill="#0c121c")
        set_manifest(contract, image.size, cells)
        if swapped:
            # 같은 크기의 두 영역을 교환하여 정확한 문자열이 잘못된 표면에 있는 fixture를 만든다.
            left, right = image.crop((0, 0, 640, 720)), image.crop((640, 0, 1280, 720))
            image.paste(right, (0, 0))
            image.paste(left, (640, 0))
        stream = io.BytesIO()
        image.save(stream, "PNG")
        record("surfaces_swapped" if swapped else "surfaces_correct", stream.getvalue(), contract, not swapped)
    result = {"scope": "synthetic_raster_real_local_tesseract_not_gemini", "paid_api_calls": 0, "cases": cases}
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = audit(Path(args.output))
    print(json.dumps([{"fixture": c["fixture"], "expected_pass": c["expected_pass"],
                       "passed": c["report"]["passed"], "recognized": c["report"]["recognized"]}
                      for c in result["cases"]], ensure_ascii=False, indent=2))

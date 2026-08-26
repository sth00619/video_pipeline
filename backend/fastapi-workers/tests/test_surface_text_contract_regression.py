"""WO-IMG-01-C 선행 명세. 합성 래스터와 mock OCR을 사용한다."""
import hashlib
import io

from PIL import Image

from app.services import final_frame_text_integrity as gate
from app.utils.image_text_contract import build_scene_text_contract
from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts
from app.workers.images_worker import ImagesWorker


def test_semantic_policy_keeps_information_out_of_generator_without_erasing_text():
    result = build_scene_text_contract({
        "text_render_policy": "semantic_roles_v1",
        "screen_texts": ["영업이익", "KOSPI", "와!"],
        "screen_text_validation": {"passed": True},
    })
    assert result["generated_texts"] == []
    assert result["deterministic_texts"] == ["영업이익", "KOSPI", "와!"]


def trend_scene():
    return {
        "verified_facts": [{"figure": "2.50% → 2.75% (+0.25%p)",
                            "fact": "기준금리는 2.50%에서 2.75%로 0.25%p 인상됐다."}],
        "v5_verified_overlays": [{
            "label": "인상폭", "value": "0.25%p", "start_value": "2.50%", "end_value": "2.75%",
            "visualization": "upward_trend", "source_ref": "facts[0]",
            "anchor": {"x": .1, "y": .1, "width": .8, "height": .8, "kind": "monitor"},
        }],
    }


def test_renderer_emits_individual_trend_text_positions():
    scene = trend_scene()
    stream = io.BytesIO()
    Image.new("RGB", (1280, 720), "#20354d").save(stream, "PNG")
    apply_verified_scene_facts(stream.getvalue(), scene)
    assert {cell["role"] for cell in scene.get("surface_text_manifest", {}).get("cells", [])} == {
        "label", "value", "start_value", "end_value",
    }


def test_worker_renders_two_bound_surfaces_and_checks_separate_ocr(tmp_path, monkeypatch):
    path = tmp_path / "surfaces.png"
    Image.new("RGB", (1280, 720), "#20354d").save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    scene = {
        "text_render_policy": "semantic_roles_v1",
        "screen_texts": ["현재 전망", "수정 전망"],
        "screen_text_validation": {"passed": True},
        "screen_text_plan": [{"text": "현재 전망", "surface": "left", "purpose": "information"},
                             {"text": "수정 전망", "surface": "right", "purpose": "information"}],
        "surface_bindings": {
            "left": {"bbox": [.05, .1, .4, .5], "image_sha256": digest, "validated": True},
            "right": {"bbox": [.55, .1, .4, .5], "image_sha256": digest, "validated": True},
        },
    }
    results = iter(["현재 전망", "현재 전망", "수정 전망", "수정 전망"])
    monkeypatch.setattr(gate, "_read_tesseract_rows", lambda *a, **k: (
        "completed", [{"text": next(results)}],
    ))
    ImagesWorker()._apply_image_overlays(scene, str(path))
    assert len(scene.get("surface_text_manifest", {}).get("cells", [])) == 2
    assert scene["final_frame_text_integrity"]["ocr_passed"] is True

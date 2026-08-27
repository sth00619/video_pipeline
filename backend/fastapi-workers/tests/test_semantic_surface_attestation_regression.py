"""의미형 문자 표면이 bool 플래그만으로 승인되지 않도록 하는 선행 회귀."""
import hashlib

import pytest
from PIL import Image, ImageDraw

from app.services import final_frame_text_integrity as gate
from app.services.semantic_surface_text import render_semantic_surface_text


def _scene(path, bbox, *, geometry="axis_aligned_rect"):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "text_render_policy": "semantic_roles_v1",
        "screen_texts": ["현재 전망"],
        "screen_text_validation": {"passed": True},
        "screen_text_plan": [{"text": "현재 전망", "surface": "main", "purpose": "information"}],
        "surface_bindings": {"main": {
            "bbox": bbox, "geometry": geometry, "surface_kind": "board",
            "image_sha256": digest, "validated": True,
        }},
    }


def _mock_final_ocr(monkeypatch):
    values = iter(("현재 전망", "현재 전망"))
    monkeypatch.setattr(gate, "_read_tesseract_rows", lambda *a, **k: (
        "completed", [{"text": next(values)}],
    ))


def _save_panel(path, *, text=False, occluded=False):
    image = Image.new("RGB", (1280, 720), "#20354d")
    draw = ImageDraw.Draw(image)
    draw.rectangle((128, 72, 576, 360), fill="#eef8fb", outline="#081522", width=12)
    if text:
        draw.text((220, 180), "OLD 14X", fill="#081522", stroke_width=2)
    if occluded:
        draw.ellipse((300, 120, 650, 520), fill="#e0a927", outline="#081522", width=12)
    image.save(path)


def test_open_background_cannot_self_approve_with_validated_boolean(tmp_path, monkeypatch):
    path = tmp_path / "open.png"
    Image.new("RGB", (1280, 720), "#eef8fb").save(path)
    scene = _scene(path, [.10, .10, .35, .40])
    _mock_final_ocr(monkeypatch)
    with pytest.raises(ValueError, match="물리 표면"):
        render_semantic_surface_text(scene, str(path))


def test_actual_blank_bordered_panel_emits_pixel_attestation(tmp_path, monkeypatch):
    path = tmp_path / "panel.png"
    _save_panel(path)
    scene = _scene(path, [.10, .10, .35, .40])
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    _mock_final_ocr(monkeypatch)
    render_semantic_surface_text(scene, str(path))
    attestation = scene["surface_bindings"]["main"]["attestation"]
    assert attestation["version"] == 1
    assert attestation["source_sha256"] == source_sha
    assert attestation["validation_method"] == "opencv_geometry_text_free_v1"
    assert attestation["surface_bbox"] == [.10, .10, .35, .40]
    assert len(attestation["surface_crop_sha256"]) == 64


@pytest.mark.parametrize("variant", ["text", "occlusion"])
def test_labeled_or_occluded_panel_is_rejected_before_render(tmp_path, monkeypatch, variant):
    path = tmp_path / f"{variant}.png"
    _save_panel(path, text=variant == "text", occluded=variant == "occlusion")
    scene = _scene(path, [.10, .10, .35, .40])
    before = path.read_bytes()
    _mock_final_ocr(monkeypatch)
    with pytest.raises(ValueError, match="물리 표면"):
        render_semantic_surface_text(scene, str(path))
    assert path.read_bytes() == before
    assert "attestation" not in scene["surface_bindings"]["main"]


def test_slanted_surface_is_blocked_until_perspective_renderer_exists(tmp_path, monkeypatch):
    path = tmp_path / "slanted.png"
    _save_panel(path)
    scene = _scene(path, [.10, .10, .35, .40], geometry="planar_quad")
    _mock_final_ocr(monkeypatch)
    with pytest.raises(ValueError, match="원근"):
        render_semantic_surface_text(scene, str(path))

"""문자 위치 계약의 회귀. 판독 로직 테스트는 mock임을 명시한다."""
import copy
import hashlib
import io

import pytest
from PIL import Image, ImageDraw

from app.services import final_frame_text_integrity as gate
from app.services.semantic_surface_text import render_semantic_surface_text
from app.services.surface_text_manifest import validate_manifest
from app.utils.image_text_contract import build_scene_text_contract
from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts
from app.v5.scene.runtime_contract import plan_v5_scene_contract
from test_surface_text_contract_regression import trend_scene


def trend_file(tmp_path):
    scene = trend_scene()
    stream = io.BytesIO()
    Image.new("RGB", (1280, 720), "#20354d").save(stream, "PNG")
    path = tmp_path / "trend.png"
    path.write_bytes(apply_verified_scene_facts(stream.getvalue(), scene))
    return scene, path


def mock_cells(monkeypatch, scene, replace=None):
    replace = replace or {}
    values = iter(replace.get(cell["id"], cell["text"])
                  for cell in scene["surface_text_manifest"]["cells"] for _ in cell["psm_modes"])
    monkeypatch.setattr(gate, "_read_tesseract_rows", lambda *a, **k: (
        "completed", [{"text": next(values)}],
    ))


def bound_scene(tmp_path, texts=("현재 전망", "수정 전망")):
    path = tmp_path / "bound.png"
    image = Image.new("RGB", (1280, 720), "#20354d")
    draw = ImageDraw.Draw(image)
    draw.rectangle((64, 72, 576, 432), fill="#eef8fb", outline="#081522", width=12)
    draw.rectangle((704, 72, 1216, 432), fill="#eef8fb", outline="#081522", width=12)
    image.save(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    scene = {
        "text_render_policy": "semantic_roles_v1", "screen_texts": list(texts),
        "screen_text_validation": {"passed": True},
        "screen_text_plan": [{"text": text, "surface": name, "purpose": "information"}
                             for text, name in zip(texts, ("left", "right"))],
        "surface_bindings": {
            "left": {"bbox": [.05, .1, .4, .5], "geometry": "axis_aligned_rect", "surface_kind": "board",
                     "image_sha256": sha, "validated": True},
            "right": {"bbox": [.55, .1, .4, .5], "geometry": "axis_aligned_rect", "surface_kind": "board",
                      "image_sha256": sha, "validated": True},
        },
    }
    return scene, path


def mock_plan(monkeypatch, texts):
    values = iter(text for text in texts for _ in (6, 7))
    monkeypatch.setattr(gate, "_read_tesseract_rows", lambda *a, **k: ("completed", [{"text": next(values)}]))


def test_trend_cells_do_not_overlap_and_all_four_roles_reach_gate(tmp_path, monkeypatch):
    scene, path = trend_file(tmp_path)
    cells = validate_manifest(scene, (1280, 720))
    assert len(cells) == 4
    mock_cells(monkeypatch, scene)
    report = gate.inspect_final_frame_text_integrity(str(path), scene)
    assert report["ocr_passed"] is True
    assert {r["cell_id"] for r in report["region_comparisons"]} == {c["id"] for c in cells}


def test_trend_endpoint_ocr_cell_does_not_contain_graph_ink(tmp_path):
    scene, path = trend_file(tmp_path)
    end_cell = next(cell for cell in scene["surface_text_manifest"]["cells"] if cell["role"] == "end_value")
    with Image.open(path) as image:
        colors = set(image.convert("RGB").crop(end_cell["bbox"]).getdata())
    assert (255, 204, 66) not in colors  # 추세선/화살표
    assert (20, 176, 197) not in colors  # 추세선 외곽광
    assert end_cell["psm_modes"] == [6, 7]


def test_single_line_overlay_label_uses_the_measured_line_mode(tmp_path):
    scene, _ = trend_file(tmp_path)
    label = next(cell for cell in scene["surface_text_manifest"]["cells"] if cell["role"] == "label")
    assert label["psm_modes"] == [7]


def test_non_trend_label_keeps_both_existing_modes(tmp_path):
    scene = {
        "verified_facts": [{"figure": "PER 4배", "fact": "PER은 4배다."}],
        "v5_verified_overlays": [{"label": "PER", "value": "4배", "source_ref": "facts[0]",
                                  "anchor": {"x": .1, "y": .1, "width": .4, "height": .4, "kind": "monitor"}}],
    }
    stream = io.BytesIO()
    Image.new("RGB", (1280, 720), "#20354d").save(stream, "PNG")
    apply_verified_scene_facts(stream.getvalue(), scene)
    label = next(cell for cell in scene["surface_text_manifest"]["cells"] if cell["role"] == "label")
    assert label["psm_modes"] == [6, 7]


def test_wrong_endpoint_is_rejected_even_when_label_delta_and_start_match(tmp_path, monkeypatch):
    scene, path = trend_file(tmp_path)
    mock_cells(monkeypatch, scene, {"overlay:0:end_value": "12.75%"})
    report = gate.inspect_final_frame_text_integrity(str(path), scene)
    assert report["passed"] is False
    assert report["missing_or_altered"] == ["2.75%"]


@pytest.mark.parametrize("damage", ["missing", "duplicate", "stale", "frame", "swapped", "clipped", "mode", "malformed"])
def test_manifest_damage_fails_closed(tmp_path, damage):
    scene, path = trend_file(tmp_path)
    manifest = scene["surface_text_manifest"]
    cells = manifest["cells"]
    if damage == "missing":
        cells.pop()
    elif damage == "duplicate":
        cells[-1] = copy.deepcopy(cells[0])
    elif damage == "stale":
        scene["v5_verified_overlays"][0]["value"] = "0.50%p"
    elif damage == "frame":
        manifest["frame_size"][0] = 1920
    elif damage == "swapped":
        cells[0]["anchor_bbox"] = [0, 0, 100, 100]
    elif damage == "clipped":
        cells[0]["bbox"][0] = -1
    elif damage == "mode":
        cells[0]["psm_modes"] = [6]
    else:
        cells[0] = None
    assert gate.inspect_final_frame_text_integrity(str(path), scene)["passed"] is False


def test_flat_ocr_injection_cannot_claim_location(tmp_path):
    scene, path = trend_file(tmp_path)
    rows = [{"text": text} for text in gate.expected_final_frame_texts(scene)]
    report = gate.inspect_final_frame_text_integrity(str(path), scene, ocr_rows=rows)
    assert report["status"] == "spatial_ocr_required"
    assert report["passed"] is False


def test_one_correct_psm_cannot_hide_other_wrong_observation(tmp_path, monkeypatch):
    scene, path = trend_file(tmp_path)
    values = [cell["text"] for cell in scene["surface_text_manifest"]["cells"] for _ in (6, 7)]
    values[5] = "12.75%"
    sequence = iter(values)
    monkeypatch.setattr(gate, "_read_tesseract_rows", lambda *a, **k: ("completed", [{"text": next(sequence)}]))
    assert gate.inspect_final_frame_text_integrity(str(path), scene)["passed"] is False


def test_semantic_numeric_surface_still_uses_upstream_fact_gate(tmp_path, monkeypatch):
    scene, path = bound_scene(tmp_path)
    scene.update(trend_scene())
    scene["screen_texts"] = ["인상폭", "0.25%p", "2.50%", "2.75%"]
    scene["screen_text_plan"] = []
    # 실제 픽셀로 검증 가능한 왼쪽 패널 안에 수치 오버레이를 둔다.
    scene["v5_verified_overlays"][0]["surface"] = "left"
    scene["v5_verified_overlays"][0]["anchor"] = {
        "x": .07, "y": .12, "width": .36, "height": .36, "kind": "monitor",
    }
    original = path.read_bytes()
    invalid = copy.deepcopy(scene)
    invalid["v5_verified_overlays"][0]["value"] = "0.5%p"
    with pytest.raises(ValueError):
        render_semantic_surface_text(invalid, str(path))
    assert path.read_bytes() == original
    expected = copy.deepcopy(scene)
    apply_verified_scene_facts(original, expected)
    mock_cells(monkeypatch, expected)
    render_semantic_surface_text(scene, str(path))
    assert len(scene["surface_text_manifest"]["cells"]) == 4


def test_missing_plan_cannot_be_reported_as_not_applicable(tmp_path):
    scene, path = bound_scene(tmp_path)
    scene["screen_text_plan"] = []
    report = gate.inspect_final_frame_text_integrity(str(path), scene)
    assert report["passed"] is False
    assert report["status"] == "invalid_surface_contract"


@pytest.mark.parametrize("swapped", [False, True])
def test_two_surfaces_require_their_own_strings(tmp_path, monkeypatch, swapped):
    scene, path = bound_scene(tmp_path)
    original, before = path.read_bytes(), copy.deepcopy(scene)
    texts = scene["screen_texts"][::-1] if swapped else scene["screen_texts"]
    mock_plan(monkeypatch, texts)
    if swapped:
        with pytest.raises(gate.FinalFrameTextIntegrityError):
            render_semantic_surface_text(scene, str(path))
        assert path.read_bytes() == original and scene == before
    else:
        render_semantic_surface_text(scene, str(path))
        assert scene["final_frame_text_integrity"]["passed"] is True


def test_repeat_text_is_not_deduplicated_between_surfaces(tmp_path, monkeypatch):
    scene, path = bound_scene(tmp_path, ("전망", "전망"))
    mock_plan(monkeypatch, ("전망", "전망"))
    render_semantic_surface_text(scene, str(path))
    assert len(scene["surface_text_manifest"]["cells"]) == 2


@pytest.mark.parametrize("damage", ["hash", "geometry", "missing", "overlap", "numeric"])
def test_bad_binding_or_ungrounded_number_does_not_overwrite(tmp_path, monkeypatch, damage):
    scene, path = bound_scene(tmp_path)
    if damage == "hash":
        scene["surface_bindings"]["left"]["image_sha256"] = "stale"
    elif damage == "geometry":
        scene["surface_bindings"]["left"]["geometry"] = "planar_quad"
    elif damage == "missing":
        scene["screen_text_plan"].pop()
    elif damage == "overlap":
        scene["surface_bindings"]["right"]["bbox"] = scene["surface_bindings"]["left"]["bbox"]
    else:
        scene["screen_texts"][0] = "14배"
        scene["screen_text_plan"][0]["text"] = "14배"
    original, before = path.read_bytes(), copy.deepcopy(scene)
    with pytest.raises(ValueError):
        render_semantic_surface_text(scene, str(path))
    assert path.read_bytes() == original and scene == before


def test_resume_checks_ocr_again_without_redrawing(tmp_path, monkeypatch):
    scene, path = bound_scene(tmp_path)
    mock_plan(monkeypatch, scene["screen_texts"])
    render_semantic_surface_text(scene, str(path))
    first = path.read_bytes()
    mock_plan(monkeypatch, scene["screen_texts"])
    render_semantic_surface_text(scene, str(path))
    assert path.read_bytes() == first
    mock_plan(monkeypatch, ("거짓 전망", "수정 전망"))
    with pytest.raises(gate.FinalFrameTextIntegrityError):
        render_semantic_surface_text(scene, str(path))
    assert path.read_bytes() == first


def test_numeric_decoration_cannot_escape_information_route():
    scene = {"text_render_policy": "semantic_roles_v1", "screen_texts": ["4배", "와!"],
             "screen_text_validation": {"passed": True},
             "screen_text_plan": [
                 {"text": "4배", "purpose": "decorative", "surface_id": "metric_board"},
                 {"text": "와!", "purpose": "decorative", "surface_id": "reaction_badge"},
             ]}
    route = build_scene_text_contract(scene)
    assert [r["purpose"] for r in route["semantic_routing"]] == ["information", "decorative"]
    assert route["generated_texts"] == []
    assert route["semantic_routing"][1]["reason"] == "decoration_size_calibration_pending"


def test_plan_cannot_approve_its_own_new_text():
    with pytest.raises(ValueError):
        build_scene_text_contract({"text_render_policy": "semantic_roles_v1", "screen_texts": ["영업이익"],
                                   "screen_text_validation": {"passed": True},
                                   "screen_text_plan": [{"text": "비영업이익"}]})


def test_runtime_contract_uses_same_semantic_routing():
    result = plan_v5_scene_contract({"text_render_policy": "semantic_roles_v1",
                                    "scene_type": "general",
                                    "screen_texts": ["영업이익", "KOSPI"],
                                    "screen_text_validation": {"passed": True},
                                    "narration": "반도체 공장에서 이익의 흐름을 살펴봅니다."}, 0)
    assert result["surface_caption"]["generated_texts"] == []
    assert result["surface_caption"]["deterministic_texts"] == ["영업이익", "KOSPI"]
    assert result["source_visual_text_policy"] == "strict_textless"
    assert result["visual_text_policy"] == "deterministic_surface_text"


def test_multiple_texts_share_one_surface_only_with_explicit_non_overlapping_regions(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.semantic_surface_text.attest_scene_surfaces", lambda *args: None)
    scene, path = bound_scene(tmp_path, ("삼성전자", "SK하이닉스"))
    scene["surface_bindings"] = {"left": scene["surface_bindings"]["left"]}
    scene["screen_text_plan"] = [
        {"text": "삼성전자", "surface": "left", "purpose": "information",
         "region": [.05, .10, .90, .34]},
        {"text": "SK하이닉스", "surface": "left", "purpose": "information",
         "region": [.05, .56, .90, .34]},
    ]
    mock_plan(monkeypatch, scene["screen_texts"])
    render_semantic_surface_text(scene, str(path))
    cells = validate_manifest(scene, (1280, 720))
    assert len(cells) == 2
    assert cells[0]["anchor_bbox"] != cells[1]["anchor_bbox"]
    assert cells[0]["bbox"][3] < cells[1]["bbox"][1]


def test_numeric_plan_value_requires_exact_scene_local_verified_fact(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.semantic_surface_text.attest_scene_surfaces", lambda *args: None)
    scene, path = bound_scene(tmp_path, ("4배", "현재 전망"))
    scene["screen_text_plan"][0].update(source_ref="facts[0]")
    scene["verified_facts"] = [{"figure": "PER 14배", "fact": "현재 장면은 PER 14배다."}]
    original = path.read_bytes()
    with pytest.raises(ValueError, match="검증 사실"):
        render_semantic_surface_text(scene, str(path))
    assert path.read_bytes() == original

    scene["verified_facts"] = [{"figure": "PER 4배", "fact": "현재 장면은 PER 4배다."}]
    mock_plan(monkeypatch, scene["screen_texts"])
    render_semantic_surface_text(scene, str(path))
    assert scene["final_frame_text_integrity"]["passed"] is True

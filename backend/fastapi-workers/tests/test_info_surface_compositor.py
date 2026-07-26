from pathlib import Path
import hashlib

import numpy as np
from PIL import Image
import pytest

cv2 = pytest.importorskip("cv2")

from app.services.info_surface.contracts import InfoItem, InfoSurfacePlan, SurfaceContract
from app.services.info_surface.detector import detect_surface_quad
from app.services.info_surface.warp_compositor import composite_planar, diegetic_supersample_factor, render_data_cutaway
from app.workers.images_worker import ImagesWorker
from app.workers.longform_worker import _ffmpeg_static_image


def _input():
    image = np.full((540, 960, 3), (34, 48, 61), dtype=np.uint8)
    marker = (224, 208, 174); border = (72, 48, 30)
    quad = np.array([[540, 100], [860, 130], [820, 410], [510, 370]], np.int32)
    cv2.fillConvexPoly(image, quad, border[::-1])
    inner = np.array([[550, 111], [849, 139], [811, 399], [520, 360]], np.int32)
    cv2.fillConvexPoly(image, inner, marker[::-1])
    cv2.line(image, (680, 80), (700, 430), (12, 12, 12), 8)
    return image, marker, border


def test_diegetic_supersample_is_derived_from_quad_size():
    logical = (1427, 1239)
    large = np.array([[300, 100], [1700, 100], [1700, 950], [300, 950]], dtype=np.float32)
    small = np.array([[500, 200], [900, 200], [900, 500], [500, 500]], dtype=np.float32)
    large_result = diegetic_supersample_factor(logical, large, text_candidates=("수령",))
    small_result = diegetic_supersample_factor(logical, small, text_candidates=("수령",))
    assert large_result["factor"] < small_result["factor"]
    assert large_result["final_output_scale"] > small_result["final_output_scale"]


def test_warp_keeps_chain_above_verified_ink():
    source, marker, border = _input()
    contract = SurfaceContract(surface_kind="hanging_tag", marker_rgb=marker, border_rgb=border, area_ratio_min=.05, area_ratio_max=.35, preferred_region={"x": .45, "y": .10, "width": .48, "height": .72})
    detection = detect_surface_quad(source, contract)
    assert detection is not None
    plan = InfoSurfacePlan(scene_id="fixture", render_mode="DIEGETIC_WARP", surface=contract, items=[InfoItem(item_id="chart", role="chart")])
    chart = {"verified": True, "source_ref": "fixture", "visual_kind": "indexed_comparison", "label": "비용 지수", "comparison_baseline": 100, "comparison_basis": "2026-07-21 = 100", "comparison_values": [{"label": "기준", "value": 100}, {"label": "상한", "value": 110}]}
    result = composite_planar(Image.fromarray(cv2.cvtColor(source, cv2.COLOR_BGR2RGB)), chart, plan, detection)
    # The vertical chain remains dark at its center after composition.
    assert max(result.convert("RGB").getpixel((690, 240))) < 75


def test_data_cutaway_is_a_full_size_one_to_one_replacement():
    image = render_data_cutaway({"verified": True, "source_ref": "fixture", "visual_kind": "indexed_comparison", "label": "비용", "comparison_basis": "2026-07-21 = 100", "comparison_values": [{"label": "A", "value": 100}, {"label": "B", "value": 110}]})
    assert image.size == (1920, 1080)


def test_images_worker_bakes_verified_chart_before_longform(tmp_path):
    source, marker, border = _input()
    source = cv2.resize(source, (1920, 1080))
    path = tmp_path / "scene.png"
    Image.fromarray(cv2.cvtColor(source, cv2.COLOR_BGR2RGB)).save(path)
    scene = {
        "index": 4,
        "market_chart": {"verified": True, "source": "fixture", "source_ref": "fixture", "visual_kind": "indexed_comparison", "label": "비용", "comparison_baseline": 100, "comparison_basis": "2026-07-21 = 100", "comparison_values": [{"label": "기준", "value": 100}, {"label": "상한", "value": 110}]},
        "art_direction": {"surface_contract": {"surface_kind": "hanging_tag", "geometry": "planar_quad", "marker_rgb": marker, "border_rgb": border, "area_ratio_min": .05, "area_ratio_max": .35, "preferred_region": {"x": .45, "y": .10, "width": .48, "height": .72}}},
    }
    direct = detect_surface_quad(cv2.cvtColor(np.asarray(Image.open(path).convert("RGB")), cv2.COLOR_RGB2BGR), SurfaceContract.model_validate(scene["art_direction"]["surface_contract"]))
    assert direct is not None
    ImagesWorker()._apply_image_overlays(scene, str(path))
    assert scene["final_image_path"] == str(path)
    assert scene["info_surface_plan"]["render_mode"] == "DIEGETIC_WARP"
    assert scene["info_surface_plan"]["detection"]["confidence"] >= .55


def test_resume_recomposes_from_preserved_source_when_chart_changes(tmp_path):
    source, marker, border = _input()
    source = cv2.resize(source, (1920, 1080))
    path = tmp_path / "scene.png"
    Image.fromarray(cv2.cvtColor(source, cv2.COLOR_BGR2RGB)).save(path)
    scene = {
        "index": 5,
        "market_chart": {
            "verified": True, "source": "fixture", "source_ref": "fixture",
            "visual_kind": "indexed_comparison", "label": "cost",
            "comparison_baseline": 100,
            "comparison_basis": "2026-07-21 = 100",
            "comparison_values": [{"label": "base", "value": 100}, {"label": "after", "value": 110}],
        },
        "art_direction": {"surface_contract": {
            "surface_kind": "hanging_tag", "geometry": "planar_quad", "marker_rgb": marker,
            "border_rgb": border, "area_ratio_min": .05, "area_ratio_max": .35,
            "preferred_region": {"x": .45, "y": .10, "width": .48, "height": .72},
        }},
    }
    worker = ImagesWorker()
    worker._apply_image_overlays(scene, str(path))
    source_path = Path(scene["source_image_path"])
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    first_final_hash = scene["info_surface_final_sha256"]

    # A changed verified payload must invalidate only the final render, never
    # use the prior warped PNG as its new source.
    scene["market_chart"]["comparison_values"][1]["value"] = 135
    worker._apply_image_overlays(scene, str(path))
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_hash
    assert scene["info_surface_final_sha256"] != first_final_hash
    assert scene["final_image_path"] == str(path)
    assert len(scene["info_surface_plan"]["render_attempts"]) == 2


def test_non_planar_chart_replaces_scene_with_one_to_one_cutaway(tmp_path):
    path = tmp_path / "scene.png"
    Image.new("RGB", (1920, 1080), "#123456").save(path)
    scene = {
        "index": 6,
        "market_chart": {
            "verified": True, "source": "fixture", "source_ref": "fixture",
            "visual_kind": "indexed_comparison", "label": "cost",
            "comparison_basis": "2026-07-21 = 100",
            "comparison_values": [{"label": "base", "value": 100}, {"label": "after", "value": 110}],
        },
        "art_direction": {"surface_contract": {
            "surface_kind": "map_cloud", "geometry": "irregular_mask",
        }},
    }
    ImagesWorker()._apply_image_overlays(scene, str(path))
    plan = scene["info_surface_plan"]
    assert plan["render_mode"] == "DATA_CUTAWAY"
    assert plan["timeline_mode"] == "one_to_one_replace"
    assert plan["replacement_of_scene_id"] == "6"
    assert plan["render_attempts"][-1]["outcome"] == "DATA_CUTAWAY"
    assert scene["source_image_path"] != scene["final_image_path"]


def test_partial_legacy_surface_contract_still_uses_chart_fallback(tmp_path):
    path = tmp_path / "scene.png"
    Image.new("RGB", (1920, 1080), "#123456").save(path)
    scene = {
        "index": 7,
        "market_chart": {
            "verified": True, "source": "fixture", "source_ref": "fixture",
            "visual_kind": "indexed_comparison", "label": "cost",
            "comparison_basis": "2026-07-21 = 100",
            "comparison_values": [{"label": "base", "value": 100}, {"label": "after", "value": 110}],
        },
        # An older job may have named a planar prop but omitted its marker.
        "art_direction": {"surface_contract": {"surface_kind": "monitor", "geometry": "planar_quad"}},
    }
    ImagesWorker()._apply_image_overlays(scene, str(path))
    assert scene["info_surface_plan"]["render_mode"] == "DATA_CUTAWAY"


def test_small_detected_chart_surface_uses_1080p_readability_fallback(tmp_path):
    marker = (224, 208, 174); border = (72, 48, 30)
    image = np.full((1080, 1920, 3), (34, 48, 61), dtype=np.uint8)
    cv2.rectangle(image, (1300, 130), (1600, 340), border[::-1], -1)
    cv2.rectangle(image, (1308, 138), (1592, 332), marker[::-1], -1)
    path = tmp_path / "scene.png"
    Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).save(path)
    scene = {
        "index": 8,
        "market_chart": {"verified": True, "source": "fixture", "source_ref": "fixture", "visual_kind": "indexed_comparison", "label": "cost", "comparison_basis": "2026-07-21 = 100", "comparison_values": [{"label": "base", "value": 100}, {"label": "after", "value": 110}]},
        "art_direction": {"surface_contract": {"surface_kind": "tag", "geometry": "planar_quad", "marker_rgb": marker, "border_rgb": border, "area_ratio_min": .01, "area_ratio_max": .05, "preferred_region": {"x": .65, "y": .10, "width": .20, "height": .25}}},
    }
    ImagesWorker()._apply_image_overlays(scene, str(path))
    plan = scene["info_surface_plan"]
    assert plan["render_mode"] == "DATA_CUTAWAY"
    assert "surface_too_small_for_1080p_type" in plan["fallback_chain"]


def test_final_1080p_encoded_frame_retains_baked_chart_ink(tmp_path):
    source, marker, border = _input()
    source = cv2.resize(source, (1920, 1080))
    path = tmp_path / "scene.png"
    Image.fromarray(cv2.cvtColor(source, cv2.COLOR_BGR2RGB)).save(path)
    scene = {
        "index": 9,
        "market_chart": {"verified": True, "source": "fixture", "source_ref": "fixture", "visual_kind": "indexed_comparison", "label": "cost", "comparison_baseline": 100, "comparison_basis": "2026-07-21 = 100", "comparison_values": [{"label": "base", "value": 100}, {"label": "after", "value": 110}]},
        "art_direction": {"surface_contract": {"surface_kind": "hanging_tag", "geometry": "planar_quad", "marker_rgb": marker, "border_rgb": border, "area_ratio_min": .05, "area_ratio_max": .35, "preferred_region": {"x": .45, "y": .10, "width": .48, "height": .72}}},
    }
    ImagesWorker()._apply_image_overlays(scene, str(path))
    assert scene["info_surface_plan"]["render_mode"] == "DIEGETIC_WARP"
    clip = tmp_path / "clip.mp4"
    _ffmpeg_static_image(str(path), str(clip), .35, job_id=0)
    capture = cv2.VideoCapture(str(clip))
    ok, frame = capture.read()
    capture.release()
    assert ok and frame.shape[:2] == (1080, 1920)
    original = cv2.cvtColor(np.asarray(Image.open(scene["source_image_path"]).convert("RGB")), cv2.COLOR_RGB2BGR)
    # The warped ink differs materially from the original physical prop even
    # after yuv420p encoding; it is not a later fixed-coordinate overlay.
    assert np.mean(np.abs(frame.astype(np.int16) - original.astype(np.int16))) > 1.0

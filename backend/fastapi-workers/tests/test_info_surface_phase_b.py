import cv2
import numpy as np

from app.services.info_surface.phase_b.contracts import BarSpec, ExpectedText, HarmonizeRequest
from app.services.info_surface.phase_b.gates import bar_geometry_gate, edge_iou_gate, palette_gate, run_all_gates, text_integrity_gate
from app.services.info_surface.phase_b.harmonizer import harmonize_surface
from app.services.info_surface.phase_b.ocr_readers import MockReader
from app.services.info_surface.phase_b.providers import IdentityProvider, ProviderResult

NAVY = (58, 26, 7); CREAM = (232, 248, 255); YELLOW = (48, 210, 255)
PALETTE = [(7, 26, 58), (255, 248, 232), (255, 210, 48), (255, 81, 72)]


def _board(heights=(120, 86), size=(320, 420)):
    height, width = size; image = np.full((height, width, 3), CREAM, np.uint8); bars = []; x = 60
    for value in heights:
        y = height - 60 - value
        cv2.rectangle(image, (x, y), (x + 90, height - 60), YELLOW, -1); cv2.rectangle(image, (x, y), (x + 90, height - 60), NAVY, 5)
        bars.append(BarSpec(bbox=(x - 5, 40, 100, height - 100), value=float(value), fill_rgb=(255, 210, 48))); x += 150
    return image, bars


def _request(bars):
    return HarmonizeRequest(scene_id="fixture", surface_kind="paper", crop_bbox_in_frame=(100, 80, 420, 320), expected_texts=[ExpectedText(text="Transport cost")], bars=bars, palette_rgb=PALETTE, style_prompt="inked paper")


def test_text_gate_passes_exact_text_and_rejects_numeric_change():
    expected = [ExpectedText(text="+7.0%")]
    assert text_integrity_gate(np.zeros((4, 4, 3), np.uint8), expected, MockReader(["+7.0%"])).passed
    assert not text_integrity_gate(np.zeros((4, 4, 3), np.uint8), expected, MockReader(["+7.8%"])).passed


def test_text_gate_allows_only_whitespace_normalization():
    assert text_integrity_gate(np.zeros((4, 4, 3), np.uint8), [ExpectedText(text="Base index 100")], MockReader(["Base  index\n100"])).passed


def test_bar_gate_accepts_same_geometry():
    image, bars = _board(); assert bar_geometry_gate(image, image.copy(), bars).passed


def test_bar_gate_rejects_ratio_drift():
    original, bars = _board((120, 86)); changed, _ = _board((120, 104)); assert not bar_geometry_gate(original, changed, bars).passed


def test_bar_gate_skips_single_bar():
    image, bars = _board((120,)); assert bar_geometry_gate(image, image, bars).passed


def test_palette_gate_rejects_off_token_colour():
    image, _ = _board(); image[:, :200] = (200, 60, 160); assert not palette_gate(image, PALETTE).passed


def test_edge_gate_rejects_melted_structure():
    image, _ = _board(); assert not edge_iou_gate(image, cv2.GaussianBlur(image, (31, 31), 12)).passed


def test_shape_mismatch_fails_before_other_gates():
    image, _ = _board(); gates = run_all_gates(image, image[:-2], expected_texts=[], bars=[], palette_rgb=PALETTE, reader=MockReader([])); assert len(gates) == 1 and not gates[0].passed


def test_harmonizer_accepts_dry_run_and_only_changes_crop():
    frame = np.full((600, 900, 3), NAVY, np.uint8); board, bars = _board(); frame[80:400, 100:520] = board
    result, final = harmonize_surface(_request(bars), frame, IdentityProvider(), MockReader(["Transport cost"]))
    assert result.accepted and np.array_equal(final[500:], frame[500:])


def test_harmonizer_falls_back_on_gate_failure_and_provider_error():
    frame = np.full((600, 900, 3), NAVY, np.uint8); board, bars = _board(); frame[80:400, 100:520] = board
    rejected, returned = harmonize_surface(_request(bars), frame, IdentityProvider(), MockReader(["Transport 89%"])); assert not rejected.accepted and np.array_equal(returned, frame)
    class Boom:
        def stylize(self, *_): raise RuntimeError("503")
    errored, returned = harmonize_surface(_request([]), frame, Boom(), MockReader([])); assert not errored.accepted and "provider_error" in errored.fallback_reason and np.array_equal(returned, frame)


def test_composite_mask_limits_accepted_paste():
    frame = np.full((300, 300, 3), 255, np.uint8); frame[50:250, 50:250] = CREAM
    request = _request([]).model_copy(update={"crop_bbox_in_frame": (50, 50, 200, 200), "expected_texts": []})
    mask = np.zeros((300, 300), bool); mask[100:150, 100:150] = True
    result, final = harmonize_surface(request, frame, IdentityProvider(), MockReader([]), composite_mask_full=mask)
    outside = np.ones((300, 300), bool); outside[100:150, 100:150] = False
    assert result.accepted and np.array_equal(final[outside], frame[outside])

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from app.services.info_surface.contracts import SurfaceContract
from app.services.info_surface.detector import detect_surface_quad


MARKER = (224, 208, 174)
BORDER = (72, 48, 30)


def _scene(*, chain=False, texture=False):
    image = np.full((600, 1000, 3), (35, 48, 60), dtype=np.uint8)
    # Four cream props reproduce the real sephia collision risk. Only the
    # upper-right marker has the required dark border and preferred placement.
    for x, y, w, h in ((60, 50, 160, 130), (80, 300, 175, 125), (420, 80, 170, 130), (660, 100, 230, 210)):
        cv2.rectangle(image, (x, y), (x + w, y + h), BORDER, -1)
        cv2.rectangle(image, (x + 8, y + 8), (x + w - 8, y + h - 8), MARKER[::-1], -1)
    if texture:
        rng = np.random.default_rng(22)
        for x, y in rng.integers([670, 110], [875, 300], size=(120, 2)):
            cv2.circle(image, (int(x), int(y)), 1, (180, 165, 140), -1)
    if chain:
        cv2.line(image, (760, 92), (790, 320), (15, 15, 15), 9)
    return image


def _contract():
    return SurfaceContract(
        surface_kind="hanging_tag", marker_rgb=MARKER, border_rgb=BORDER,
        area_ratio_min=.02, area_ratio_max=.20, preferred_side="right",
        preferred_region={"x": .60, "y": .06, "width": .34, "height": .56},
    )


def _rounded_rect(image, start, end, radius, color):
    """OpenCV 빌드 차이와 무관하게 채워진 둥근 사각형을 만든다."""
    x1, y1 = start; x2, y2 = end
    cv2.rectangle(image, (x1 + radius, y1), (x2 - radius, y2), color, -1)
    cv2.rectangle(image, (x1, y1 + radius), (x2, y2 - radius), color, -1)
    for point in ((x1 + radius, y1 + radius), (x2 - radius, y1 + radius), (x1 + radius, y2 - radius), (x2 - radius, y2 - radius)):
        cv2.circle(image, point, radius, color, -1)


def test_four_cream_surfaces_selects_the_bordered_right_tag():
    detection = detect_surface_quad(_scene(), _contract())
    assert detection is not None
    center = detection.quad.mean(axis=0)
    assert center[0] > 700
    assert detection.confidence >= .55


def test_metal_border_passes_by_contrast_when_the_color_hint_differs():
    """테두리 색상 힌트가 달라도 실제 물리적 경계 대비로 표면을 선택한다."""
    image = np.full((600, 1000, 3), (38, 35, 30), dtype=np.uint8)
    # 생성 모델이 금고에 자연스럽게 붙이는 금속 갈색 테두리(RGB 128/93/74).
    cv2.rectangle(image, (660, 100), (890, 310), (74, 93, 128), -1)
    cv2.rectangle(image, (668, 108), (882, 302), MARKER[::-1], -1)
    contract = SurfaceContract(
        surface_kind="vault_panel", marker_rgb=MARKER,
        # 기존 채널 남색은 선택적 힌트일 뿐, 다른 금속 테두리를 감점하지 않는다.
        border_rgb=(7, 26, 58), area_ratio_min=.02, area_ratio_max=.20,
        preferred_side="right", preferred_region={"x": .60, "y": .06, "width": .34, "height": .56},
    )
    detection = detect_surface_quad(image, contract)
    assert detection is not None
    assert detection.border_match >= .65
    assert detection.quad.mean(axis=0)[0] > 700


def test_rounded_physical_board_is_accepted_as_a_planar_quad():
    """생성 모델의 둥근 실물 보드는 평면 워프 후보로 유지한다."""
    image = np.full((600, 1000, 3), (38, 35, 30), dtype=np.uint8)
    _rounded_rect(image, (660, 100), (890, 310), 28, (74, 93, 128))
    _rounded_rect(image, (668, 108), (882, 302), 22, MARKER[::-1])
    contract = SurfaceContract(
        surface_kind="vault_panel", marker_rgb=MARKER, border_rgb=(7, 26, 58),
        area_ratio_min=.02, area_ratio_max=.20, preferred_side="right",
        preferred_region={"x": .60, "y": .06, "width": .34, "height": .56},
    )
    detection = detect_surface_quad(image, contract)
    assert detection is not None
    assert detection.quad.mean(axis=0)[0] > 700


def test_texture_only_does_not_become_occlusion():
    detection = detect_surface_quad(_scene(texture=True), _contract())
    assert detection is not None
    assert np.count_nonzero(detection.occluder_mask) == 0


def test_chain_crossing_is_retained_as_a_real_occluder():
    detection = detect_surface_quad(_scene(chain=True), _contract())
    assert detection is not None
    assert np.count_nonzero(detection.occluder_mask) > 500


def test_marker_edge_antialiasing_is_not_treated_as_occlusion():
    image = _scene()
    # A one-pixel shaded inner border is normal raster anti-aliasing, not a
    # foreground object.  The detector excludes the two-pixel quad interior
    # boundary before connected-component filtering.
    cv2.rectangle(image, (668, 108), (882, 302), (180, 165, 140), 1)
    detection = detect_surface_quad(image, _contract())
    assert detection is not None
    assert np.count_nonzero(detection.occluder_mask) == 0

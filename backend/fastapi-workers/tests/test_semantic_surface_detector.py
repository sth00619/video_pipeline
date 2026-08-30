from pathlib import Path

from PIL import Image, ImageDraw

from app.services.overlay.surface_detector import (
    SurfaceDetection,
    _candidate_matches_locator,
    _relative_subregion_detection,
    _surface_region_is_text_free,
)


def test_locator_rejects_large_unrelated_board_and_keeps_scale_base_candidate():
    board = SurfaceDetection(((.15, .10), (.85, .10), (.85, .55), (.15, .55)), .9, "opencv")
    plinth = SurfaceDetection(((.25, .76), (.51, .76), (.51, .91), (.25, .91)), .7, "opencv")
    locator = [.18, .62, .42, .36]

    assert _candidate_matches_locator(board, locator) is False
    assert _candidate_matches_locator(plinth, locator) is True


def test_shared_monitor_numeric_region_can_be_clear_when_parent_contains_a_label(tmp_path: Path):
    path = tmp_path / "monitor.png"
    image = Image.new("RGB", (1000, 700), "#173047")
    draw = ImageDraw.Draw(image)
    draw.rectangle((300, 90, 800, 540), fill="#dceaf0", outline="#07131f", width=12)
    draw.rectangle((340, 130, 760, 270), fill="#647d8a")
    # 위쪽 승인 라벨을 흉내 낸 선화. 아래 예약 영역은 비워 둔다.
    draw.line((420, 180, 680, 180), fill="#07131f", width=18)
    image.save(path)
    parent = SurfaceDetection(((.30, .13), (.80, .13), (.80, .77), (.30, .77)), .9, "opencv")

    child = _relative_subregion_detection(parent, [.08, .52, .84, .40])

    assert _surface_region_is_text_free(Path(path), child) is True

from PIL import Image, ImageDraw, ImageFont

from app.services.overlay import surface_detector as detector
from app.services.overlay.surface_detector import _sliding_blank_surface, detect_surface, detect_surface_quad


def test_surface_detector_returns_normalised_quad_for_blank_illustrated_panel(tmp_path):
    image = Image.new("RGB", (1000, 600), "#24415c")
    draw = ImageDraw.Draw(image)
    draw.rectangle((560, 90, 920, 350), fill="#e6c283", outline="#3c2d1c", width=8)
    source = tmp_path / "panel.png"
    image.save(source)

    result = detect_surface(str(source), "board")
    assert result is not None
    assert result.strategy in {"opencv", "heuristic"}
    assert detect_surface_quad(str(source), "board") == result.quad
    assert all(0 <= value <= 1 for point in result.quad for value in point)


def test_sliding_detector_finds_large_low_line_density_panel(tmp_path):
    source = tmp_path / "panel.png"
    image = Image.new("RGB", (1280, 720), "#15243b")
    draw = ImageDraw.Draw(image)
    draw.rectangle((110, 90, 540, 360), fill="#eef8fb", outline="#081522", width=10)
    draw.line((760, 80, 1180, 520), fill="#ff3344", width=18)
    image.save(source)

    result = _sliding_blank_surface(source)

    assert result is not None
    assert result.strategy == "heuristic"
    assert result.quad[0][0] < .20
    assert result.quad[0][1] < .30


def test_sliding_detector_uses_unoccluded_upper_band_of_scene_native_screen(tmp_path):
    source = tmp_path / "partly-occluded-panel.png"
    image = Image.new("RGB", (1280, 720), "#5b1720")
    draw = ImageDraw.Draw(image)
    draw.rectangle((165, 90, 525, 350), fill="#f4c7c7", outline="#20131a", width=10)
    # 캐릭터나 소품이 화면 하단을 가린 상황을 단순화한 마스크다.
    draw.ellipse((265, 190, 505, 470), fill="#d9a52d", outline="#20131a", width=12)
    image.save(source)

    result = _sliding_blank_surface(source)

    assert result is not None
    assert result.quad[0][0] < .20
    assert result.quad[2][1] <= .32


def test_surface_detector_rejects_panel_that_already_contains_large_text(tmp_path):
    source = tmp_path / "labeled-panel.png"
    image = Image.new("RGB", (1280, 720), "#15243b")
    draw = ImageDraw.Draw(image)
    draw.rectangle((110, 90, 600, 390), fill="#eef8fb", outline="#081522", width=12)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 58)
    draw.text((145, 185), "90-110", font=font, fill="#081522", stroke_width=3)
    image.save(source)

    assert detect_surface(str(source), "board", job_id=None) is None


def test_surface_detector_rejects_bright_open_background_without_physical_border(tmp_path):
    source = tmp_path / "open-background.png"
    Image.new("RGB", (1280, 720), "#eef8fb").save(source)

    assert detect_surface(str(source), "board", job_id=None) is None


def test_surface_detector_chooses_highest_confidence_safe_candidate(tmp_path, monkeypatch):
    source = tmp_path / "two-candidates.png"
    image = Image.new("RGB", (1280, 720), "#15243b")
    draw = ImageDraw.Draw(image)
    draw.rectangle((760, 100, 1080, 300), fill="#eef8fb", outline="#081522", width=12)
    image.save(source)

    low = detector.SurfaceDetection(((.10, .60), (.40, .60), (.40, .80), (.10, .80)), .405, "opencv")
    high = detector.SurfaceDetection(((.60, .14), (.84, .14), (.84, .42), (.60, .42)), .656, "heuristic")
    monkeypatch.setattr(detector, "_opencv_quad", lambda _path: low)
    monkeypatch.setattr(detector, "_heuristic_quad", lambda _path: None)
    monkeypatch.setattr(detector, "_sliding_blank_surface", lambda _path: high)
    monkeypatch.setattr(detector, "_surface_is_text_free", lambda _path, _candidate: True)

    result = detect_surface(str(source), "board", job_id=None)

    assert result == high


def test_vision_surface_is_cached_by_source_hash_and_reused_without_second_call(tmp_path, monkeypatch):
    source = tmp_path / "vision-panel.png"
    image = Image.new("RGB", (1280, 720), "#15243b")
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 100, 560, 330), fill="#eef8fb", outline="#081522", width=12)
    image.save(source)

    monkeypatch.setattr(detector, "_opencv_quad", lambda _path: None)
    monkeypatch.setattr(detector, "_heuristic_quad", lambda _path: None)
    monkeypatch.setattr(detector, "_sliding_blank_surface", lambda _path: None)
    monkeypatch.setattr(detector, "can_charge_overlay_vision", lambda _job, _key: True)
    monkeypatch.setattr(detector, "record_cost", lambda *_args, **_kwargs: {})
    calls = []

    def resolve(_path, _kind):
        calls.append(_path)
        return (((.127, .156), (.428, .156), (.428, .442), (.127, .442)), .91)

    first = detect_surface(str(source), "board", job_id=54, scene_key="scene:1", vision_resolver=resolve)
    second = detect_surface(
        str(source), "board", job_id=54, scene_key="scene:1",
        vision_resolver=lambda *_args: (_ for _ in ()).throw(AssertionError("캐시를 재사용해야 함")),
    )

    assert first is not None
    assert second == first
    assert len(calls) == 1
    assert source.with_name(source.name + ".surface-detection.json").is_file()

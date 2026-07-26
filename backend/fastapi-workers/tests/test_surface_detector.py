from PIL import Image, ImageDraw

from app.services.overlay.surface_detector import detect_surface, detect_surface_quad


def test_surface_detector_returns_normalised_quad_for_blank_illustrated_panel(tmp_path):
    image = Image.new("RGB", (1000, 600), "#24415c")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((560, 90, 920, 350), radius=18, fill="#e6c283", outline="#3c2d1c", width=8)
    source = tmp_path / "panel.png"
    image.save(source)

    result = detect_surface(str(source), "board")
    assert result is not None
    assert result.strategy in {"opencv", "heuristic"}
    assert detect_surface_quad(str(source), "board") == result.quad
    assert all(0 <= value <= 1 for point in result.quad for value in point)

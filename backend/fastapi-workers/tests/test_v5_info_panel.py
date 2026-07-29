"""P1-c 정보 패널의 결정론적 렌더링 계약 테스트."""
import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.korean_overlay import InfoPanelSpec, VerifiedMetric, apply_info_panel


def test_info_panel_preserves_canvas_and_changes_pixels():
    base = Image.new("RGB", (1280, 720), "#334155")
    encoded = io.BytesIO()
    base.save(encoded, format="PNG")
    result = apply_info_panel(encoded.getvalue(), InfoPanelSpec(
        title="검증 패널", timestamp="테스트", metrics=(VerifiedMetric("값", "1", "테스트"),),
        chart_value=1.0, chart_max=2.0, source_note="테스트 근거",
    ))
    rendered = Image.open(io.BytesIO(result)).convert("RGB")
    assert rendered.size == (1280, 720)
    assert rendered.getpixel((70, 110)) != base.getpixel((70, 110))

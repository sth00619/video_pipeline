"""여러 물리 모니터에 흩어진 생성 문자 OCR 재현율 회귀."""
from pathlib import Path
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.fal_motion_safety import inspect_visible_text
from app.utils.image_text_contract import visible_text_contract_result


def _font_path() -> str:
    candidates = (
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    pytest.skip("한국어 Tesseract 재현 fixture용 Nanum 글꼴이 없습니다.")


def _multi_monitor_fixture(path: Path) -> None:
    """scene28처럼 축소 전체 OCR이 놓치는 기울어진 다중 표면을 만든다."""
    canvas = Image.new("RGB", (2752, 1536), (18, 28, 48))
    font = ImageFont.truetype(_font_path(), 112)
    plans = (
        ("대형주수", 14, (160, 100)),
        ("대형주수", -4, (1050, 250)),
        # 오른쪽 승인 표면은 정면에 가깝고, 왼쪽·가운데 이탈 표면은 서로
        # 다른 기울기를 가져 한 프레임의 다중 표면 경로를 함께 검증한다.
        ("대형주", 0, (1880, 100)),
    )
    for text, angle, position in plans:
        panel = Image.new("RGB", (620, 360), (218, 239, 242))
        draw = ImageDraw.Draw(panel)
        draw.rectangle((8, 8, 611, 351), outline=(35, 48, 70), width=16)
        draw.text(
            (70, 105), text, font=font, fill=(30, 45, 70),
            stroke_width=2, stroke_fill=(210, 80, 90),
        )
        # 차트 선이 글자 후보 분할을 방해하는 실제 장면의 조건을 보존한다.
        for x in range(40, 580, 55):
            draw.line((x, 280, x + 30, 210), fill=(220, 100, 120), width=5)
        rotated = panel.rotate(angle, expand=True, fillcolor=(18, 28, 48))
        canvas.paste(rotated, position)
    canvas.save(path)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract가 없습니다.")
def test_original_resolution_surface_recall_reads_suffix_variant_and_exact_label(tmp_path: Path):
    image_path = tmp_path / "multi-monitor.png"
    _multi_monitor_fixture(image_path)

    inspection = inspect_visible_text(
        str(image_path),
        expected_texts=["대형주"],
        targeted_exact_retry=True,
        surface_text_recall=True,
    )

    assert "대형주수" in inspection["visible_tokens"]
    assert inspection["exact_generated_texts"] == ["대형주"]
    assert inspection["surface_text_ocr_status"] == "completed"

    contract = visible_text_contract_result(inspection["visible_tokens"], {
        "screen_texts": ["대형주"],
        "generated_text_ocr_policy": {
            "version": "strict-scene-local-generated-text-v1",
            "require_all_approved": True,
            "reject_unapproved": True,
        },
    })
    assert contract["passed"] is False
    assert "대형주수" in contract["unexpected_texts"]

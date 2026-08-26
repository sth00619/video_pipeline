"""WO-IMG-01 4절 B의 5개 명세. 실제 OCR 대신 반환 행을 주입해 대조 로직을 검증한다.

회귀 테스트를 수정 코드보다 먼저 커밋한다. 앞의 두 사례는 기존 부분 문자열
검사에서 실패해야 하며, 나머지 세 사례는 유지해야 할 거절/공백 허용 동작이다.
"""
import pytest

from app.services.final_frame_text_integrity import (
    FinalFrameTextIntegrityError,
    inspect_final_frame_text_integrity,
    require_final_frame_text_integrity,
)


@pytest.mark.parametrize("expected,recognized,should_pass", [
    pytest.param("4배", "14배", False, id="reject-extra-digit"),
    pytest.param("영업이익", "비영업이익", False, id="reject-negating-prefix"),
    pytest.param("PER", "per", False, id="reject-case-change"),
    pytest.param("현재 전망", "현력 토공", False, id="reject-korean-typo"),
    pytest.param("143조 원", "143조\n원", True, id="allow-whitespace-only"),
])
def test_wo_img01_exact_text_spec(tmp_path, expected, recognized, should_pass):
    scene = {"v5_render_contract": {
        "visual_text_policy": "deterministic_surface_text",
        "surface_caption": {"texts": [expected]},
    }}
    # 파일이 없고 픽셀 계보도 없다. 실제 이미지/OCR/유료 공급자를 호출하지 않는다.
    image_path = str(tmp_path / "unused-fixture.png")
    rows = [{"text": recognized, "conf": "99"}]
    report = inspect_final_frame_text_integrity(image_path, scene, ocr_rows=rows)
    assert report["passed"] is should_pass
    if should_pass:
        assert require_final_frame_text_integrity(image_path, scene, ocr_rows=rows)["passed"]
    else:
        with pytest.raises(FinalFrameTextIntegrityError):
            require_final_frame_text_integrity(image_path, scene, ocr_rows=rows)

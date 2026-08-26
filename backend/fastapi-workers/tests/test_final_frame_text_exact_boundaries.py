"""정확 대조의 표면·재독 경계 회귀. OCR 응답만 대체하며 외부 호출은 금지한다."""
import hashlib
import socket

import pytest
from PIL import Image

from app.services import final_frame_text_integrity as gate


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("정확 대조 테스트에서 네트워크 호출 금지")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def caption(*texts):
    return {"v5_render_contract": {
        "visual_text_policy": "deterministic_surface_text",
        "surface_caption": {"texts": list(texts), "korean": "\n".join(texts)},
    }}


def panel(tmp_path):
    path = tmp_path / "panel.png"
    Image.new("RGB", (400, 200), "white").save(path)
    return str(path)


@pytest.mark.parametrize("expected,observed", [
    ("4배", "4배수"), ("-4%", "4%"), ("4.1%", "41%"),
    ("143조 원", "143억 원"), ("1,234", "1234"), ("PER", "PЕR"),
    ("영업이익", "영업이익 비영업이익"), ("영업이익", "영업"),
])
def test_does_not_normalize_financial_or_visual_changes(tmp_path, expected, observed):
    report = gate.inspect_final_frame_text_integrity(
        str(tmp_path / "unused.png"), caption(expected), ocr_rows=[{"text": observed}],
    )
    assert not report["passed"]
    assert not report["ocr_passed"]


def test_accepts_only_whitespace_changes_across_rows(tmp_path):
    report = gate.inspect_final_frame_text_integrity(
        str(tmp_path / "unused.png"), caption("143조 원"),
        ocr_rows=[{"text": "143"}, {"text": "조\t"}, {"text": "원"}],
    )
    assert report["passed"]
    assert report["verification_method"] == "ocr_exact"


def test_repeated_caption_must_not_disappear(tmp_path):
    scene = caption("PER", "PER")
    assert gate.expected_final_frame_texts(scene) == ["PER", "PER"]
    report = gate.inspect_final_frame_text_integrity(
        str(tmp_path / "unused.png"), scene, ocr_rows=[{"text": "PER"}],
    )
    assert not report["passed"]


@pytest.mark.parametrize("readings,should_pass", [
    ({6: "영업이익", 11: "4배", 13: ""}, False),
    ({6: "영업이익 4배", 11: "영업이익 14배", 13: "영업이익 4배"}, False),
    ({6: "영업이익 4배", 11: "영업이익 4배", 13: "영업이익 4배"}, True),
])
def test_psm_reads_are_independent_and_must_agree(tmp_path, monkeypatch, readings, should_pass):
    scene = caption("영업이익", "4배")
    scene["deterministic_text_regions"] = [{"bbox": [0, 0, 400, 200]}]
    calls = []

    def read(path, *, psm):
        calls.append(psm)
        return "completed", [{"text": readings[psm]}]

    monkeypatch.setattr(gate, "_read_tesseract_rows", read)
    report = gate.inspect_final_frame_text_integrity(panel(tmp_path), scene)
    assert report["passed"] is should_pass
    assert calls == [6, 11, 13]
    assert len(report["region_comparisons"][0]["attempts"]) == 3


def overlays():
    return {"v5_verified_overlays": [
        {"label": "기업A", "value": "4배", "anchor": {"x": 0, "y": 0, "width": .5, "height": 1}},
        {"label": "기업B", "value": "14배", "anchor": {"x": .5, "y": 0, "width": .5, "height": 1}},
    ]}


@pytest.mark.parametrize("readings,should_pass", [
    (["기업A 4배", "기업B 14배"], True),
    (["기업B 14배", "기업A 4배"], False),
    (["기업A 14배", "기업B 4배"], False),
    (["기업A 4배 기업B 14배", ""], False),
])
def test_texts_must_match_their_own_surface(tmp_path, monkeypatch, readings, should_pass):
    observations = iter([text for text in readings for _ in (6, 11, 13)])
    monkeypatch.setattr(gate, "_read_tesseract_rows", lambda *a, **k: (
        "completed", [{"text": next(observations)}],
    ))
    report = gate.inspect_final_frame_text_integrity(panel(tmp_path), overlays())
    assert report["passed"] is should_pass
    assert len(report["region_comparisons"]) == 2


@pytest.mark.parametrize("change,status", [
    ("missing_anchor", "invalid_surface_contract"),
    ("out_of_bounds", "invalid_surface_contract"),
    ("trend", "unsupported_surface_layout"),
])
def test_incomplete_surface_contract_is_not_approved(tmp_path, monkeypatch, change, status):
    scene = overlays()
    if change == "missing_anchor":
        del scene["v5_verified_overlays"][1]["anchor"]
    elif change == "out_of_bounds":
        scene["v5_verified_overlays"][1]["anchor"]["x"] = 2
    else:
        scene["v5_verified_overlays"][1]["visualization"] = "upward_trend"
    monkeypatch.setattr(gate, "_read_tesseract_rows", lambda *a, **k: pytest.fail("OCR 호출 전 차단 필요"))
    report = gate.inspect_final_frame_text_integrity(panel(tmp_path), scene)
    assert not report["passed"]
    assert report["status"] == status


def test_failed_psm_does_not_borrow_success_from_other_psm(tmp_path, monkeypatch):
    scene = caption("4배")
    scene["deterministic_text_regions"] = [{"bbox": [0, 0, 400, 200]}]
    monkeypatch.setattr(gate, "_read_tesseract_rows", lambda path, *, psm: (
        ("timeout", []) if psm == 11 else ("completed", [{"text": "4배"}])
    ))
    report = gate.inspect_final_frame_text_integrity(panel(tmp_path), scene)
    assert not report["passed"]
    assert report["region_comparisons"][0]["attempts"][1]["status"] == "timeout"


def test_one_matching_pixel_region_cannot_approve_another_region(tmp_path):
    path = panel(tmp_path)
    scene = caption("4배")
    with Image.open(path) as image:
        crop_hash = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
    scene["deterministic_text_regions"] = [
        {"bbox": [0, 0, 400, 200], "font_size": 30,
         "text_sha256": hashlib.sha256("4배".encode()).hexdigest(),
         "rendered_crop_sha256": crop_hash},
        {"bbox": [0, 0, 200, 100]},
    ]
    report = gate.inspect_final_frame_text_integrity(path, scene, ocr_rows=[{"text": "14배"}])
    assert not report["passed"]
    assert report["deterministic_provenance"]["reason"] == "unsupported_provenance_scope"


def test_unreadable_image_fails_closed(tmp_path):
    report = gate.inspect_final_frame_text_integrity(str(tmp_path / "absent.png"), caption("4배"))
    assert not report["passed"]
    assert report["status"] == "image_unreadable"

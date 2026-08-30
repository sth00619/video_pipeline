"""WO-IMG-01-F 해부학·화풍·장면 의미 회귀의 선행 실패 명세."""
from pathlib import Path

from app.v5.providers.gemini_provider import (
    _load_default_references,
    ensure_gemini_reference_contract,
    select_contextual_reference_paths,
)
from app.utils.canary_visual_review import (
    build_canary_visual_review_packet,
    record_canary_user_visual_review,
)


REPO = Path(__file__).resolve().parents[3]
REPORT = REPO / "docs/WO_PROVIDER_01_SCENE07_PROMPTFIX_AND_OCR_RESULT_2026-08-28.md"
RUNNER = REPO / "backend/fastapi-workers/scripts/run_gemini_scene07_promptfix_canary.py"
AGENTS = REPO / "AGENTS.md"


def test_data_laboratory_routes_to_job52_data_lab_style_reference():
    selected = select_contextual_reference_paths(
        "white lab coat and round scientist goggles in a data laboratory",
        _load_default_references(),
    )

    assert "channel_style_job52_data_lab.png" in {
        Path(path).name for path in selected
    }


def test_reference_contract_keeps_coin_dominant_but_allows_job52_costume_wrap(tmp_path: Path):
    face = tmp_path / "channel_character_face_range_v2.png"
    style = tmp_path / "channel_style_job52_data_lab.png"
    face.write_bytes(b"face")
    style.write_bytes(b"style")

    prompt = ensure_gemini_reference_contract("data laboratory", [str(face), str(style)])

    assert "round coin disc remains the dominant unified head-and-upper-body silhouette" in prompt
    assert "costume may wrap around and extend modestly below the coin rim" in prompt
    assert "two short compact legs" in prompt
    assert "roughly half of the coin diameter" in prompt
    assert "long human legs" in prompt


def test_scene07_canary_runner_requires_user_visual_review_packet():
    source = RUNNER.read_text(encoding="utf-8")

    assert "build_canary_visual_review_packet" in source
    assert "pending_user_visual_review" in source
    assert "approval_blocked" in source


def test_canary_visual_review_stays_blocked_until_every_user_check_passes(tmp_path: Path):
    image = tmp_path / "candidate.png"
    image.write_bytes(b"candidate")
    import hashlib

    packet = build_canary_visual_review_packet(
        image,
        hashlib.sha256(b"candidate").hexdigest(),
        automated_findings={"ocr": "pass"},
    )

    assert packet["status"] == "pending_user_visual_review"
    assert packet["approval_blocked"] is True
    assert packet["image_attachment_required"] is True
    decisions = {row["name"]: True for row in packet["required_checks"]}
    decisions["scene_meaning_legibility"] = False
    reviewed = record_canary_user_visual_review(packet, decisions, reviewer="user")
    assert reviewed["status"] == "rejected_by_user_visual_review"
    assert reviewed["approval_blocked"] is True


def test_canary_requires_ambiguous_prop_and_unlisted_failure_scan(tmp_path: Path):
    image = tmp_path / "candidate.png"
    image.write_bytes(b"candidate")
    import hashlib

    packet = build_canary_visual_review_packet(
        image,
        hashlib.sha256(b"candidate").hexdigest(),
        automated_findings={
            "unexpected_or_ambiguous_props": True,
            "unlisted_failure_scan": True,
        },
    )
    names = {row["name"] for row in packet["required_checks"]}
    assert "unexpected_or_ambiguous_props" in names
    assert "unlisted_failure_scan" in names

    decisions = {name: True for name in names}
    decisions["unexpected_or_ambiguous_props"] = False
    reviewed = record_canary_user_visual_review(
        packet,
        decisions,
        reviewer="user",
        findings=["오른손의 검은 소품이 총·무전기·레버 중 무엇인지 모호함"],
    )
    assert reviewed["approval_blocked"] is True
    assert reviewed["unexpected_findings"]
    assert reviewed["judgment_disagreements"][0]["check"] == "unexpected_or_ambiguous_props"


def test_scene07_report_and_global_rules_record_visual_regression_and_review_hold():
    report = REPORT.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")

    assert "WO-IMG-01-F 판정 정정" in report
    assert "해부학 붕괴" in report
    assert "화풍 이탈" in report
    assert "승인 후보에서 제외" in report
    assert "사용자 육안 확인 전에는" in agents
    assert "해부학" in agents and "화풍" in agents and "장면 의미" in agents

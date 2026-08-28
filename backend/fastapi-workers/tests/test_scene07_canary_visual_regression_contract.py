"""WO-IMG-01-F 해부학·화풍·장면 의미 회귀의 선행 실패 명세."""
from pathlib import Path

from app.v5.providers.gemini_provider import (
    _load_default_references,
    ensure_gemini_reference_contract,
    select_contextual_reference_paths,
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


def test_reference_contract_defines_coin_as_complete_head_and_torso_silhouette(tmp_path: Path):
    face = tmp_path / "channel_character_face_range_v2.png"
    style = tmp_path / "channel_style_job52_data_lab.png"
    face.write_bytes(b"face")
    style.write_bytes(b"style")

    prompt = ensure_gemini_reference_contract("data laboratory", [str(face), str(style)])

    assert "one round coin disc forms the complete head-and-torso silhouette" in prompt
    assert "two short compact legs" in prompt
    assert "no separate human torso or long human legs" in prompt


def test_scene07_canary_runner_requires_user_visual_review_packet():
    source = RUNNER.read_text(encoding="utf-8")

    assert "build_canary_visual_review_packet" in source
    assert "pending_user_visual_review" in source
    assert "approval_blocked" in source


def test_scene07_report_and_global_rules_record_visual_regression_and_review_hold():
    report = REPORT.read_text(encoding="utf-8")
    agents = AGENTS.read_text(encoding="utf-8")

    assert "WO-IMG-01-F 판정 정정" in report
    assert "해부학 붕괴" in report
    assert "화풍 이탈" in report
    assert "승인 후보에서 제외" in report
    assert "사용자 육안 확인 전에는" in agents
    assert "해부학" in agents and "화풍" in agents and "장면 의미" in agents

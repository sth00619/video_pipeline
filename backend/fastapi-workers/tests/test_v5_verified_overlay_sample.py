"""V5 결정론 오버레이는 HTTP 성공 원장값만 사용할 수 있다."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "render_v5_verified_overlay_sample.py"
SPEC = importlib.util.spec_from_file_location("v5_verified_overlay_sample", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_metrics_come_from_http_success_ledger_only(tmp_path: Path):
    ledger = tmp_path / "request_ledger.json"
    ledger.write_text(json.dumps({"items": [{
        "scene_key": "bench_08_datalab", "status": "http_200", "amount_krw": 254,
        "estimated_usd": 0.14, "model": "gemini-3-pro-image",
        "cost_status": "unverified_until_console_reconciliation",
    }]}), encoding="utf-8")
    metrics, provenance = MODULE._verified_metrics(ledger)
    assert [metric.value for metric in metrics] == ["gemini-3-pro-image", "HTTP 200", "$0.140", "₩254"]
    assert provenance["cost_status"] == "unverified_until_console_reconciliation"


def test_metrics_reject_non_success_ledger_entry(tmp_path: Path):
    ledger = tmp_path / "request_ledger.json"
    ledger.write_text(json.dumps({"items": [{
        "scene_key": "bench_08_datalab", "status": "http_503", "amount_krw": 254,
        "estimated_usd": 0.14, "model": "gemini-3-pro-image",
        "cost_status": "unverified_until_console_reconciliation",
    }]}), encoding="utf-8")
    try:
        MODULE._verified_metrics(ledger)
        assert False, "성공하지 않은 요청은 오버레이 근거로 사용할 수 없습니다."
    except RuntimeError:
        pass

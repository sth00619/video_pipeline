from app import runtime_config
from app.utils import budget


def test_cost_ledger_summary_includes_reserved_requests(tmp_path, monkeypatch):
    old = runtime_config.value("max_budget_per_video_krw")
    try:
        runtime_config.update(max_budget_per_video_krw=40000)
        monkeypatch.setattr(budget, "_job_path", lambda job_id, name: tmp_path / name)
        audit = budget.ProviderRequestAudit.for_job(
            job_id=7, scene_key="scene:0", model="gemini-3-pro-image")
        audit.before_attempt(attempt=1)
        summary = budget.load_cost_ledger_summary(7)
        assert summary["currency"] == "KRW"
        assert summary["total_krw"] > 0
        assert summary["remaining_krw"] < 40000
        assert summary["items"][0]["status"] == "reserved"
    finally:
        runtime_config.update(max_budget_per_video_krw=old)

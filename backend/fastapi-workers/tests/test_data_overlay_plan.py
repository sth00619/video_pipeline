import pytest

from app.services.overlay.plans import CopyClaim, DataOverlayPlan


def test_data_plan_rejects_numeric_callout_and_requires_common_comparison_basis():
    with pytest.raises(ValueError, match="numeric"):
        DataOverlayPlan(
            chart_kind="change", primary_metric="KOSPI", unit="pt", source_refs=["snapshot.kospi"],
            focus_target="latest_point", callout=CopyClaim(text="2.1% 급등", claim_type="derived_hook", source_refs=["snapshot.kospi"]),
        )
    with pytest.raises(ValueError, match="comparison_basis"):
        DataOverlayPlan(
            chart_kind="comparison", primary_metric="시총", unit="원", source_refs=["snapshot.stocks"],
            focus_target="larger_bar",
        )


def test_data_plan_accepts_verified_non_repeating_callout():
    plan = DataOverlayPlan(
        chart_kind="trend", primary_metric="KOSPI", unit="pt", source_refs=["snapshot.kospi"],
        focus_target="latest_point",
        callout=CopyClaim(text="이 흐름이 핵심", claim_type="derived_hook", source_refs=["snapshot.kospi"]),
        date_stamp_ref="market_chart.source_date",
    )
    assert plan.callout.text == "이 흐름이 핵심"

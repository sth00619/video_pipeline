"""Brief planning with a deterministic fallback and explicit validation gate."""
from __future__ import annotations

from typing import Any

from .brief import HeadlineLine, Subject, ThumbnailBriefV2, validate_brief


class BriefValidationError(ValueError):
    code = "BRIEF_VALIDATION_FAILED"


def plan(*, keyword: str, verified_facts: list[dict], available_assets: dict[str, bool], narration: str = "") -> ThumbnailBriefV2:
    """Pick an editorial template without inventing facts.

    The caller may replace this deterministic planner with its cached Claude
    proposal; both paths are validated by the same contract before rendering.
    """
    source_ref = "facts[0]" if verified_facts else None
    headline = [HeadlineLine(text=keyword[:16] or "핵심 이슈", tone="white"), HeadlineLine(text="지금 확인할 이유", tone="yellow")]
    if available_assets.get("article") and verified_facts:
        fact = verified_facts[0]
        brief = ThumbnailBriefV2.model_validate({"template": "article_evidence", "headline": [item.model_dump() for item in headline], "primary_subject": {"kind": "article", "asset_id": "article_frame"}, "evidence": {"source_url": str(fact.get("source_url") or "https://example.invalid"), "quote": str(fact.get("quote") or fact.get("claim") or keyword)[:240], "source_ref": source_ref, "publisher": str(fact.get("publisher") or "국내 언론")}})
    elif available_assets.get("person"):
        brief = ThumbnailBriefV2(template="person_headline", headline=headline, primary_subject=Subject(kind="person", asset_id="person_asset"))
    elif available_assets.get("mascot"):
        brief = ThumbnailBriefV2.model_validate({
            "template": "mascot_headline",
            "headline": [item.model_dump() for item in headline],
            "primary_subject": {"kind": "chart", "asset_id": "scene_backdrop", "source_ref": source_ref},
            "secondary_subject": {"allowed": True, "emotion": "worried"},
        })
    elif available_assets.get("chart"):
        brief = ThumbnailBriefV2(template="chart_warning", headline=headline, primary_subject=Subject(kind="chart", asset_id="verified_chart", source_ref=source_ref))
    else:
        # This is intentionally not rendered unless a badge/source ref exists.
        raise BriefValidationError("BRIEF_VALIDATION_FAILED: no valid v2 asset type")
    errors = validate_brief(brief, verified_facts, narration)
    if errors:
        raise BriefValidationError("BRIEF_VALIDATION_FAILED: " + "; ".join(errors))
    return brief

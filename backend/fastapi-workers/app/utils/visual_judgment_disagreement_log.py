"""자동 판정과 사용자 육안 판정의 불일치를 보존한다."""
from __future__ import annotations

from typing import Any


def compare_visual_judgments(
    automated: dict[str, Any] | None,
    user: dict[str, bool],
) -> dict[str, Any]:
    """공통 boolean 항목만 비교하며 이견을 자동으로 합의 처리하지 않는다."""
    automated = automated or {}
    common = [name for name in user if isinstance(automated.get(name), bool)]
    disagreements = [
        {
            "check": name,
            "automated": automated[name],
            "user": user[name],
            "resolution": "unresolved_user_review_controls_approval",
        }
        for name in common
        if automated[name] is not user[name]
    ]
    agreements = len(common) - len(disagreements)
    return {
        "contract": "visual-judgment-agreement-v1",
        "compared_check_count": len(common),
        "agreement_count": agreements,
        "agreement_rate": agreements / len(common) if common else None,
        "disagreements": disagreements,
        "automatic_resolution": False,
    }

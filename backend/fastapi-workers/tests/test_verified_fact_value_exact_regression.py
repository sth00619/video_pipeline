"""WO-IMG-01-B: 검증 사실보다 짧은 오버레이 값의 절단을 먼저 재현한다."""
import pytest

from app.v5.overlay.diegetic_fact_overlay import facts_from_verified_scene


def _scene(*, value: str, figure: str, fact: str) -> dict:
    return {
        "verified_facts": [{"figure": figure, "fact": fact}],
        "v5_verified_overlays": [{
            "label": "검증값",
            "value": value,
            "source_ref": "facts[0]",
            "anchor": {
                "x": 0.10, "y": 0.20, "width": 0.30, "height": 0.20,
                "kind": "monitor",
            },
        }],
    }


@pytest.mark.parametrize("value,figure,fact", [
    pytest.param("4배", "14배", "PER 14배", id="reject-leading-digit-truncation"),
    pytest.param(
        "143조", "143조 5000억 원", "기업의 영업이익은 143조 5000억 원이다.",
        id="reject-trailing-amount-truncation",
    ),
])
def test_verified_overlay_rejects_truncated_value(value, figure, fact):
    with pytest.raises(ValueError, match="원문"):
        facts_from_verified_scene(_scene(value=value, figure=figure, fact=fact))

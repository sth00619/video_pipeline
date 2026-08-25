from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from app.services.local_text_repair import (
    TextRegion,
    _intersection_consensus,
    _single_provider_region_is_safe,
    assess_deterministic_inpaint_surface,
    inpaint_text_regions,
    locate_malformed_text_regions,
    text_regions_from_visual_review,
)


def test_locator_accepts_only_resolver_regions_for_requested_text(tmp_path: Path):
    image = tmp_path / "scene.png"
    cv2.imwrite(str(image), np.full((100, 200, 3), 220, dtype=np.uint8))
    expected = [TextRegion("WRONG", (.2, .3, .2, .1), .95)]

    result = locate_malformed_text_regions(
        str(image), ["WRONG"],
        resolver=lambda _path, _targets: expected,
    )

    assert result == expected


def test_two_locator_consensus_rejects_a_coordinate_hallucination():
    gemini = [TextRegion("WRONG", (.28, .80, .18, .04), .92)]
    claude_wrong = [TextRegion("WRONG", (.05, .81, .18, .04), .90)]
    claude_matching = [TextRegion("WRONG", (.29, .80, .17, .04), .88)]

    assert _intersection_consensus(gemini, claude_wrong) == []
    agreed = _intersection_consensus(gemini, claude_matching)
    assert len(agreed) == 1
    assert agreed[0].bbox[0] == .28


def test_single_provider_fallback_contract_remains_small_and_high_confidence():
    accepted = TextRegion("3005", (.74, .90, .08, .07), .96)
    rejected_wide = TextRegion("3005", (.20, .20, .40, .20), .99)
    rejected_uncertain = TextRegion("3005", (.74, .90, .08, .07), .89)

    assert _single_provider_region_is_safe(accepted)
    assert not _single_provider_region_is_safe(rejected_wide)
    assert not _single_provider_region_is_safe(rejected_uncertain)


def test_deterministic_inpaint_surface_accepts_flat_paper_and_rejects_color_gradient(tmp_path: Path):
    flat = np.full((120, 240, 3), 220, dtype=np.uint8)
    cv2.putText(flat, "BAD", (65, 70), cv2.FONT_HERSHEY_SIMPLEX, .9, (20, 20, 20), 2)
    flat_path = tmp_path / "flat.png"
    cv2.imwrite(str(flat_path), flat)

    gradient = np.zeros((120, 240, 3), dtype=np.uint8)
    palette = ((20, 210, 30), (220, 40, 40), (30, 80, 230), (230, 210, 30))
    for x in range(240):
        gradient[:, x] = palette[(x // 24) % len(palette)]
    cv2.putText(gradient, "BAD", (65, 70), cv2.FONT_HERSHEY_SIMPLEX, .9, (240, 240, 240), 2)
    gradient_path = tmp_path / "gradient.png"
    cv2.imwrite(str(gradient_path), gradient)
    region = TextRegion("BAD", (.20, .25, .45, .50), .98)

    assert assess_deterministic_inpaint_surface(str(flat_path), [region])["passed"] is True
    assert assess_deterministic_inpaint_surface(str(gradient_path), [region])["passed"] is False


def test_same_review_region_is_used_only_for_exact_target_and_high_confidence():
    review = {
        "unexpected_text_regions": [
            {"text": "67", "bbox": [.25, .40, .09, .13], "confidence": .96},
            {"text": "equation", "bbox": [.02, .05, .4, .2], "confidence": .99},
            {"text": "67", "bbox": [.8, .8, .1, .1], "confidence": .5},
        ]
    }

    regions = text_regions_from_visual_review(review, ["67"])

    assert regions == [TextRegion("67", (.25, .40, .09, .13), .96)]


def test_inpaint_changes_only_the_tight_text_mask(tmp_path: Path):
    source = np.full((120, 240, 3), 220, dtype=np.uint8)
    cv2.putText(source, "WRONG", (50, 65), cv2.FONT_HERSHEY_SIMPLEX, .8, (20, 20, 20), 2)
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "repaired.png"
    cv2.imwrite(str(source_path), source)

    report = inpaint_text_regions(
        str(source_path), str(output_path),
        [TextRegion("WRONG", (.19, .32, .32, .28), .98)],
        padding_px=2,
    )
    repaired = cv2.imread(str(output_path))
    left, top, right, bottom = report["regions"][0]["pixel_bbox"]
    outside = np.ones(source.shape[:2], dtype=bool)
    outside[top:bottom, left:right] = False

    assert report["pixel_preservation_passed"] is True
    assert report["outside_mask_max_delta"] == 0
    assert np.array_equal(source[outside], repaired[outside])
    assert not np.array_equal(source[top:bottom, left:right], repaired[top:bottom, left:right])

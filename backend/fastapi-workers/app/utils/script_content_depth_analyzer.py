"""Script Content Depth Analyzer.

Evaluates content richness, fact density, causal depth, and information redundancy
in isolation from narrative tone or style (D1-D8).
"""

from __future__ import annotations

import re
from typing import Any


CAUSAL_CONNECTIVES = (
    "때문에", "그 결과", "이는", "이로 인해", "따라서", "원인은",
    "이어졌습니다", "이유는", "배경에는", "요인은", "영향으로", "가장 큰 이유는"
)


def _count_causal_sentences(sentences: list[str]) -> int:
    count = 0
    for s in sentences:
        if any(conn in s for conn in CAUSAL_CONNECTIVES):
            count += 1
    return count


def _extract_nouns(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\s가-힣]", " ", text or "")
    return {w for w in cleaned.split() if len(w) >= 2}


def assess_script_content_depth(
    script: str,
    sections: list[dict[str, Any]],
    verified_facts: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Calculate an independent content depth and cross-verification compliance report."""
    verified_facts = verified_facts or []
    warnings: list[str] = []
    
    # 1. Fact Density per scene
    scene_fact_densities = []
    total_facts = len(verified_facts)
    facts_referenced_count = 0

    for idx, scene in enumerate(sections):
        scene_text = str(scene.get("content") or scene.get("text") or "")
        scene_nouns = _extract_nouns(scene_text)
        
        # Check matching facts
        matched_facts = 0
        for fact_item in verified_facts:
            fact_str = str(fact_item.get("fact") or "")
            fact_nouns = _extract_nouns(fact_str)
            if fact_nouns and len(fact_nouns.intersection(scene_nouns)) >= max(1, len(fact_nouns) // 3):
                matched_facts += 1

        if matched_facts > 0:
            facts_referenced_count += 1

        scene_type = str(scene.get("section_type") or scene.get("type") or "data")
        if scene_type in {"data", "background"} and matched_facts == 0:
            warnings.append(f"Scene {idx + 1} ({scene_type}) has 0 verified fact matches.")

        scene_fact_densities.append({
            "scene_index": idx + 1,
            "scene_type": scene_type,
            "matched_facts_count": matched_facts,
        })

    # 2. Causal Depth Analysis
    all_sentences = [
        s.strip() for s in re.split(r"[.!?]\s*", script or "") if len(s.strip()) > 5
    ]
    causal_sentence_count = _count_causal_sentences(all_sentences)
    causal_ratio = round(causal_sentence_count / max(len(all_sentences), 1), 3)

    if causal_ratio < 0.15:
        warnings.append("Low causal explanation ratio: less than 15% of sentences contain causal connectives.")

    # 3. Information Redundancy
    redundant_pairs = []
    for i in range(len(sections)):
        nouns_i = _extract_nouns(str(sections[i].get("content") or sections[i].get("text") or ""))
        if not nouns_i:
            continue
        for j in range(i + 1, len(sections)):
            nouns_j = _extract_nouns(str(sections[j].get("content") or sections[j].get("text") or ""))
            if not nouns_j:
                continue
            jaccard = len(nouns_i.intersection(nouns_j)) / max(len(nouns_i.union(nouns_j)), 1)
            if jaccard >= 0.65:
                redundant_pairs.append((i + 1, j + 1, round(jaccard, 2)))
                warnings.append(f"High information redundancy between Scene {i + 1} and Scene {j + 1} ({round(jaccard, 2)}).")

    # 4. Cross Verification Stats from verified_facts
    cross_verified_count = sum(1 for f in verified_facts if f.get("cross_verified"))
    single_source_count = sum(1 for f in verified_facts if not f.get("cross_verified"))
    contradictions = [f for f in verified_facts if f.get("contradiction_detected")]

    # Overall Score Calculation
    base_score = 70
    if total_facts > 0:
        base_score += min(30, int((facts_referenced_count / max(total_facts, 1)) * 20))
    base_score += min(10, int(causal_ratio * 30))
    base_score -= len(redundant_pairs) * 5
    if contradictions:
        base_score -= len(contradictions) * 10

    final_score = max(0, min(100, base_score))

    return {
        "score": final_score,
        "warnings": warnings,
        "causal_ratio": causal_ratio,
        "causal_sentence_count": causal_sentence_count,
        "fact_density_by_scene": scene_fact_densities,
        "redundant_scene_pairs": redundant_pairs,
        "cross_validation": {
            "verified_facts_total": total_facts,
            "cross_verified_count": cross_verified_count,
            "single_source_count": single_source_count,
            "contradictions": contradictions,
        },
    }

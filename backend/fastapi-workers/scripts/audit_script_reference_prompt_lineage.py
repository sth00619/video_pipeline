#!/usr/bin/env python3
"""승인 대본에서 Gemini POST 직전까지의 실제 이미지 입력 계보를 재구성한다.

유료 API를 호출하지 않는다. 현재 운영 코드가 고르는 참조 파일과 최종 프롬프트를
그대로 재구성하고, Job52 보존 이미지와 해시로 대조해 개발자 검토 자료를 만든다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from app.v5.providers.gemini_provider import (  # noqa: E402
    _CONTEXTUAL_REFERENCE_GROUPS,
    _FACE_RANGE_REF_NAME,
    _FACE_ROLE_REF_NAMES,
    _SCENE_STYLE_REF_NAMES,
    ensure_gemini_reference_contract,
)
from scripts.run_gemini_scene07_promptfix_canary import prepare_row  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _source_matches(digest: str) -> list[str]:
    root = REPO / "artifacts/job52_full_audit_20260824/images"
    return [str(path.relative_to(REPO)) for path in sorted(root.glob("scene_*.png")) if _sha(path.read_bytes()) == digest]


def _reference_role(name: str) -> str:
    if name == _FACE_RANGE_REF_NAME:
        return "identity_face_range"
    if name in _FACE_ROLE_REF_NAMES.values():
        return "identity_role_face_anchor"
    if name in _SCENE_STYLE_REF_NAMES:
        return "scene_style_candidate"
    return "explicit_user_reference"


def render_reference_contact_sheet(references: list[dict], output: Path) -> None:
    """현재 활성 9개와 scene07 선택 순서를 한 장에서 육안 대조한다."""
    cell_w, cell_h, header_h = 480, 320, 54
    sheet = Image.new("RGB", (cell_w * 3, cell_h * 3), (15, 22, 36))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    small = ImageFont.load_default(size=13)
    root = ROOT / "out/references"
    for index, row in enumerate(references):
        col, line = index % 3, index // 3
        x, y = col * cell_w, line * cell_h
        with Image.open(root / row["name"]) as source:
            thumb = ImageOps.contain(source.convert("RGB"), (cell_w - 16, cell_h - header_h - 16))
        tx = x + (cell_w - thumb.width) // 2
        ty = y + header_h + (cell_h - header_h - thumb.height) // 2
        sheet.paste(thumb, (tx, ty))
        selected = row["selected_order"]
        color = (92, 220, 140) if selected else (190, 200, 215)
        draw.rectangle((x + 3, y + 3, x + cell_w - 4, y + cell_h - 4), outline=color, width=4 if selected else 1)
        prefix = f"SELECTED {selected} | " if selected else "ACTIVE | "
        draw.text((x + 10, y + 8), prefix + row["name"], fill=color, font=font)
        sources = row["job52_exact_source_matches"]
        source_label = Path(sources[0]).stem if sources else "derived face reference"
        draw.text((x + 10, y + 30), f"{row['role']} | {source_label}", fill=(175, 185, 205), font=small)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG")


def build_report(spec_path: Path) -> tuple[dict, str, str]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    row = prepare_row(spec, verify_expected_hash=False)
    scene = row["scene"]
    bounded_prompt = row["prompt"]
    final_prompt = ensure_gemini_reference_contract(bounded_prompt, row["reference_paths"])
    narration = str(scene.get("content") or scene.get("text") or "").strip()
    original_prompt = str(scene.get("prompt_en") or "").strip()
    reference_root = ROOT / "out/references"
    selected_names = {item["name"] for item in row["references"]}
    references = []
    for name in [_FACE_RANGE_REF_NAME, *_FACE_ROLE_REF_NAMES.values(), *_SCENE_STYLE_REF_NAMES]:
        path = reference_root / name
        data = path.read_bytes()
        with Image.open(path) as image:
            size = list(image.size)
        references.append({
            "name": name,
            "role": _reference_role(name),
            "selected_for_scene07": name in selected_names,
            "selected_order": next((i for i, item in enumerate(row["references"], 1) if item["name"] == name), None),
            "sha256": _sha(data),
            "byte_count": len(data),
            "size": size,
            "job52_exact_source_matches": _source_matches(_sha(data)),
        })
    facts = list(scene.get("verified_facts") or [])
    local_fact_matches = [
        {"index": index, **fact}
        for index, fact in enumerate(facts)
        if "143조" in json.dumps(fact, ensure_ascii=False)
    ]
    surface_plan = list(scene.get("screen_text_plan") or [])
    unique_surfaces = sorted({str(item.get("surface") or "") for item in surface_plan})
    report = {
        "schema_version": 1,
        "scope": "scene07 representative read-only reconstruction; no external API call",
        "model": spec["model"],
        "service_tier": spec["service_tier"],
        "image_size": spec["image_size"],
        "stages": {
            "approved_script": {
                "text": narration,
                "sha256": _sha(narration.encode()),
                "screen_texts": scene.get("screen_texts"),
                "verified_local_fact_matches": local_fact_matches,
            },
            "original_scene_prompt": {
                "text": original_prompt,
                "sha256": _sha(original_prompt.encode()),
            },
            "bounded_pre_provider_prompt": {
                "path": "bounded-pre-provider-prompt.txt",
                "sha256": _sha(bounded_prompt.encode()),
                "character_count": len(bounded_prompt),
                "text_contract": scene.get("image_text_contract"),
                "prompt_text_contract": scene.get("image_prompt_text_contract"),
                "character_integrity_contract": scene.get("character_integrity_contract"),
            },
            "reference_selection": {
                "selection_limit": 3,
                "context_group": "data_lab",
                "context_group_candidates": list(_CONTEXTUAL_REFERENCE_GROUPS["data_lab"]),
                "selected": row["references"],
                "all_active_candidates": references,
                "contact_sheet": "active-reference-contact-sheet.png",
            },
            "final_generate_content_prompt": {
                "path": "final-gemini-prompt.txt",
                "sha256": _sha(final_prompt.encode()),
                "character_count": len(final_prompt),
                "reference_parts_before_text": [item["name"] for item in row["references"]],
            },
            "post_generation": {
                "order": [
                    "Gemini raw PNG",
                    "generated text/OCR gate",
                    "deterministic Pillow surface text",
                    "final OCR exact-match gate",
                    "holistic visual QA",
                    "user visual review for paid canary",
                    "Fal eligibility only after all still-image gates",
                ],
            },
        },
        "findings": {
            "pilot_surface_plan_unique_surfaces": unique_surfaces,
            "pilot_surface_plan": surface_plan,
            "pilot_surface_semantic_mismatch": len(surface_plan) == 4 and unique_surfaces == ["main"],
            "pilot_only_plan_source": "scripts/run_gemini_eight_scene_pilot.py::prepare_pilot_scene",
            "common_pipeline_gap": "automatic screen-text extraction does not create object-level semantic surface bindings",
            "duplicate_active_reference_hashes": [
                [left["name"], right["name"], left["sha256"]]
                for i, left in enumerate(references)
                for right in references[i + 1:]
                if left["sha256"] == right["sha256"]
            ],
            "style_reference_is_full_scene_not_clean_style_only": True,
            "style_reference_risks": [
                "approved Job52 visual language and unwanted literal text/numbers coexist in the same raster",
                "full-body anatomy varies across style scenes, so face-only identity references cannot fully disambiguate silhouette",
                "the written reference contract forbids literal copying but cannot erase conflicting pixels from the visual input",
            ],
            "deterministic_surface_prompt_conflict_after_fix": (
                "non-linguistic shapes" in bounded_prompt and bool(scene.get("image_text_contract", {}).get("deterministic_texts"))
            ),
        },
        "limitations": [
            "This reconstructs the current code path; it is not the immutable historical payload sent by Job52.",
            "No Gemini request was made, so no new image or usageMetadata exists.",
            "Style/anatomy risk classification requires human review of the reference rasters and is not a provider-causality proof.",
        ],
    }
    return report, bounded_prompt, final_prompt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report, bounded, final = build_report(args.spec.resolve())
    output = args.output_dir.resolve()
    render_reference_contact_sheet(
        report["stages"]["reference_selection"]["all_active_candidates"],
        output / "active-reference-contact-sheet.png",
    )
    _write(output / "lineage.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _write(output / "bounded-pre-provider-prompt.txt", bounded + "\n")
    _write(output / "final-gemini-prompt.txt", final + "\n")
    print(json.dumps({
        "output": str(output),
        "selected_references": report["stages"]["reference_selection"]["selected"],
        "findings": report["findings"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""의미형 문자 표면의 실제 픽셀 검증을 유료 호출 없이 재현한다."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.surface_binding_attestation import (
    attest_axis_aligned_surface, attest_scene_surfaces, bind_single_local_surface,
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fixture(path: Path, variant: str) -> None:
    image = Image.new("RGB", (1280, 720), "#eef8fb" if variant == "open_background" else "#20354d")
    draw = ImageDraw.Draw(image)
    if variant == "detached_color_card":
        draw.rectangle((128, 72, 576, 360), fill="#eef8fb")
    elif variant != "open_background":
        draw.rectangle((128, 72, 576, 360), fill="#eef8fb", outline="#081522", width=12)
    if variant == "existing_text":
        draw.text((170, 165), "OLD 14X", font=_font(58), fill="#081522", stroke_width=2)
    elif variant == "occluded":
        draw.ellipse((300, 120, 650, 520), fill="#e0a927", outline="#081522", width=12)
    image.save(path, "PNG")


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {
        "blank_bordered_panel": True,
        "open_background": False,
        "detached_color_card": False,
        "existing_text": False,
        "occluded": False,
        "perspective_without_renderer": False,
    }
    cases = []
    for name, expected_pass in expected.items():
        path = output_dir / f"{name}.png"
        _fixture(path, "blank_bordered_panel" if name == "perspective_without_renderer" else name)
        binding = {
            "bbox": [.10, .10, .35, .40],
            "geometry": "planar_quad" if name == "perspective_without_renderer" else "axis_aligned_rect",
            "surface_kind": "board",
            "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            # 이 값과 기존 attestation은 실제 승인 근거가 아님을 함께 검증한다.
            "validated": True,
            "attestation": {"version": 999, "validation_method": "forged"},
        }
        try:
            attestation = attest_axis_aligned_surface(str(path), binding)
            actual_pass, error = True, None
        except ValueError as exc:
            actual_pass, attestation, error = False, None, str(exc)
        cases.append({
            "case": name,
            "expected_pass": expected_pass,
            "actual_pass": actual_pass,
            "matched": actual_pass == expected_pass,
            "source_sha256": binding["image_sha256"],
            "attestation": attestation,
            "error": error,
        })
    local_source = output_dir / "blank_bordered_panel.png"
    local_scene = {
        "screen_text_plan": [{
            "text": "현재 전망", "surface": "main", "purpose": "information", "surface_kind": "board",
        }],
    }
    try:
        bind_single_local_surface(str(local_source), local_scene)
        attest_scene_surfaces(str(local_source), local_scene)
        automatic_binding = {
            "passed": True,
            "binding": local_scene["surface_bindings"]["main"],
            "error": None,
        }
    except ValueError as exc:
        automatic_binding = {"passed": False, "binding": None, "error": str(exc)}
    payload = {
        "audit": "semantic_surface_physical_attestation_v1",
        "paid_api_calls": 0,
        "passed": all(item["matched"] for item in cases) and automatic_binding["passed"],
        "cases": cases,
        "automatic_local_binding": automatic_binding,
    }
    (output_dir / "surface-attestation-audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.output_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

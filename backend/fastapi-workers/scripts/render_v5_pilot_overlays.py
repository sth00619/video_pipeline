#!/usr/bin/env python3
"""사전검증을 통과한 V5 파일럿 입력을 결정론적 PNG로 렌더링한다."""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.diegetic_fact_overlay import apply_verified_scene_facts
from scripts.validate_v5_pilot_input import validate_payload


def _contact_sheet(images: list[Image.Image]) -> Image.Image:
    if not images:
        raise ValueError("렌더링할 씬이 없습니다.")
    width, height = images[0].size
    canvas = Image.new("RGB", (width, height * len(images)), "#101820")
    for index, image in enumerate(images):
        canvas.paste(image.convert("RGB"), (0, height * index))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description="V5 검증 오버레이 렌더링")
    parser.add_argument("--input", required=True, help="사전검증할 V5 파일럿 JSON")
    parser.add_argument("--output-dir", required=True, help="PNG 출력 폴더")
    args = parser.parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    validate_payload(payload)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Image.Image] = []
    manifest: list[dict[str, str]] = []
    for scene in payload["scenes"]:
        background = Path(str(scene["background_path"]))
        if not background.is_absolute():
            background = ROOT / background
        png = apply_verified_scene_facts(background.read_bytes(), scene)
        image = Image.open(io.BytesIO(png)).convert("RGB")
        target = output_dir / f"{scene['scene_id']}.png"
        image.save(target, format="PNG")
        rendered.append(image)
        manifest.append({"scene_id": str(scene["scene_id"]), "png": str(target)})

    sheet = _contact_sheet(rendered)
    sheet_path = output_dir / "contact_sheet.png"
    sheet.save(sheet_path, format="PNG")
    (output_dir / "render_manifest.json").write_text(
        json.dumps({"scenes": manifest, "contact_sheet": str(sheet_path)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"status": "rendered_after_preflight", "contact_sheet": str(sheet_path), "scenes": manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

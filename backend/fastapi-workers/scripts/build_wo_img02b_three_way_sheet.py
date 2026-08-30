#!/usr/bin/env python3
"""Job52 원본·WO-IMG-02-A·WO-IMG-02-B 결과를 한 장에 비교한다."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SCENES = (0, 7, 15, 28)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _font(size: int):
    try:
        return ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", size)
    except OSError:
        return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job52-dir", type=Path, required=True)
    parser.add_argument("--previous-dir", type=Path, required=True)
    parser.add_argument("--current-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cell_w, cell_h, header = 640, 358, 48
    canvas = Image.new("RGB", (cell_w * 3, (cell_h + header) * len(SCENES)), "#111827")
    draw = ImageDraw.Draw(canvas)
    font = _font(21)
    rows = []
    for row_index, scene_index in enumerate(SCENES):
        paths = (
            args.job52_dir / f"scene_{scene_index:03d}.png",
            args.previous_dir / f"scene_{scene_index:02d}_pro_priority_raw.png",
            args.current_dir / f"scene_{scene_index:02d}_pro_priority_raw.png",
        )
        labels = ("Job52 before", "WO-IMG-02-A after", "WO-IMG-02-B density after")
        y = row_index * (cell_h + header)
        row = {"scene": scene_index, "images": []}
        for column, (label, path) in enumerate(zip(labels, paths)):
            draw.text((column * cell_w + 10, y + 10), f"scene {scene_index:02d} | {label}", fill="white", font=font)
            if not path.is_file():
                raise FileNotFoundError(f"3자 비교 입력 없음: {path}")
            image = Image.open(path).convert("RGB")
            image.thumbnail((cell_w, cell_h))
            canvas.paste(image, (column * cell_w + (cell_w - image.width) // 2, y + header))
            row["images"].append({"label": label, "path": str(path.resolve()), "sha256": _sha(path)})
        rows.append(row)

    sheet = output / "wo_img02b_job52_previous_current_three_way_sheet.jpg"
    canvas.save(sheet, quality=94)
    manifest = {
        "version": "wo-img02b-three-way-sheet-v1",
        "scenes": list(SCENES),
        "rows": rows,
        "sheet_path": str(sheet),
        "sheet_sha256": _sha(sheet),
    }
    (output / "three-way-sheet-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"sheet": str(sheet), "sha256": manifest["sheet_sha256"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

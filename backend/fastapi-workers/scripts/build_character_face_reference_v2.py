#!/usr/bin/env python3
"""Job52 승인 장면 여섯 장에서 얼굴 참조 v2를 결정론적으로 만든다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image
from PIL import ImageDraw


REPO = Path(__file__).resolve().parents[3]
SOURCE_DIR = REPO / "artifacts/job52_full_audit_20260824/images"
OUTPUT_DIR = REPO / "backend/fastapi-workers/out/references"
OUTPUT = OUTPUT_DIR / "channel_character_face_range_v2.png"
MANIFEST = OUTPUT_DIR / "channel_character_face_range_v2.manifest.json"
SCENE05_ANCHOR_OUTPUT = OUTPUT_DIR / "channel_character_face_scene05_v1.png"
SCENE05_ANCHOR_MANIFEST = OUTPUT_DIR / "channel_character_face_scene05_v1.manifest.json"
APPROVED_RANGE_SHA256 = "7e7981e389d07c4c3eca908708365cdcc809226c0f9a039f7ff7f62bbad8e40e"
PANEL_SIZE = 512
FACE_MASK_BOX = (12, 105, 500, 510)
FACE_BACKGROUND = (232, 238, 244)

# 박스는 (left, top, right, bottom)이며 원본 1920x1080 좌표다. 생성 모델로
# 보정하지 않고 얼굴·이마·눈썹·볼과 장면별 머리 장식 일부만 정사각 크롭한다.
SOURCES = (
    (3, "fad619f51fbef7f6b87636e2c33c3fde584b2576ec26c4b05011452e0eb1c024", (725, 190, 1085, 550)),
    (4, "87c52f3ef3c0bdd0bfddeb3ed08f15f7038c38c48fc5ebf291db625d8aed05e6", (755, 195, 1115, 555)),
    (5, "f38142ec185ddab03e08d5baacdf9fbbda3659c168ecbeaa225f75483e92d46e", (700, 180, 1060, 540)),
    (9, "80c6ba98deb097119ae911b607df164e1a54d6859772f5db65a2f2452664654b", (1175, 330, 1535, 690)),
    (13, "cd6502b7879fdd2a283238ae29513151890b782ed9a227defc03205121d8da59", (765, 250, 1125, 610)),
    (14, "e584e57951bad80307e01b921f58177d92853a81fafeb0c9942a8cf1813f45c7", (740, 280, 1100, 640)),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    # 이미 승인·전송 원장에 연결된 v2 시트는 현재 Pillow 버전으로 재인코딩하지
    # 않는다. 바이트가 달라지면 같은 픽셀이어도 참조 계보가 끊긴다.
    if not OUTPUT.is_file() or sha256(OUTPUT) != APPROVED_RANGE_SHA256:
        raise RuntimeError("승인 얼굴 v2 시트가 없거나 SHA-256이 달라 scene05 기준점을 만들 수 없습니다.")
    scene05_panel: Image.Image | None = None
    scene05_row: dict | None = None
    for scene_number, expected_sha256, crop_box in SOURCES:
        if scene_number != 5:
            continue
        source = SOURCE_DIR / f"scene_{scene_number:03d}.png"
        actual_sha256 = sha256(source)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Job52 scene {scene_number:02d} 원본 해시 불일치: "
                f"{actual_sha256} != {expected_sha256}"
            )
        with Image.open(source) as image:
            if image.size != (1920, 1080):
                raise RuntimeError(f"예상하지 않은 원본 크기: {source} {image.size}")
            crop = image.convert("RGB").crop(crop_box).resize(
                (PANEL_SIZE, PANEL_SIZE), Image.Resampling.LANCZOS
            )
            # 참조에서 배경 문자·그래프·소품을 학습하지 않도록 얼굴 타원 밖은
            # 중성색으로 가린다. 얼굴 내부 픽셀에는 생성·보정·재채색을 하지 않는다.
            mask = Image.new("L", (PANEL_SIZE, PANEL_SIZE), 0)
            ImageDraw.Draw(mask).ellipse(FACE_MASK_BOX, fill=255)
            panel = Image.composite(crop, Image.new("RGB", crop.size, FACE_BACKGROUND), mask)
        row = {
                "scene_number": scene_number,
                "source": str(source.relative_to(REPO)),
                "source_sha256": actual_sha256,
                "source_size": [1920, 1080],
                "crop_box_xyxy": list(crop_box),
                "panel_size": [PANEL_SIZE, PANEL_SIZE],
            }
        scene05_panel = panel.copy()
        scene05_row = dict(row)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if scene05_panel is None or scene05_row is None:
        raise RuntimeError("scene05 얼굴 기준점 원본을 만들지 못했습니다.")
    scene05_panel.save(SCENE05_ANCHOR_OUTPUT, format="PNG", optimize=True)
    anchor_manifest = {
        "schema_version": 1,
        "purpose": "고글 장면에서 6장 얼굴 범위 중 Job52 scene05를 확대해 보는 역할 기준점",
        "build_method": "face range v2와 동일한 고정 좌표 크롭·중성 배경 마스크, 생성형 보정 없음",
        "selection_policy": "고글 역할 장면에서만 전체 6장 범위와 함께 사용하며 의상·표정·포즈를 고정하지 않음",
        "source": scene05_row,
        "output": str(SCENE05_ANCHOR_OUTPUT.relative_to(REPO)),
        "output_size": list(scene05_panel.size),
        "output_sha256": sha256(SCENE05_ANCHOR_OUTPUT),
    }
    SCENE05_ANCHOR_MANIFEST.write_text(
        json.dumps(anchor_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "approved_range": str(OUTPUT),
        "approved_range_sha256": APPROVED_RANGE_SHA256,
        "scene05_anchor": str(SCENE05_ANCHOR_OUTPUT),
        "scene05_anchor_sha256": anchor_manifest["output_sha256"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V5 Gemini용 텍스트 없는 참조 자산 v2를 결정론적으로 만든다."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
VIDEO = Path(r"C:\Users\song\Downloads\final (1).mp4")
OUT_DIR = ROOT / "out" / "references"
REFERENCE_VERSION = "v2_textless"


def _frame(seconds: int, target: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(seconds), "-i", str(VIDEO), "-frames:v", "1", str(target)],
        check=True,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not VIDEO.exists():
        print(f"ERROR 사용자 제공 참조 영상을 찾지 못했습니다: {VIDEO}")
        return 2
    if not shutil.which("ffmpeg"):
        print("ERROR ffmpeg를 찾지 못했습니다")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for seconds in (5, 20, 35, 50):
        path = OUT_DIR / f"source_{seconds:02d}s.png"
        if not path.exists():
            _frame(seconds, path)
        frames.append(path)

    # 하단 자막 시작점보다 충분히 위에서 자른 캐릭터 정체성 참조다.
    character = Image.open(frames[0]).convert("RGB").crop((700, 35, 1510, 850))
    character_path = OUT_DIR / "character_reference_v2_textless.png"
    character.save(character_path)

    # 선·색·셀셰이딩만 남기고, 자막 및 수치 화면을 포함한 영역은 제외한다.
    # 스타일 참조는 몽타주가 아니라 하나의 원본 장면을 비율 변경 없이 사용한다.
    # 참조 이미지의 비율은 생성 결과의 16:9 구도를 강제하지 않으며, 구도는 별도의
    # layout 참조가 담당한다. 하단 자막 직전까지만 남겨 화면 전체 시야를 보존한다.
    style = Image.open(frames[0]).convert("RGB").crop((0, 0, 1920, 880))
    style_path = OUT_DIR / "style_reference_v2_textless.png"
    style.save(style_path)

    # 글자·숫자·기호 없이 영역의 위치와 크기만 표현한 구도 가이드다.
    layout = Image.new("RGB", (1920, 1080), "#112438")
    draw = ImageDraw.Draw(layout)
    draw.rectangle((0, 0, 1919, 1079), outline="#70D9FF", width=8)
    draw.rectangle((90, 120, 1090, 820), outline="#70D9FF", width=8)
    draw.rectangle((1160, 105, 1810, 880), outline="#FFD24A", width=8)
    draw.rectangle((90, 910, 1830, 1020), outline="#FFFFFF", width=5)
    draw.line((1090, 120, 1090, 820), fill="#70D9FF", width=4)
    layout_path = OUT_DIR / "layout_reference_v2_textless.png"
    layout.save(layout_path)

    artifacts = [("character", character_path), ("style", style_path), ("layout", layout_path)]
    manifest = {
        "version": REFERENCE_VERSION,
        "contract": "텍스트·숫자·로고·자막이 없는 순수 픽셀 참조 자산",
        "artifacts": [
            {"role": role, "path": str(path), "sha256": _sha256(path)}
            for role, path in artifacts
        ],
    }
    (OUT_DIR / "reference_manifest_v2_textless.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 레이아웃 래스터는 모델이 테두리 자체를 소품으로 복제할 수 있어 V3 호출에는 전송하지 않는다.
    # 기존 V2 자산은 재현성 검토를 위해 보존하며, V3 manifest는 실제 전송하는 두 장만 선언한다.
    v3_artifacts = [("character", character_path), ("style", style_path)]
    v3_manifest = {
        "version": "v3_textless_no_layout_raster",
        "contract": "텍스트 없는 캐릭터·스타일 참조만 전송하고 배치는 프롬프트 문장으로 지시",
        "artifacts": [
            {"role": role, "path": str(path), "sha256": _sha256(path)}
            for role, path in v3_artifacts
        ],
    }
    (OUT_DIR / "reference_manifest_v3_textless_no_layout_raster.json").write_text(
        json.dumps(v3_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"PASS 무문자 참조 자산 3종 저장: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""얼굴 참조 v1 각 패널이 Job52 어느 장면에서 왔는지 ORB로 대조한다."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2


REPO = Path(__file__).resolve().parents[3]
V1 = REPO / "backend/fastapi-workers/out/references/channel_character_face_range_v1.png"
SCENES = REPO / "artifacts/job52_full_audit_20260824/images"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def good_match_count(left, right) -> int:
    orb = cv2.ORB_create(nfeatures=6000)
    _, left_descriptors = orb.detectAndCompute(left, None)
    _, right_descriptors = orb.detectAndCompute(right, None)
    if left_descriptors is None or right_descriptors is None:
        return 0
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(left_descriptors, right_descriptors, k=2)
    return sum(1 for first, second in pairs if first.distance < 0.75 * second.distance)


def build_report() -> dict:
    strip = cv2.imread(str(V1), cv2.IMREAD_GRAYSCALE)
    if strip is None or strip.shape != (512, 1536):
        raise RuntimeError(f"예상하지 않은 v1 크기: {None if strip is None else strip.shape}")
    scene_paths = sorted(SCENES.glob("scene_*.png"))
    panels = []
    for index in range(3):
        panel = strip[:, index * 512:(index + 1) * 512]
        scores = []
        for scene_path in scene_paths:
            scene = cv2.imread(str(scene_path), cv2.IMREAD_GRAYSCALE)
            scores.append({
                "scene_number": int(scene_path.stem.split("_")[-1]),
                "good_orb_matches": good_match_count(panel, scene),
                "scene_sha256": sha256(scene_path),
            })
        scores.sort(key=lambda row: row["good_orb_matches"], reverse=True)
        panels.append({"panel_index": index, "top_matches": scores[:5]})
    return {
        "schema_version": 1,
        "method": "ORB 6000 features, Hamming KNN, Lowe ratio 0.75",
        "v1_path": str(V1.relative_to(REPO)),
        "v1_sha256": sha256(V1),
        "panel_size": [512, 512],
        "panels": panels,
        "interpretation_limit": "특징점 일치는 출처 확인용이며 얼굴 품질 점수가 아니다.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([
        {"panel_index": row["panel_index"], **row["top_matches"][0]}
        for row in report["panels"]
    ], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

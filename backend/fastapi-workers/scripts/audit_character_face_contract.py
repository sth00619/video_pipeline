#!/usr/bin/env python3
"""승인 얼굴 6장과 기존 파일럿 실패 3장의 눈 구조를 정량 대조한다."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean

from PIL import Image


REPO = Path(__file__).resolve().parents[3]
MIN_RATIO = 0.38
MAX_RATIO = 0.58

# 좌표는 원본 PNG에서 사람이 선택한 (left, top, right, bottom) 경계다. 학습형
# 얼굴 검출기가 아니라 픽셀 눈금 측정이므로 자동 의미 판정으로 확대하지 않는다.
SAMPLES = (
    {
        "kind": "approved_reference", "scene": 3,
        "path": "artifacts/job52_full_audit_20260824/images/scene_003.png",
        "sha256": "fad619f51fbef7f6b87636e2c33c3fde584b2576ec26c4b05011452e0eb1c024",
        "eyes": [((775, 310, 845, 405), (800, 330, 832, 392)), ((900, 310, 970, 405), (922, 330, 954, 392))],
        "sclera_visible": True, "warm_brown_iris": True, "layered_catchlights": True,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": False,
    },
    {
        "kind": "approved_reference", "scene": 4,
        "path": "artifacts/job52_full_audit_20260824/images/scene_004.png",
        "sha256": "87c52f3ef3c0bdd0bfddeb3ed08f15f7038c38c48fc5ebf291db625d8aed05e6",
        "eyes": [((775, 260, 865, 375), (805, 280, 848, 360)), ((920, 260, 1010, 375), (948, 280, 991, 360))],
        "sclera_visible": True, "warm_brown_iris": True, "layered_catchlights": True,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": True,
    },
    {
        "kind": "approved_reference", "scene": 5,
        "path": "artifacts/job52_full_audit_20260824/images/scene_005.png",
        "sha256": "f38142ec185ddab03e08d5baacdf9fbbda3659c168ecbeaa225f75483e92d46e",
        "eyes": [((765, 320, 830, 410), (788, 335, 820, 398)), ((890, 310, 950, 400), (907, 326, 936, 390))],
        "sclera_visible": True, "warm_brown_iris": True, "layered_catchlights": True,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": True,
    },
    {
        "kind": "approved_reference", "scene": 9,
        "path": "artifacts/job52_full_audit_20260824/images/scene_009.png",
        "sha256": "80c6ba98deb097119ae911b607df164e1a54d6859772f5db65a2f2452664654b",
        "eyes": [((1230, 465, 1290, 555), (1248, 480, 1277, 543)), ((1360, 465, 1420, 555), (1380, 480, 1409, 543))],
        "sclera_visible": True, "warm_brown_iris": True, "layered_catchlights": True,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": False,
    },
    {
        "kind": "approved_reference", "scene": 13,
        "path": "artifacts/job52_full_audit_20260824/images/scene_013.png",
        "sha256": "cd6502b7879fdd2a283238ae29513151890b782ed9a227defc03205121d8da59",
        "eyes": [((820, 405, 880, 495), (838, 420, 866, 482)), ((940, 405, 1000, 495), (958, 420, 986, 482))],
        "sclera_visible": True, "warm_brown_iris": True, "layered_catchlights": True,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": False,
    },
    {
        "kind": "approved_reference", "scene": 14,
        "path": "artifacts/job52_full_audit_20260824/images/scene_014.png",
        "sha256": "e584e57951bad80307e01b921f58177d92853a81fafeb0c9942a8cf1813f45c7",
        "eyes": [((800, 450, 860, 540), (818, 465, 846, 527)), ((920, 450, 980, 540), (938, 465, 966, 527))],
        "sclera_visible": True, "warm_brown_iris": True, "layered_catchlights": True,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": True,
    },
    {
        "kind": "pilot_failure", "scene": 2,
        "path": "artifacts/wo_img01_c3_eight_scene_pilot/scene_02_raw.png",
        "sha256": "9a6821a14fd175d2af2f76aad24c98a35bb2de5053c530a4a640e50521aeaf3a",
        "eyes": [((905, 655, 1005, 795), (950, 680, 979, 770)), ((1060, 655, 1132, 795), (1088, 680, 1114, 770))],
        "sclera_visible": True, "warm_brown_iris": False, "layered_catchlights": False,
        "forehead_highlight": True, "eyebrow_shape": "deep_furrow", "blush": False,
        "wardrobe_observation": "대본 근거 없는 경찰모·경찰 제복",
    },
    {
        "kind": "pilot_failure", "scene": 7,
        "path": "artifacts/wo_img01_c3_eight_scene_pilot/scene_07_raw.png",
        "sha256": "d442a2a00399e6feb65fdca543ab3b0cad1e9eea2a97ef241b804015bbaa4e6e",
        "eyes": [((1830, 735, 1872, 825), (1830, 735, 1872, 825)), ((1985, 735, 2027, 825), (1985, 735, 2027, 825))],
        "sclera_visible": False, "warm_brown_iris": False, "layered_catchlights": False,
        "forehead_highlight": True, "eyebrow_shape": "sharp_angle", "blush": False,
    },
    {
        "kind": "pilot_failure", "scene": 35,
        "path": "artifacts/wo_img01_c3_eight_scene_pilot/scene_35_raw.png",
        "sha256": "800ebc51b1ea91894eab4fe808fdb0c63ec00a61f1b080055275fe30c1799428",
        "eyes": [((1250, 575, 1337, 695), (1288, 595, 1317, 675)), ((1438, 575, 1525, 695), (1476, 595, 1505, 675))],
        "sclera_visible": True, "warm_brown_iris": False, "layered_catchlights": False,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": False,
        "wardrobe_observation": "대본 근거 없는 경찰모",
    },
    {
        "kind": "reopen_candidate", "scene": 7,
        "path": "artifacts/wo_img01_d_face_reference_pilot_20260828/scene_07_reopen_01_raw.png",
        "sha256": "4925e325ebd8000dc61ee7db4733e63ffa96ef0ec34f0a8dea8c34eefa8d8b7e",
        "eyes": [
            ((696, 774, 735, 844), (696, 774, 735, 844)),
            ((830, 761, 866, 830), (830, 761, 866, 830)),
        ],
        "sclera_visible": False, "warm_brown_iris": False, "layered_catchlights": False,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": False,
        "attempt_id": "dfbf4c89677f4a63a58c3212d5245a93",
        "observation": "HTTP 200이지만 기존 scene07과 같은 흰자 없는 검은 타원 눈",
    },
    {
        "kind": "promptfix_candidate", "scene": 7,
        "path": "artifacts/wo_scene07_promptfix_canary_v3_20260828/scene_07_raw.png",
        "sha256": "93eea450aea1fd398fb4774f9c303c3acedaed0d44ef46dbe84f4710fa2834c3",
        "eyes": [
            ((585, 660, 780, 840), (665, 710, 725, 795)),
            ((830, 655, 990, 835), (870, 700, 930, 785)),
        ],
        "sclera_visible": True, "warm_brown_iris": False, "layered_catchlights": False,
        "forehead_highlight": True, "eyebrow_shape": "sharp_angle", "blush": False,
        "attempt_id": "a259e66e5bdd462997a639dade7dd77e",
        "observation": "검은 타원 눈은 해소됐지만 홍채가 작고 회청색이며 캐치라이트가 한 겹이고 눈썹이 각짐",
    },
    {
        "kind": "common_quality_floor_candidate", "scene": 7,
        "path": "artifacts/common_quality_floor_canary_20260828/scene_07_raw.png",
        "sha256": "b230878c7b685b18c118f47a9ba84deda554d0c18dfe9b34464475180861d493",
        "eyes": [
            ((1785, 540, 1855, 655), (1785, 540, 1855, 655)),
            ((2028, 535, 2095, 655), (2028, 535, 2095, 655)),
        ],
        "sclera_visible": False, "warm_brown_iris": False, "layered_catchlights": False,
        "forehead_highlight": True, "eyebrow_shape": "gentle_curve", "blush": False,
        "attempt_id": "97931aa419cf4a7ea5fad1016f6a071d",
        "observation": "흰 캐치라이트 점은 있으나 별도 흰자 영역과 갈색 홍채가 없는 검은 타원 눈",
    },
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bbox_width(box: tuple[int, int, int, int]) -> int:
    return box[2] - box[0]


def eye_layer_pixel_ratios(
    image_path: Path,
    box: tuple[int, int, int, int],
) -> dict[str, float]:
    """수동 눈 ROI 안의 흰 영역·갈색 영역 비율을 보조 증거로 계산한다.

    ROI 좌표가 필요한 감사용 계측이며 일반 장면의 눈 위치를 자동 추정하지
    않는다. 따라서 운영 하드 게이트가 아니라 육안 판정 전 보조 근거다.
    """
    with Image.open(image_path) as source:
        pixels = list(source.convert("RGB").crop(box).getdata())
    count = max(1, len(pixels))
    white = sum(
        min(red, green, blue) >= 205 and max(red, green, blue) - min(red, green, blue) <= 45
        for red, green, blue in pixels
    )
    warm_brown = sum(
        45 <= red <= 210
        and red >= green * 1.18
        and green >= blue * 1.05
        and red - blue >= 25
        for red, green, blue in pixels
    )
    return {
        "white_region_ratio": round(white / count, 4),
        "warm_brown_region_ratio": round(warm_brown / count, 4),
    }


def evaluate(sample: dict, *, verify_source: bool = True) -> dict:
    path = REPO / sample["path"]
    actual_sha256 = sha256(path) if verify_source else sample["sha256"]
    if verify_source and actual_sha256 != sample["sha256"]:
        raise RuntimeError(f"원본 해시 불일치: {path}")
    ratios = [bbox_width(iris) / bbox_width(eye) for eye, iris in sample["eyes"]]
    pixel_layers = (
        [eye_layer_pixel_ratios(path, eye) for eye, _ in sample["eyes"]]
        if verify_source else []
    )
    checks = {
        "iris_width_ratio_in_range": all(MIN_RATIO <= value <= MAX_RATIO for value in ratios),
        "sclera_visible": sample["sclera_visible"],
        "warm_brown_iris": sample["warm_brown_iris"],
        "layered_catchlights": sample["layered_catchlights"],
        "forehead_highlight": sample["forehead_highlight"],
        "eyebrow_shape_allowed": sample["eyebrow_shape"] == "gentle_curve",
    }
    return {
        **{key: value for key, value in sample.items() if key != "eyes"},
        "sha256": actual_sha256,
        "source_hash_verified": verify_source,
        "eye_annotations": [
            {"eye_bbox_xyxy": list(eye), "iris_bbox_xyxy": list(iris), "iris_eye_width_ratio": round(ratio, 4)}
            for (eye, iris), ratio in zip(sample["eyes"], ratios)
        ],
        "mean_iris_eye_width_ratio": round(mean(ratios), 4),
        "eye_layer_pixel_ratios": pixel_layers,
        "checks": checks,
        "face_contract_pass": all(checks.values()),
    }


def build_report(*, verify_sources: bool = True) -> dict:
    rows = [evaluate(sample, verify_source=verify_sources) for sample in SAMPLES]
    approved = [row for row in rows if row["kind"] == "approved_reference"]
    pilots = [row for row in rows if row["kind"] == "pilot_failure"]
    reopen_candidates = [row for row in rows if row["kind"] == "reopen_candidate"]
    promptfix_candidates = [row for row in rows if row["kind"] == "promptfix_candidate"]
    common_quality_floor_candidates = [
        row for row in rows if row["kind"] == "common_quality_floor_candidate"
    ]
    return {
        "schema_version": 1,
        "measurement_method": "원본 PNG의 눈/홍채 경계를 사람이 픽셀 좌표로 선택하고 비율은 코드로 계산",
        "source_hashes_verified": verify_sources,
        "limitations": [
            "학습형 얼굴 랜드마크 검출기가 아니며 육안 의미 판정을 대체하지 않는다.",
            "유료 재생성 전 선행 실패를 반복 가능한 좌표와 산술로 고정하기 위한 측정이다.",
        ],
        "contract": {"iris_eye_width_ratio_min": MIN_RATIO, "iris_eye_width_ratio_max": MAX_RATIO},
        "approved_reference_observed_mean_range": [
            min(row["mean_iris_eye_width_ratio"] for row in approved),
            max(row["mean_iris_eye_width_ratio"] for row in approved),
        ],
        "approved_reference_pass_count": sum(row["face_contract_pass"] for row in approved),
        "pilot_failure_reproduced_count": sum(not row["face_contract_pass"] for row in pilots),
        "reopen_candidate_failure_count": sum(
            not row["face_contract_pass"] for row in reopen_candidates
        ),
        "promptfix_candidate_failure_count": sum(
            not row["face_contract_pass"] for row in promptfix_candidates
        ),
        "common_quality_floor_candidate_failure_count": sum(
            not row["face_contract_pass"] for row in common_quality_floor_candidates
        ),
        "samples": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "approved_reference_pass_count": report["approved_reference_pass_count"],
        "pilot_failure_reproduced_count": report["pilot_failure_reproduced_count"],
        "reopen_candidate_failure_count": report["reopen_candidate_failure_count"],
        "promptfix_candidate_failure_count": report["promptfix_candidate_failure_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

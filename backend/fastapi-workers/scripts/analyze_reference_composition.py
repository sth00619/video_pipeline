#!/usr/bin/env python3
"""레퍼런스 프레임의 배경 구성·색조·화면 내 수치 배치를 재현 가능하게 측정한다.

캐릭터를 정밀 분할하는 모델은 사용하지 않는다. 대신 중앙 인물 가능 영역과
하단 자막 띠를 제외한 주변부 픽셀 통계를 함께 기록하며, 이 값은 배경 전용
정답이 아니라 비교 가능한 보조 지표로만 사용한다.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import cv2
import numpy as np


DEVICE_ROLE_RULES = {
    "physical_economic_metaphor": {
        "observed_primary_device_range": [1, 2],
        "role_rule": "하나의 중심 사물 관계가 결론을 맡고 보조 장치는 원인·결과 중 다른 한 축만 맡는다.",
        "duplicate_risk": "저울·칠판·그래프가 같은 비교값을 반복하면 레퍼런스보다 설명 장치가 과잉이다.",
    },
    "classroom_briefing": {
        "observed_primary_device_range": [1, 2],
        "role_rule": "칠판은 개념/관계를 맡고 손의 포인터·저울·실물 소품은 사례나 비교를 맡는다.",
        "duplicate_risk": "칠판과 실물 소품이 동일 문구·동일 수치를 되풀이하지 않는다.",
    },
    "evidence_insert": {
        "observed_primary_device_range": [1, 1],
        "role_rule": "검증된 기사·차트 캡처 하나가 근거의 주인공이며 생성 배경은 이를 재작성하지 않는다.",
        "duplicate_risk": "캡처의 수치를 생성 간판에 다시 쓰면 근거 계보와 정확성이 깨진다.",
    },
    "control_room_data_lab": {
        "observed_primary_device_range": [2, 6],
        "role_rule": "여러 화면은 추세·원인·결론 등 서로 다른 정보 역할을 분담한다.",
        "duplicate_risk": "같은 승인 문구를 여러 모니터에 복제해 장치 수를 채우지 않는다.",
    },
    "factory_construction": {
        "observed_primary_device_range": [1, 3],
        "role_rule": "생산 설비/공정 흐름이 원인을, 한 개의 계기·표지가 상태나 결론을 맡는다.",
        "duplicate_risk": "장식 모니터를 늘려 실제 생산 메커니즘을 대체하지 않는다.",
    },
    "market_news_crisis": {
        "observed_primary_device_range": [2, 6],
        "role_rule": "반복되는 붉은 방향선은 분위기 연출이며, 읽을 수 있는 문구·수치는 한 핵심 표면에 집중한다.",
        "duplicate_risk": "방향성 도형의 반복과 동일 텍스트의 반복을 혼동하지 않는다.",
    },
    "dialogue_office_library": {
        "observed_primary_device_range": [1, 2],
        "role_rule": "짧은 판단은 말풍선/책/노트북 중 한 장치가 맡고 나머지는 공간 맥락을 만든다.",
        "duplicate_risk": "낮은 밀도를 빈 화면으로 해석하지 않고 책·창·조명 같은 비문자 공간 소품으로 채운다.",
    },
    "channel_interstitial": {
        "observed_primary_device_range": [1, 1],
        "role_rule": "채널 전환 자산이며 일반 설명 장면의 밀도·표면 규칙 표본에서 제외한다.",
        "duplicate_risk": "운영 설명 장면의 archetype 근거로 사용하지 않는다.",
    },
}


def _tesseract_rows(path: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "kor+eng", "--psm", "11", "tsv"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode:
        return []
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(result.stdout.splitlines(), delimiter="\t"):
        text = str(row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf") or -1)
        except ValueError:
            confidence = -1
        if text and confidence >= 25:
            rows.append({
                "text": text,
                "confidence": confidence,
                "left": int(row["left"]), "top": int(row["top"]),
                "width": int(row["width"]), "height": int(row["height"]),
            })
    return rows


def _frame_metrics(path: Path) -> dict[str, Any]:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {path}")
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 110)

    # 하단 자막과 중앙 캐릭터 가능 영역을 제외한 주변부 보조 통계다.
    peripheral = np.ones((height, width), dtype=bool)
    peripheral[round(height * .82):, :] = False
    peripheral[round(height * .15):round(height * .82), round(width * .30):round(width * .70)] = False

    tile_rows, tile_columns = 6, 8
    blank_tiles = 0
    considered_tiles = 0
    for row in range(tile_rows):
        for column in range(tile_columns):
            top, bottom = round(row * height / tile_rows), round((row + 1) * height / tile_rows)
            left, right = round(column * width / tile_columns), round((column + 1) * width / tile_columns)
            if top >= height * .82:
                continue
            mask = peripheral[top:bottom, left:right]
            if not mask.any():
                continue
            considered_tiles += 1
            tile_edges = edges[top:bottom, left:right][mask]
            tile_gray = gray[top:bottom, left:right][mask]
            if float(np.mean(tile_edges > 0)) < .018 and float(np.std(tile_gray)) < 24:
                blank_tiles += 1

    ocr = _tesseract_rows(path)
    in_scene = [row for row in ocr if row["top"] + row["height"] / 2 < height * .82]
    numeric = [row for row in in_scene if re.search(r"\d", row["text"])]
    largest_numeric = max(numeric, key=lambda row: row["width"] * row["height"], default=None)
    return {
        "frame": int(path.stem.split("_")[-1]),
        "mean_saturation": round(float(hsv[:, :, 1].mean()), 3),
        "p90_saturation": round(float(np.percentile(hsv[:, :, 1], 90)), 3),
        "luma_stddev": round(float(gray.std()), 3),
        "peripheral_edge_density": round(float(np.mean(edges[peripheral] > 0)), 6),
        "peripheral_blank_tile_ratio": round(blank_tiles / max(1, considered_tiles), 4),
        "in_scene_ocr_token_count": len(in_scene),
        "in_scene_numeric_token_count": len(numeric),
        "largest_numeric": None if largest_numeric is None else {
            "text": largest_numeric["text"],
            "center_x_ratio": round((largest_numeric["left"] + largest_numeric["width"] / 2) / width, 4),
            "center_y_ratio": round((largest_numeric["top"] + largest_numeric["height"] / 2) / height, 4),
            "height_ratio": round(largest_numeric["height"] / height, 4),
            "area_ratio": round(largest_numeric["width"] * largest_numeric["height"] / (width * height), 6),
        },
    }


def _summary(values: list[float]) -> dict[str, float]:
    data = np.asarray(values, dtype=float)
    return {
        "median": round(float(np.median(data)), 4),
        "p10": round(float(np.percentile(data, 10)), 4),
        "p90": round(float(np.percentile(data, 90)), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    classification = json.loads(args.classification.read_text(encoding="utf-8"))
    type_by_frame = {
        int(frame): item["id"]
        for item in classification["primary_background_types"]
        for frame in item["frames"]
    }
    rows = [_frame_metrics(path) for path in sorted(args.frames.glob("frame_*.jpg"))]
    if len(rows) != 69 or set(type_by_frame) != {row["frame"] for row in rows}:
        raise ValueError("69개 프레임과 배타적 유형 분류가 정확히 대응하지 않습니다.")
    for row in rows:
        row["background_type"] = type_by_frame[row["frame"]]

    group_summary = {}
    for background_type in DEVICE_ROLE_RULES:
        group = [row for row in rows if row["background_type"] == background_type]
        numeric = [row["largest_numeric"] for row in group if row["largest_numeric"]]
        group_summary[background_type] = {
            "frame_count": len(group),
            "saturation": _summary([row["mean_saturation"] for row in group]),
            "luma_contrast": _summary([row["luma_stddev"] for row in group]),
            "peripheral_edge_density": _summary([row["peripheral_edge_density"] for row in group]),
            "peripheral_blank_tile_ratio": _summary([row["peripheral_blank_tile_ratio"] for row in group]),
            "numeric_frames_detected_by_ocr": len(numeric),
            "largest_numeric_height_ratio": _summary([item["height_ratio"] for item in numeric]) if numeric else None,
            "largest_numeric_center_y_ratio": _summary([item["center_y_ratio"] for item in numeric]) if numeric else None,
            **DEVICE_ROLE_RULES[background_type],
        }
    payload = {
        "version": "wo-img02c-reference-composition-benchmark-v1",
        "scope": {
            "frame_count": 69,
            "character_exclusion": "중앙 인물 가능 영역과 하단 자막을 제외한 주변부 통계 프록시이며 캐릭터 정밀 분할 결과가 아님",
            "ocr_limit": "Tesseract가 읽은 화면 내 숫자의 재현율 하한이며 미검출을 숫자 부재로 해석하지 않음",
        },
        "group_summary": group_summary,
        "frames": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

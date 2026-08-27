#!/usr/bin/env python3
"""8장 파일럿 원장에서 실제 전송된 얼굴 참조 해시를 추출한다."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "artifacts/wo_img01_c3_eight_scene_pilot/pilot_manifest.json"
EXPECTED_V1_SHA256 = "3d113c43e9395435d1b07b6e5a015c17e606b246e7a4f177bd3de4d074489c45"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_report() -> dict:
    source = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for scene in source["scenes"]:
        entries = scene["request_summary"]["entries"]
        if len(entries) != 1:
            raise RuntimeError(f"scene {scene['index']} 요청 수가 1이 아닙니다: {len(entries)}")
        high_level = scene["references"]
        actual = entries[0]["request_evidence"]["references"]
        if high_level[0]["sha256"] != EXPECTED_V1_SHA256 or actual[0]["sha256"] != EXPECTED_V1_SHA256:
            raise RuntimeError(f"scene {scene['index']}의 첫 참조가 v1 해시가 아닙니다.")
        rows.append({
            "scene": scene["index"],
            "payload_sha256": entries[0]["request_evidence"]["payload_sha256"],
            "high_level_reference_names": [item["name"] for item in high_level],
            "high_level_reference_sha256": [item["sha256"] for item in high_level],
            "actual_request_reference_sha256": [item["sha256"] for item in actual],
            "v1_is_first_reference_in_both_records": True,
        })
    return {
        "schema_version": 1,
        "source": str(MANIFEST.relative_to(REPO)),
        "source_sha256": sha256(MANIFEST),
        "expected_v1_sha256": EXPECTED_V1_SHA256,
        "scene_count": len(rows),
        "all_scenes_sent_v1_first": all(row["v1_is_first_reference_in_both_records"] for row in rows),
        "scenes": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "scene_count": report["scene_count"],
        "all_scenes_sent_v1_first": report["all_scenes_sent_v1_first"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

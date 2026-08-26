"""저장된 대본을 수정하지 않고 엔티티 바인더 변경 전후를 전수 비교한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.utils.scene_entity_binder import bind_scene_entities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenes = json.loads(args.scenes.read_text())
    if not isinstance(scenes, list):
        scenes = scenes["scenes"]
    # 사용자 검토 범위는 scene 00~47이다. 이미지를 만들거나 메타데이터를 덮어쓰지 않는다.
    rows = []
    for scene in scenes[:48]:
        binding = bind_scene_entities([scene], [], [])[0]
        before = scene.get("core_entities", [])
        text = str(scene.get("content") or scene.get("text") or "").strip()
        assert binding.narration == text
        assert binding.narration_hash == hashlib.sha256(text.encode()).hexdigest()
        rows.append({
            "index": scene["index"], "narration": text,
            "narration_sha256_unchanged": binding.narration_hash,
            "before": before, "after": binding.core_entities,
            "removed": sorted(set(before) - set(binding.core_entities)),
            "added": sorted(set(binding.core_entities) - set(before)),
            "scope": "저장된 과거 binding과 현재 레지스트리만 비교; 당시 verified_facts 재연 아님",
        })
    report = {
        "source_sha256": hashlib.sha256(args.scenes.read_bytes()).hexdigest(),
        "scene_count": len(rows),
        "narration_hashes_preserved": len(rows),
        "before_commodity_scenes": {e: [r["index"] for r in rows if e in r["before"]] for e in ("금", "은")},
        "after_commodity_scenes": {e: [r["index"] for r in rows if e in r["after"]] for e in ("금", "은")},
        "scene_results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "scene_results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

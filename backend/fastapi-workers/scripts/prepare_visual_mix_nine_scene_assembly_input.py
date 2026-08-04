"""검수 완료된 9장과 TTS 매니페스트를 조립 입력으로 고정한다.

이미지·대본을 새로 만들지 않으며, 기사형·상황형·정보형의 기존 산출물만
컨테이너에서 읽을 수 있는 경로로 연결한다. 텍스트가 있는 9장에는 Kling을
강제하지 않아 이미지 안의 글자·캐릭터가 변형되는 것을 방지한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
INPUT_PATH = REPO_ROOT / "artifacts/diagnostics/visual_mix_nine_scene_tts_sync_input_20260803.json"
TTS_PATH = REPO_ROOT / "artifacts/diagnostics/tts_920260804_manifest.json"
OUTPUT_PATH = REPO_ROOT / "artifacts/diagnostics/visual_mix_nine_scene_assembly_input_20260803.json"


def _container_image_path(host_path: str) -> str:
    source = Path(host_path).resolve()
    try:
        relative = source.relative_to(WORKER_ROOT)
    except ValueError as exc:
        raise RuntimeError(f"작업자 경로 밖의 이미지입니다: {source}") from exc
    return "/app/" + relative.as_posix()


def main() -> int:
    visual_input = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    tts_meta = json.loads(TTS_PATH.read_text(encoding="utf-8"))
    scenes = []
    for index, raw_scene in enumerate(visual_input["sections"]):
        scene = dict(raw_scene)
        scene["index"] = index
        scene["image_path"] = _container_image_path(scene.pop("selected_asset_path"))
        scene["final_image_path"] = scene["image_path"]
        # 이 파일럿의 첫 장면은 기사·텍스트 자산이다. Kling이 글자나 얼굴을
        # 변형하지 않게 정적 조립으로 고정한다. Fal 검증은 별도 무문자 인트로에만 적용한다.
        scene["use_kling"] = False
        scenes.append(scene)

    payload = {
        "run_id": "visual_mix_nine_scene_assembly_20260803",
        "scope": "approved_nine_images_static_assembly_only",
        "tts_meta": tts_meta,
        "scenes": scenes,
        "gifs": [],
        "kling_started": False,
        "reason": "텍스트·기사형 9장 보호: 무문자 인트로 자산이 별도로 승인되기 전에는 Kling을 호출하지 않음",
        "thumbnail_started": False,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "scene_count": len(scenes),
        "canonical_sha256": tts_meta["canonical_sha256"],
        "kling_selected_scene_count": 0,
        "visual_modes": sorted({scene["visual_mode"] for scene in scenes}),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

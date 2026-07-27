"""기존 v4 갤러리의 생성 배경은 유지하고 결정론적 보드 잉크만 다시 합성한다."""
from __future__ import annotations

import json
from pathlib import Path

from app.workers.images_worker import ImagesWorker
from scripts.run_v4_template_gallery import JOB_ID, scenes


def main() -> None:
    job_dir = Path(f"/app/data/jobs/{JOB_ID}")
    image_dir = job_dir / "images"
    refreshed = []
    worker = ImagesWorker()
    for index, scene in enumerate(scenes()):
        image_path = image_dir / f"scene_{index:03d}.png"
        source_path = image_dir / f"scene_{index:03d}_source.png"
        if not image_path.is_file() or not source_path.is_file():
            raise FileNotFoundError(f"갤러리 원본이 없습니다: {image_path}")
        scene["source_image_path"] = str(source_path)
        worker._apply_image_overlays(scene, str(image_path))
        refreshed.append({**scene, "image_path": str(image_path)})
    result = {"job_id": JOB_ID, "scene_count": len(refreshed), "scenes": refreshed}
    (job_dir / "v4_template_gallery_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"job_id": JOB_ID, "refreshed": len(refreshed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""USTR 확정 공지 기반 v4 관세형 정보 장면을 실제로 생성한다."""
from __future__ import annotations

import json
from pathlib import Path

from app.utils.budget import record_cost
from app.workers.images_worker import ImagesWorker


JOB_ID = 94302
USTR_SOURCE = (
    "https://ustr.gov/about-us/policy-offices/press-office/press-releases/2024/"
    "september/ustr-finalizes-action-china-tariffs-following-statutory-four-year-review"
)


def main() -> None:
    output = Path(f"/app/data/jobs/{JOB_ID}/v4_tariff_validation_manifest.json")
    if output.is_file():
        result = json.loads(output.read_text(encoding="utf-8"))
        scene = result["scenes"][0]
        ImagesWorker()._apply_image_overlays(scene, scene["image_path"])
        ledger_path = output.parent / "cost_ledger.json"
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ledger = {"items": []}
        if not any(item.get("scene_key") == "image:0" for item in ledger.get("items", [])):
            record_cost(JOB_ID, "pro", scene_key="image:0")
        result["scenes"][0] = scene
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"job_id": JOB_ID, "resumed": True, "image": scene["image_path"]}, ensure_ascii=False))
        return

    scene = {
        "scene_id": "tariff-map-001",
        "title": "중국산 핵심 품목 관세",
        "content": "미국 USTR이 확정한 중국산 핵심 품목의 Section 301 관세율입니다.",
        "section": "data",
        "visual_type": "data_visual",
        "market_chart": {
            "verified": True,
            "source": "USTR Section 301 final action (2024-09-13)",
            "source_ref": USTR_SOURCE,
            "label": "중국산 핵심 품목 관세",
            "external_rates": [
                {"label": "전기차", "value": "100%", "source_refs": [USTR_SOURCE]},
                {"label": "전기차 배터리", "value": "25%", "source_refs": [USTR_SOURCE]},
            ],
        },
        "image_profile": {
            "tier": "pro",
            "model": "gemini-3-pro-image",
            "image_size": "2K",
            "reason": "v4 tariff template validation",
        },
    }
    result = ImagesWorker().generate(scenes_meta=[scene], job_id=JOB_ID)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "job_id": JOB_ID,
        "scene_count": result["scene_count"],
        "manifest": str(output),
        "image": result["scenes"][0]["image_path"] if result["scenes"] else None,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

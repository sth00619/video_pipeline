"""v4 정보 장면 템플릿 네 종류를 실제 생성·합성해 검증한다."""
from __future__ import annotations

import json
from pathlib import Path

from app.workers.images_worker import ImagesWorker


JOB_ID = 94304
USTR_SOURCE = (
    "https://ustr.gov/about-us/policy-offices/press-office/press-releases/2024/"
    "september/ustr-finalizes-action-china-tariffs-following-statutory-four-year-review"
)


def _item(label: str, value: str | None = None, *, emphasis: bool = False) -> dict:
    return {
        "label": label,
        "value": value,
        "emphasis": emphasis,
        "source_refs": [USTR_SOURCE],
    }


def _scene(scene_id: str, title: str, content: str, **payload: object) -> dict:
    return {
        "scene_id": scene_id,
        "title": title,
        "content": content,
        "section": "data",
        "visual_type": "data_visual",
        "market_chart": {
            "verified": True,
            "source": "USTR Section 301 final action (2024-09-13)",
            "source_ref": USTR_SOURCE,
            "label": title,
            "scene_seed": scene_id,
        },
        "image_profile": {
            "tier": "pro",
            "model": "gemini-3-pro-image",
            "image_size": "2K",
            "reason": "v4 template gallery verification",
        },
        **payload,
    }


def scenes() -> list[dict]:
    return [
        _scene(
            "vault-stages-001",
            "관세 적용 단계",
            "검증용 장면: 관세 적용 절차를 단계별로 보여줍니다.",
            stage_items=[
                _item("검토", "4년"),
                _item("확정", "2024", emphasis=True),
                _item("적용", "2024–26"),
            ],
        ),
        _scene(
            "blueprint-structure-001",
            "핵심 품목 구조",
            "검증용 장면: 공지에 언급된 핵심 품목을 구조적으로 보여줍니다.",
            structure_items=[
                _item("전기차", "100%", emphasis=True),
                _item("배터리", "25%"),
                _item("반도체", "50%"),
            ],
        ),
        _scene(
            "weather-rates-001",
            "중국산 핵심 품목 관세",
            "검증용 장면: USTR이 확정한 일부 중국산 핵심 품목 관세율입니다.",
            market_chart={
                "verified": True,
                "source": "USTR Section 301 final action (2024-09-13)",
                "source_ref": USTR_SOURCE,
                "label": "중국산 핵심 품목 관세",
                "scene_seed": "weather-rates-001",
                "external_rates": [
                    _item("전기차", "100%", emphasis=True),
                    _item("전기차 배터리", "25%"),
                ],
            },
        ),
        _scene(
            "chalk-flow-001",
            "관세 전달 경로",
            "검증용 장면: 관세가 비용 압력으로 전달되는 일반적인 경로를 보여줍니다.",
            causal_nodes=[
                _item("관세", "정책"),
                _item("비용", "상승"),
                _item("가격", "압력", emphasis=True),
            ],
            verdict_stamp="USTR 확정",
        ),
    ]


def main() -> None:
    output = Path(f"/app/data/jobs/{JOB_ID}/v4_template_gallery_manifest.json")
    result = ImagesWorker().generate(scenes_meta=scenes(), job_id=JOB_ID)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "job_id": JOB_ID,
        "scene_count": result["scene_count"],
        "manifest": str(output),
        "images": [scene.get("image_path") for scene in result.get("scenes", [])],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

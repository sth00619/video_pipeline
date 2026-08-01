"""사용자 레퍼런스의 계산대 화면을 검증된 코스피 종가로 교체한 무비용 미리보기."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.v5.overlay.diegetic_fact_overlay import SurfaceAnchor, VerifiedFact
from app.v5.overlay.in_scene_fact_templates import InSceneTemplate, apply_checkout_total


REFERENCE = Path(r"C:/Users/song/Downloads/사용자 첨부 파일 (1).png")
FACTS = ROOT / "out/v5_pilot/kospi_july_2026/verified_facts.json"
OUTPUT_DIR = ROOT / "out/v5_pilot/kospi_july_2026/checkout_surface_preview"


def main() -> None:
    if not REFERENCE.is_file():
        raise FileNotFoundError(f"레퍼런스 이미지를 찾을 수 없습니다: {REFERENCE}")
    facts = json.loads(FACTS.read_text(encoding="utf-8"))["facts"]
    source = facts[0]
    fact = VerifiedFact(
        label=str(source["overlay_label"]),
        value=str(source["figure"]),
        source_ref="facts[0]",
        # 이 좌표는 검증 대상이 아닌 렌더 템플릿 영역이며, 원본 POS의 붉은
        # 내부 LCD만 덮는다. 외부 베젤과 주변 소품은 보존한다.
        anchor=SurfaceAnchor(.225, .414, .125, .145, "embedded_monitor"),
    )
    template = InSceneTemplate("checkout_total", .225, .414, .125, .145)
    rendered = apply_checkout_total(REFERENCE.read_bytes(), fact, template)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = OUTPUT_DIR / "kospi_checkout_surface_preview.png"
    image_path.write_bytes(rendered)
    (OUTPUT_DIR / "provenance.json").write_text(json.dumps({
        "template": "checkout_total",
        "source_url": source["source_url"],
        "source_title": source["source_title"],
        "value": fact.value,
        "heading": "KOSPI CLOSE",
        "reference_image": str(REFERENCE),
        "edited_region": {"x": template.x, "y": template.y, "width": template.width, "height": template.height},
        "cost_usd": 0,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(image_path)


if __name__ == "__main__":
    main()

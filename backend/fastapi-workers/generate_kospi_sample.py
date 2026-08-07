"""
"코스피가 7,651.78포인트로, 3.17퍼센트 감소하여 마무리되었습니다." 문장에 대한
파이프라인 실제 이미지 생성 및 아키타입/프롬프트 분석 스크립트
"""
import os
import sys
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
    root_env = Path(__file__).resolve().parents[2] / ".env"
    if root_env.is_file():
        load_dotenv(root_env)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from app.utils.art_direction import direct_scenes
from app.workers.images_worker import ImagesWorker
from app.providers.real.image import NanaBananaProvider

os.environ["V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD"] = "0.04"

def generate_kospi_scene():
    narration = "코스피가 7,651.78포인트로, 3.17퍼센트 감소하여 마무리되었습니다."
    
    scenes = [{"index": 0, "content": narration}]
    directed = direct_scenes(scenes)[0]
    
    print("\n" + "=" * 70)
    print(f"[INPUT NARRATION] \"{narration}\"")
    print("=" * 70)
    print(f"1. 선택된 아키타입 (Archetype): {directed['archetype']}")
    print(f"   선택 사유 (Reason): {directed['archetype_reason']}")
    print(f"   추가 소품 (Props): {directed['specific_props']}")
    
    worker = ImagesWorker()
    
    # KOSPI 7651.78pt, -3.17% core_entities / figures 바인딩
    prompt_en = worker._build_prompt_from_narration(
        narration=narration,
        scene_type=directed['archetype'],
        title=directed['specific_props'],
        visual_mode="archetype_explainer",
        core_entities=["KOSPI"],
        core_figures=[
            {"raw": "7,651.78포인트", "kind": "index"},
            {"raw": "-3.17%", "kind": "percentage"}
        ]
    )
    
    safe_prompt = prompt_en[:300].encode('ascii', errors='ignore').decode('ascii')
    print(f"\n2. 구축된 영문 씬 프롬프트 (Prompt_EN):\n{safe_prompt}...\n")
    
    output_dir = Path(__file__).resolve().parents[0] / "out" / "pipeline_test_runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "kospi_drop_sample_scene.png"
    
    print("3. Gemini 3 Pro 이미지 렌더링 중 (7개 참조 자산 + 의상/모자/50-65% 비율 규칙 포함)...")
    provider = NanaBananaProvider()
    provider.generate(
        prompt=prompt_en,
        output_path=str(out_path),
        image_provider="gemini",
        gemini_model="gemini-3-pro-image",
        gemini_image_size="2K"
    )
    
    print(f"\n[SUCCESS] 이미지 생성 완료! 저장 위치: {out_path} ({out_path.stat().st_size:,} bytes)")
    return str(out_path)

if __name__ == "__main__":
    generate_kospi_scene()

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
from app.v5.scene.runtime_contract import attach_v5_scene_contracts
from app.workers.images_worker import ImagesWorker
from app.providers.real.image import NanaBananaProvider

os.environ["V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD"] = "0.04"

def generate_kospi_scene():
    narration = "코스피가 7,651.78포인트로, 3.17퍼센트 감소하여 마무리되었습니다."
    
    scenes = [{
        "index": 0,
        "scene_type": "metric",
        "content": narration,
        "verified_facts": [{
            "fact": "코스피 지수는 7,651.78포인트로 하락했다.",
            "figure": "7,651.78포인트",
            "source_field": "kr.chart_series.kospi"
        }]
    }]
    
    directed = direct_scenes(scenes)[0]
    planned = attach_v5_scene_contracts([directed])[0]
    
    print("\n" + "=" * 70)
    print(f"[INPUT NARRATION] \"{narration}\"")
    print("=" * 70)
    print(f"1. 선택된 아키타입: {planned['archetype']}")
    print(f"   v5_verified_overlays 평면 오버레이 미사용 확인 (None/[]): {planned.get('v5_verified_overlays')}")
    
    worker = ImagesWorker()
    
    # 지수명/브랜드명 KOSPI는 실명으로 프롬프트 전달, 숫자는 ASS 자막이 전담
    prompt_en = worker._build_prompt_from_narration(
        narration=narration,
        scene_type=planned['archetype'],
        title=planned['specific_props'],
        visual_mode="archetype_explainer",
        core_entities=["KOSPI"],
        core_figures=[{"raw": "7,651.78포인트", "kind": "index"}]
    )
    
    safe_prompt = prompt_en[:300].encode('ascii', errors='ignore').decode('ascii')
    print(f"\n2. 구축된 영문 씬 프롬프트 (Prompt_EN):\n{safe_prompt}...\n")
    
    output_dir = Path(__file__).resolve().parents[0] / "out" / "pipeline_test_runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "kospi_clean_role_divided_scene.png"
    
    print("3. 순수 씬 이미지 생성 (Pillow 평면 텍스트 오버레이 완전 제거)...")
    provider = NanaBananaProvider()
    provider.generate(
        prompt=prompt_en,
        output_path=str(out_path),
        image_provider="gemini",
        gemini_model="gemini-3-pro-image",
        gemini_image_size="2K"
    )
    
    print(f"\n[SUCCESS] 클린 씬 이미지 생성 완료! 저장 위치: {out_path} ({out_path.stat().st_size:,} bytes)")
    return str(out_path)

if __name__ == "__main__":
    generate_kospi_scene()

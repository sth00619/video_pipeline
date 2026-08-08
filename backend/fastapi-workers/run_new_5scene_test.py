"""
신규 5개 종합 검증 벤치마크 (테슬라 급등/PER 개념/LG엔솔&삼성SDI/국제유가/부동산 거래량) 테스트 스크립트
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

NEW_BENCHMARK_SCENES = [
    {
        "index": 0,
        "scene_type": "metric",
        "title": "Scene 1: Tesla Earnings Surge",
        "content": "테슬라가 예상을 뛰어넘는 실적을 발표하자 주가가 장중 8.4퍼센트 급등했습니다.",
        "core_entities": ["Tesla", "테슬라"],
        "core_figures": [{"raw": "+8.4%", "kind": "percentage"}],
        "filename": "new_benchmark_01_tesla_surge.png"
    },
    {
        "index": 1,
        "scene_type": "general",
        "title": "Scene 2: PER Concept Classroom Cap Test",
        "content": "개념부터 짚고 가겠습니다. PER이란 주가를 주당순이익으로 나눈 값으로, 기업이 고평가인지 저평가인지 가늠하는 지표입니다.",
        "core_entities": ["PER"],
        "core_figures": [],
        "filename": "new_benchmark_02_per_classroom.png"
    },
    {
        "index": 2,
        "scene_type": "general",
        "title": "Scene 3: LG Energy & Samsung SDI Battery Plants",
        "content": "LG에너지솔루션과 삼성SDI가 나란히 미국 배터리 공장 증설 계획을 발표했습니다.",
        "core_entities": ["LG Energy Solution", "Samsung SDI", "LG에너지솔루션", "삼성SDI"],
        "core_figures": [],
        "filename": "new_benchmark_03_battery_plants.png"
    },
    {
        "index": 3,
        "scene_type": "metric",
        "title": "Scene 4: Oil Price $92 Barrel Middle East Risk",
        "content": "중동발 지정학적 리스크로 국제유가가 배럴당 92달러를 돌파하며 국내 정유주가 일제히 강세를 보였습니다.",
        "core_entities": ["WTI Crude Oil", "국제유가"],
        "core_figures": [{"raw": "$92/barrel", "kind": "price"}],
        "filename": "new_benchmark_04_oil_price_surge.png"
    },
    {
        "index": 4,
        "scene_type": "metric",
        "title": "Scene 5: Seoul Apartment Real Estate Office Drop",
        "content": "부동산 시장이 얼어붙었습니다. 서울 아파트 거래량이 전월 대비 42퍼센트 급감했습니다.",
        "core_entities": ["Seoul Apartment", "부동산 시장"],
        "core_figures": [{"raw": "-42%", "kind": "percentage"}],
        "filename": "new_benchmark_05_real_estate_drop.png"
    }
]

def run_new_benchmark():
    import argparse
    parser = argparse.ArgumentParser(description="New 5-Scene Benchmark Test")
    parser.add_argument("--scene", type=int, choices=[1, 2, 3, 4, 5], help="Target single scene number (1 to 5) to generate")
    args = parser.parse_args()

    output_dir = Path(__file__).resolve().parents[0] / "out" / "pipeline_test_runs" / "new_benchmark_5scenes"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    scenes_to_run = NEW_BENCHMARK_SCENES
    if args.scene:
        scenes_to_run = [NEW_BENCHMARK_SCENES[args.scene - 1]]

    print("\n" + "=" * 80)
    print(f"[START] New 5-Scene Comprehensive Benchmark Generation (Selected Scenes: {len(scenes_to_run)})")
    print("=" * 80)
    
    # 1. direct_scenes & attach_v5_scene_contracts
    directed_scenes = direct_scenes(NEW_BENCHMARK_SCENES)
    planned_scenes = attach_v5_scene_contracts(directed_scenes)
    
    # Filter planned scenes if single scene selected
    if args.scene:
        target_idx = args.scene - 1
        planned_scenes = [p for p in planned_scenes if p["index"] == target_idx]
    
    worker = ImagesWorker()
    provider = NanaBananaProvider()
    
    results = []
    for item in planned_scenes:
        idx = item["index"]
        meta = NEW_BENCHMARK_SCENES[idx]
        print(f"\n----------------------------------------------------------------------")
        print(f"[{meta['title']}] (Index: {idx})")
        print(f"Narration: \"{meta['content']}\"")
        print(f"-> Archetype: {item['archetype']}")
        print(f"-> Reason: {item['archetype_reason']}")
        
        prompt_en = worker._build_prompt_from_narration(
            narration=meta['content'],
            scene_type=item['archetype'],
            title=item['specific_props'],
            visual_mode="archetype_explainer",
            core_entities=meta['core_entities'],
            core_figures=meta['core_figures']
        )
        
        out_path = output_dir / meta['filename']
        print(f"-> Generating Gemini 3 Pro 2K image...")
        
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                provider.generate(
                    prompt=prompt_en,
                    output_path=str(out_path),
                    image_provider="gemini",
                    gemini_model="gemini-3-pro-image",
                    gemini_image_size="2K"
                )
                break
            except Exception as exc:
                if "429" in str(exc) and attempt < max_retries - 1:
                    print(f"-> [QUOTA NOTICE] Rate limit hit (429). Waiting 35 seconds before retry {attempt+2}/{max_retries}...")
                    time.sleep(35)
                else:
                    raise exc
        
        print(f"-> [SUCCESS] Scene generated: {out_path} ({out_path.stat().st_size:,} bytes)")
        time.sleep(5)
        results.append({
            "index": idx,
            "title": meta['title'],
            "narration": meta['content'],
            "archetype": item['archetype'],
            "path": str(out_path)
        })
        
    print("\n" + "=" * 80)
    print("[FINISHED] Scene Generation Complete!")
    print("=" * 80)
    for r in sorted(results, key=lambda x: x["index"]):
        print(f"- Scene {r['index']+1}: {r['title']} | Archetype: {r['archetype']} | Path: {r['path']}")

if __name__ == "__main__":
    run_new_benchmark()

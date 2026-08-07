"""
5개 벤치마크 씬 (상승/실명동시노출/상반대조/%p구분/미국시장) 테스트 및 이미지 생성 스크립트
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

BENCHMARK_SCENES = [
    {
        "index": 0,
        "scene_type": "metric",
        "title": "Scene 1: KOSPI Record Surge",
        "content": "코스피가 2,847.35포인트로, 4.12퍼센트 급등하며 사상 최고치를 새로 썼습니다.",
        "core_entities": ["KOSPI"],
        "core_figures": [{"raw": "2,847.35포인트", "kind": "index"}, {"raw": "+4.12%", "kind": "percentage"}],
        "filename": "benchmark_scene_01_kospi_surge.png"
    },
    {
        "index": 1,
        "scene_type": "general",
        "title": "Scene 2: Dual Real Names HBM Shortage",
        "content": "SK하이닉스와 삼성전자가 동시에 HBM 공급 부족을 발표하면서 반도체 업종 전체가 들썩였습니다.",
        "core_entities": ["SK하이닉스", "삼성전자", "HBM"],
        "core_figures": [],
        "filename": "benchmark_scene_02_hbm_dual_names.png"
    },
    {
        "index": 2,
        "scene_type": "diagram",
        "title": "Scene 3: Split Earnings Performance",
        "content": "삼성전자는 이번 분기 영업이익이 12조 원을 넘겼지만, SK하이닉스는 시장 예상치를 밑돌며 주가가 급락했습니다.",
        "core_entities": ["삼성전자", "SK하이닉스"],
        "core_figures": [{"raw": "12조 원", "kind": "currency"}],
        "filename": "benchmark_scene_03_split_earnings.png"
    },
    {
        "index": 3,
        "scene_type": "metric",
        "title": "Scene 4: Fed Rate Cut (%p Unit Accuracy)",
        "content": "미국 연준이 기준금리를 0.25퍼센트포인트 인하하면서 원달러 환율이 즉각 하락했습니다.",
        "core_entities": ["미국 연준", "원달러 환율"],
        "core_figures": [{"raw": "-0.25%p", "kind": "percentage_point"}],
        "filename": "benchmark_scene_04_fed_rate_cut_pp.png"
    },
    {
        "index": 4,
        "scene_type": "metric",
        "title": "Scene 5: US Tech Alliance Nasdaq Surge",
        "content": "애플과 엔비디아가 AI 반도체 동맹을 발표하자 나스닥이 3.8퍼센트 뛰어올랐습니다.",
        "core_entities": ["애플", "엔비디아", "나스닥"],
        "core_figures": [{"raw": "+3.8%", "kind": "percentage"}],
        "filename": "benchmark_scene_05_us_tech_nasdaq.png"
    }
]

def run_benchmark():
    output_dir = Path(__file__).resolve().parents[0] / "out" / "pipeline_test_runs" / "benchmark_5scenes"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "=" * 80)
    print("[START] 5 Scene Benchmark Archetype & Image Generation")
    print("=" * 80)
    
    # 1. direct_scenes & attach_v5_scene_contracts
    directed_scenes = direct_scenes(BENCHMARK_SCENES)
    planned_scenes = attach_v5_scene_contracts(directed_scenes)
    
    worker = ImagesWorker()
    provider = NanaBananaProvider()
    
    results = []
    for item in planned_scenes:
        idx = item["index"]
        meta = BENCHMARK_SCENES[idx]
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
        provider.generate(
            prompt=prompt_en,
            output_path=str(out_path),
            image_provider="gemini",
            gemini_model="gemini-3-pro-image",
            gemini_image_size="2K"
        )
        
        print(f"-> [SUCCESS] Scene generated: {out_path} ({out_path.stat().st_size:,} bytes)")
        results.append({
            "index": idx,
            "title": meta['title'],
            "narration": meta['content'],
            "archetype": item['archetype'],
            "path": str(out_path)
        })
        
    print("\n" + "=" * 80)
    print("[FINISHED] 5 Scene Generation Complete!")
    print("=" * 80)
    for r in sorted(results, key=lambda x: x["index"]):
        print(f"- Scene {r['index']+1}: {r['title']} | Archetype: {r['archetype']} | Path: {r['path']}")

if __name__ == "__main__":
    run_benchmark()

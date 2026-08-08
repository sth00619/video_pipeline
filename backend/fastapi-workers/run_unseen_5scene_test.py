"""
완전히 새로운 5개 미학습 씬 일반화 규칙 검증 스크립트 (run_unseen_5scene_test.py)
"""
import os
import sys
import logging
import time
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
from app.utils.scene_content_classifier import classify_narration_content_type

os.environ["V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD"] = "0.04"

UNSEEN_BENCHMARK_SCENES = [
    {
        "index": 0,
        "scene_type": "general",
        "title": "Unseen Scene 1: ROE Concept Explainer",
        "content": "ROE란 자기자본이익률로, 기업이 주주의 돈을 얼마나 효율적으로 활용해 이익을 냈는지 보여주는 핵심 지표입니다.",
        "core_entities": ["ROE", "자기자본이익률"],
        "core_figures": [],
        "filename": "unseen_01_roe_concept.png"
    },
    {
        "index": 1,
        "scene_type": "general",
        "title": "Unseen Scene 2: Kakao AI Subscription Plan Release",
        "content": "카카오가 하반기 새로운 AI 구독 서비스 요금제 출시 계획을 전격 발표했습니다.",
        "core_entities": ["카카오"],
        "core_figures": [],
        "filename": "unseen_02_kakao_ai_plan.png"
    },
    {
        "index": 2,
        "scene_type": "metric",
        "title": "Unseen Scene 3: Copper Surge $9,500/ton Macro Supply Risk",
        "content": "글로벌 정련소 공급 차질로 구리 가격이 톤당 9,500달러를 돌파하며 최고치를 경신했습니다.",
        "core_entities": ["구리", "Copper"],
        "core_figures": [{"raw": "$9,500/ton", "kind": "price"}],
        "filename": "unseen_03_copper_surge.png"
    },
    {
        "index": 3,
        "scene_type": "diagram",
        "title": "Unseen Scene 4: Hyundai Motor Surge vs Kia Plunge Comparison",
        "content": "현대차는 미국 서부 공장 판매량이 15퍼센트 급증한 반면, 기아는 부품 공급난으로 출고량이 하락했습니다.",
        "core_entities": ["현대차", "기아"],
        "core_figures": [{"raw": "+15%", "kind": "percentage"}],
        "filename": "unseen_04_hyundai_kia_split.png"
    },
    {
        "index": 4,
        "scene_type": "metric",
        "title": "Unseen Scene 5: KOSDAQ Index 5% Plunge Market Selloff",
        "content": "코스닥 지수가 5퍼센트 폭락하며 시장에 매도세가 쏟아졌습니다.",
        "core_entities": ["코스닥", "KOSDAQ"],
        "core_figures": [{"raw": "-5%", "kind": "percentage"}],
        "filename": "unseen_05_kosdaq_plunge.png"
    }
]

def run_unseen_benchmark():
    import argparse
    parser = argparse.ArgumentParser(description="Unseen 5-Scene Generalization Benchmark Test")
    parser.add_argument("--scene", type=int, choices=[1, 2, 3, 4, 5], help="Target single scene number (1 to 5) to generate")
    args = parser.parse_args()

    output_dir = Path(__file__).resolve().parents[0] / "out" / "pipeline_test_runs" / "unseen_benchmark_5scenes"
    output_dir.mkdir(parents=True, exist_ok=True)

    directed_scenes = direct_scenes(UNSEEN_BENCHMARK_SCENES)
    planned_scenes = attach_v5_scene_contracts(directed_scenes)

    if args.scene:
        target_idx = args.scene - 1
        planned_scenes = [p for p in planned_scenes if p["index"] == target_idx]

    worker = ImagesWorker()
    provider = NanaBananaProvider()

    results = []
    print("\n" + "=" * 80)
    print(f"[START] Unseen 5-Scene Content Classifier Benchmark (Target Count: {len(planned_scenes)})")
    print("=" * 80)

    for item in planned_scenes:
        idx = item["index"]
        meta = UNSEEN_BENCHMARK_SCENES[idx]
        strategy = classify_narration_content_type(meta['content'], meta['core_entities'], meta['core_figures'])

        print(f"\n----------------------------------------------------------------------")
        print(f"[{meta['title']}] (Index: {idx})")
        print(f"Narration: \"{meta['content']}\"")
        print(f"-> Classified Content Type: {strategy.content_type.upper()}")
        print(f"-> Label Rule: {strategy.label_text_rule}")
        print(f"-> Archetype Assigned: {item['archetype']}")

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
            "content_type": strategy.content_type,
            "archetype": item['archetype'],
            "path": str(out_path)
        })

    print("\n" + "=" * 80)
    print("[FINISHED] Unseen 5-Scene Benchmark Generation Complete!")
    print("=" * 80)
    for r in sorted(results, key=lambda x: x["index"]):
        print(f"- Scene {r['index']+1}: {r['title']} | Type: {r['content_type'].upper()} | Archetype: {r['archetype']} | Path: {r['path']}")

if __name__ == "__main__":
    run_unseen_benchmark()

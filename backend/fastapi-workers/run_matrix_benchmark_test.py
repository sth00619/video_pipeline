"""
200개+ 레지스트리 Hit/Miss 10종 교차 검증 매트릭스 실행 스크립트 (run_matrix_benchmark_test.py)
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
from app.utils.entity_english_map import get_entity_english_name

os.environ["V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD"] = "0.04"

MATRIX_BENCHMARK_SCENES = [
    # 1. concept_explainer
    {
        "index": 0,
        "scene_type": "general",
        "title": "Matrix 01: Concept Explainer - Hit (PER)",
        "content": "개념부터 짚고 가겠습니다. PER이란 주가를 주당순이익으로 나눈 값으로, 기업이 고평가인지 저평가인지 가늠하는 지표입니다.",
        "core_entities": ["PER"],
        "core_figures": [],
        "filename": "matrix_01_concept_hit_per.png"
    },
    {
        "index": 1,
        "scene_type": "general",
        "title": "Matrix 02: Concept Explainer - Miss (PSR)",
        "content": "개념부터 짚고 가겠습니다. PSR이란 주가를 주당매출액으로 나눈 값으로, 매출 대비 주가 수준을 가늠하는 지표입니다.",
        "core_entities": ["PSR"],
        "core_figures": [],
        "filename": "matrix_02_concept_miss_psr.png"
    },
    # 2. entity_news
    {
        "index": 2,
        "scene_type": "general",
        "title": "Matrix 03: Entity News - Hit (삼성전자)",
        "content": "삼성전자가 이번 분기 세계 최초 차세대 반도체 공정 양산 성공 소식을 전격 발표했습니다.",
        "core_entities": ["삼성전자"],
        "core_figures": [],
        "filename": "matrix_03_news_hit_samsung.png"
    },
    {
        "index": 3,
        "scene_type": "general",
        "title": "Matrix 04: Entity News - Miss (한미반도체)",
        "content": "한미반도체가 신규 반도체 패키징 장비 대규모 공급 계약 체결 소식을 발표했습니다.",
        "core_entities": ["한미반도체"],
        "core_figures": [],
        "filename": "matrix_04_news_miss_hanmi.png"
    },
    # 3. market_index_move
    {
        "index": 4,
        "scene_type": "metric",
        "title": "Matrix 05: Market Index Move - Hit (코스피)",
        "content": "코스피가 2,847포인트로 급등하며 사상 최고치를 경신했습니다.",
        "core_entities": ["코스피"],
        "core_figures": [{"raw": "2,847pt", "kind": "points"}],
        "filename": "matrix_05_index_hit_kospi.png"
    },
    {
        "index": 5,
        "scene_type": "metric",
        "title": "Matrix 06: Market Index Move - Miss (동티모르지수)",
        "content": "동티모르지수가 3퍼센트 폭락하며 아시아 증시 전반에 매도세가 확대되었습니다.",
        "core_entities": ["동티모르지수"],
        "core_figures": [{"raw": "-3%", "kind": "percentage"}],
        "filename": "matrix_06_index_miss_timor.png"
    },
    # 4. macro_geopolitical
    {
        "index": 6,
        "scene_type": "metric",
        "title": "Matrix 07: Macro Geopolitical - Hit (WTI)",
        "content": "중동발 지정학적 리스크 심화로 WTI 국제유가가 배럴당 92달러를 돌파했습니다.",
        "core_entities": ["WTI"],
        "core_figures": [{"raw": "$92/barrel", "kind": "price"}],
        "filename": "matrix_07_macro_hit_wti.png"
    },
    {
        "index": 7,
        "scene_type": "metric",
        "title": "Matrix 08: Macro Geopolitical - Miss (아연)",
        "content": "남미 광산 파업으로 아연 가격이 톤당 급등하며 비철금속 시장이 들썩였습니다.",
        "core_entities": ["아연"],
        "core_figures": [],
        "filename": "matrix_08_macro_miss_zinc.png"
    },
    # 5. comparison
    {
        "index": 8,
        "scene_type": "diagram",
        "title": "Matrix 09: Comparison - Hit Pair (현대차 vs 기아)",
        "content": "현대차는 미국 서부 공장 판매량이 급증한 반면, 기아는 부품 공급난으로 출고량이 하락했습니다.",
        "core_entities": ["현대차", "기아"],
        "core_figures": [],
        "filename": "matrix_09_comparison_hit_pair.png"
    },
    {
        "index": 9,
        "scene_type": "diagram",
        "title": "Matrix 10: Comparison - Mixed Pair (삼성전자 Hit vs 한미반도체 Miss)",
        "content": "삼성전자는 글로벌 메모리 반도체 매출이 급증한 반면, 한미반도체는 신규 장비 검사가 지연되며 출고가 하락했습니다.",
        "core_entities": ["삼성전자", "한미반도체"],
        "core_figures": [],
        "filename": "matrix_10_comparison_mixed_pair.png"
    }
]

def run_matrix_benchmark():
    import argparse
    parser = argparse.ArgumentParser(description="10-Scene Cross Matrix Validation Benchmark Runner")
    parser.add_argument("--scene", type=int, choices=list(range(1, 11)), help="Target single scene number (1 to 10)")
    args = parser.parse_args()

    output_dir = Path(__file__).resolve().parents[0] / "out" / "pipeline_test_runs" / "matrix_benchmark_10scenes"
    output_dir.mkdir(parents=True, exist_ok=True)

    directed_scenes = direct_scenes(MATRIX_BENCHMARK_SCENES)
    planned_scenes = attach_v5_scene_contracts(directed_scenes)

    if args.scene:
        target_idx = args.scene - 1
        planned_scenes = [p for p in planned_scenes if p["index"] == target_idx]

    worker = ImagesWorker()
    provider = NanaBananaProvider()

    results = []
    print("\n" + "=" * 85)
    print(f"[START] 10-Scene Cross Matrix Validation Benchmark (Target Count: {len(planned_scenes)})")
    print("=" * 85)

    for item in planned_scenes:
        idx = item["index"]
        meta = MATRIX_BENCHMARK_SCENES[idx]
        strategy = classify_narration_content_type(meta['content'], meta['core_entities'], meta['core_figures'])

        mappings = [get_entity_english_name(e) for e in meta['core_entities']]
        map_str = ", ".join(f"{e} -> {name} ({conf})" for e, (name, conf) in zip(meta['core_entities'], mappings))

        print(f"\n----------------------------------------------------------------------")
        print(f"[{meta['title']}] (Index: {idx})")
        print(f"Narration: \"{meta['content']}\"")
        print(f"-> Classified Content Type: {strategy.content_type.upper()}")
        print(f"-> Entity Mappings: {map_str}")
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
        time.sleep(4)
        results.append({
            "index": idx,
            "title": meta['title'],
            "content_type": strategy.content_type,
            "mapping": map_str,
            "archetype": item['archetype'],
            "path": str(out_path)
        })

    print("\n" + "=" * 85)
    print("[FINISHED] 10-Scene Cross Matrix Validation Complete!")
    print("=" * 85)
    for r in sorted(results, key=lambda x: x["index"]):
        print(f"- Scene {r['index']+1}: {r['title']} | Type: {r['content_type'].upper()} | Mappings: {r['mapping']} | Path: {r['path']}")

if __name__ == "__main__":
    run_matrix_benchmark()

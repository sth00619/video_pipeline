"""
파이프라인 아키타입 분배 및 이미지 생성 검증 스크립트.
ImagesWorker와 direct_scenes()를 통해 10개 씬의 파이프라인 아키타입 및 캡을 검증한다.
"""
import os
import sys
import json
import logging
from pathlib import Path

# python-dotenv로 .env 로드
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

# 단가 설정
os.environ["V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD"] = "0.04"

# 10개 실전 대본 씬
SCRIPT_10_SCENES = [
    {"index": 0, "content": "반도체 업황이 좋다고들 합니다."},
    {"index": 1, "content": "그런데 SK하이닉스 ADR은 급락했습니다."},
    {"index": 2, "content": "이 두 가지가 동시에 사실일 수 있을까요?"},
    {"index": 3, "content": "지금 시장이 바로 그 상황입니다."},
    {"index": 4, "content": "실적 발표를 앞두고 경계 심리가 퍼졌습니다."},
    {"index": 5, "content": "엔비디아는 올랐지만 ADR은 반대로 움직였습니다."},
    {"index": 6, "content": "단순 악재가 아니라 불확실성의 엇갈림입니다."},
    {"index": 7, "content": "그러면 업황 지표는 어떤 신호를 보낼까요?"},
    {"index": 8, "content": "샌디스크는 조정 영업이익 10조 원을 넘겼습니다. 8개 기업과 4년 장기 계약도 맺었습니다."},
    {"index": 9, "content": "하이닉스 실적이 아닌 점, 주의하세요. 그래도 낸드 수요가 살아있다는 근거는 됩니다."}
]

def run_archetype_and_generation_pipeline():
    print("=" * 70)
    print("[STEP 1] direct_scenes() 아키타입 매핑 및 classroom 캡 검증")
    print("=" * 70)
    
    directed_scenes = direct_scenes(SCRIPT_10_SCENES)
    
    archetypes = [s["archetype"] for s in directed_scenes]
    classroom_count = archetypes.count("classroom")
    total_count = len(directed_scenes)
    classroom_cap = max(1, round(total_count * 0.15))
    
    print(f"총 씬 수: {total_count}")
    print(f"classroom 캡(max 15%): {classroom_cap}개 이하")
    print(f"실제 배정된 classroom 개수: {classroom_count}개")
    print("\n씬별 배정 결과:")
    for idx, sc in enumerate(directed_scenes):
        print(f"  Scene {idx+1:02d}: archetype='{sc['archetype']}' (사유: {sc['archetype_reason']})")
        print(f"           대사: \"{sc['content']}\"")
        print()
    
    print(f"아키타입 분포: {dict((a, archetypes.count(a)) for a in set(archetypes))}")
    
    if classroom_count <= classroom_cap:
        print(f"[PASS] classroom 갯수 ({classroom_count}개)가 캡 ({classroom_cap}개) 이내입니다.\n")
    else:
        print(f"[FAIL] classroom 갯수 ({classroom_count}개)가 캡 ({classroom_cap}개)을 초과했습니다!\n")
        return
        
    print("=" * 70)
    print("[STEP 2] ImagesWorker 실제 파이프라인으로 씬 프롬프트 생성 및 이미지 렌더링 검증")
    print("=" * 70)
    
    worker = ImagesWorker()
    output_dir = Path(__file__).resolve().parents[0] / "out" / "pipeline_test_runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 10개 씬 중 주요 테스트 씬 3개 렌더링
    from app.providers.real.image import NanaBananaProvider
    provider = NanaBananaProvider()
    
    test_target_indices = [0, 5, 8]
    generated_results = []
    
    for t_idx in test_target_indices:
        sc = directed_scenes[t_idx]
        print(f"\n--- [생성 중] Scene {sc['index']+1}: archetype={sc['archetype']} ---")
        print(f"대사: \"{sc['content']}\"")
        
        prompt_en = worker._build_prompt_from_narration(
            narration=sc['content'],
            scene_type=sc['archetype'],
            title=sc['specific_props'],
            visual_mode="archetype_explainer",
            core_entities=["Sandisk", "SK Hynix"] if t_idx in [1, 8] else ["Semiconductor"],
            core_figures=[{"raw": "10조 원", "kind": "metric"}] if t_idx == 8 else []
        )
        
        safe_prompt = prompt_en[:250].encode('ascii', errors='ignore').decode('ascii')
        print(f"파이프라인 구축 프롬프트 (first 250 chars):\n{safe_prompt}...")
        
        # 칠판 직역 도배 금지 지침 포함 여부 검증
        if "literally translate" in prompt_en.lower() or "not translate narration" in prompt_en.lower():
            print("  [CHECK] anti-literal-translation 프롬프트 지침 포함 확인됨 (PASS)")
        else:
            print("  [WARNING] anti-literal-translation 프롬프트 지침 미포함 (WARNING)")
            
        out_path = output_dir / f"pipeline_scene_{sc['index']+1:02d}_{sc['archetype']}.png"
        
        # NanaBananaProvider()로 Gemini API 파이프라인 생성 (7개 참조 이미지 자동 로드)
        provider.generate(
            prompt=prompt_en,
            output_path=str(out_path),
            image_provider="gemini",
            gemini_model="gemini-3-pro-image",
            gemini_image_size="2K"
        )
        print(f"  [SUCCESS] 파이프라인 이미지 생성 완료 -> {out_path} ({out_path.stat().st_size:,} bytes)")
        generated_results.append(str(out_path))

    print("\n============================================================")
    print("[FINAL] 모든 검증 및 생성 완료")
    print(f"생성된 파일 {len(generated_results)}개:")
    for path in generated_results:
        print(f"  - {path}")
    print("============================================================\n")

if __name__ == "__main__":
    run_archetype_and_generation_pipeline()

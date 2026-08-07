"""
대본 문장에 따른 단독 이미지 생성 테스트 스크립트.
수정된 GeminiProvider를 사용해 실제 이미지를 생성하고 로그를 확인한다.
"""
import os
import sys
import logging
from pathlib import Path

# python-dotenv를 사용해 루트 .env 로드
try:
    from dotenv import load_dotenv
    root_env = Path(__file__).resolve().parents[2] / ".env"
    if root_env.is_file():
        load_dotenv(root_env)
        print(f"[ENV] Loaded env from {root_env}")
except ImportError:
    pass

# 콘솔에 INFO 로그(감사 로그 포함) 출력 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from app.v5.providers.gemini_provider import GeminiProvider, GeminiModel

# 단가 환경변수 설정 (Preflight/Estimate용)
os.environ["V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD"] = "0.04"

def generate_test_scene():
    # 요청 대본: "샌디스크는 조정 영업이익 10조 원을 넘겼습니다. 8개 기업과 4년 장기 계약도 맺었습니다."
    script_text = "샌디스크는 조정 영업이익 10조 원을 넘겼습니다. 8개 기업과 4년 장기 계약도 맺었습니다."
    
    # 씬 구성 프롬프트 (우리 채널 기존 스타일 3~8번 문법 반영: 의상, 둥근 금화, 텍스트 사인보드/소품)
    scene_prompt = (
        "A 2D cartoon scene featuring our official channel mascot (round gold coin character with big expressive eyes, black eyebrows, rosy cheeks, wearing white gloves, brown shoes, and a professional suit with a tie). "
        "The mascot is standing in an analyst office or data room setting, pointing enthusiastically at a large blackboard and screen display. "
        "On the screen and board, clear text signage and infographics are explicitly displayed: "
        "'SANDISK: OPERATING PROFIT OVER 10 TRILLION KRW' and '4-YEAR LONG-TERM CONTRACT WITH 8 COMPANIES'. "
        "The character is wearing a neat business suit (navy suit jacket, white shirt, red tie). "
        "Style matches the provided reference images: bold clean outlines, vibrant cel shading, high contrast, clean typography on boards."
    )
    
    print("\n============================================================")
    print(f"[TEST RUN] 대본: {script_text}")
    print("============================================================\n")
    
    provider = GeminiProvider()
    
    output_dir = Path(__file__).resolve().parents[0] / "out" / "test_generations"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        result = provider.generate(
            prompt=scene_prompt,
            model=GeminiModel.PRO,
            width=1920,
            height=1080
        )
        
        save_path = output_dir / "sandisk_profit_scene.png"
        save_path.write_bytes(result.image_bytes)
        
        print("\n============================================================")
        print(f"[SUCCESS] 이미지 생성 완료!")
        print(f"저장 위치: {save_path}")
        print(f"이미지 크기: {len(result.image_bytes):,} bytes")
        print("============================================================\n")
        return str(save_path)
    except Exception as e:
        print(f"\n[ERROR] 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    generate_test_scene()

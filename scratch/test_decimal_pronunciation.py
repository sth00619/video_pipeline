import sys
import os

# backend/fastapi-workers 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend", "fastapi-workers"))

from app.workers.tts_worker import TtsWorker

def test_preprocessing():
    worker = TtsWorker()
    
    test_cases = [
        ("6.56", "육 점 오육"),
        ("1.125", "일 점 일이오"),
        ("0.05", "영 점 영오"),
        ("15.0", "십오 점 영"),
        ("7,246", "칠천이백사십육"),
        ("반도체 주가가 +5.56% 급등했습니다.", "반도체 주가가 플러스 오 점 오육퍼센트 급등했습니다."),
    ]
    
    success = True
    for original, expected in test_cases:
        actual = worker._preprocess_for_tts(original)
        if actual == expected:
            print(f"[SUCCESS] '{original}' -> '{actual}'")
        else:
            print(f"[FAIL] '{original}' -> expected '{expected}', got '{actual}'")
            success = False
            
    if success:
        print("\nAll preprocessing tests passed successfully!")
    else:
        print("\nSome tests failed. Please check the logic.")

if __name__ == "__main__":
    test_preprocessing()

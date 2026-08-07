"""
gemini_provider._load_default_references() 단독 검증.
API 키 없이도 실행 가능 — 파일 존재 여부와 해시만 확인한다.
"""
import hashlib
import logging
import sys
from pathlib import Path

# 로거를 stdout 으로 설정해 로그를 콘솔에서 바로 확인한다.
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

# 프로젝트 루트에서 임포트
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.v5.providers.gemini_provider import _load_default_references, _SCENE_STYLE_REF_NAMES

print("=" * 60)
print("[검증] _load_default_references() 반환 자산 목록")
print("=" * 60)

paths = _load_default_references()
print(f"총 참조 자산 수: {len(paths)}\n")

expected_count = 7  # character + style + scene_ref 5개
for idx, p_str in enumerate(paths, start=1):
    p = Path(p_str)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    size_kb = p.stat().st_size // 1024
    role = (
        "character_identity" if "character_reference" in p.name else
        "style_sheet"       if "style_reference_v4" in p.name else
        "scene_style_example"
    )
    status = "OK" if p.is_file() else "MISSING"
    print(f"  [{idx}] [{status}] role={role}")
    print(f"        name : {p.name}")
    print(f"        sha256: {sha}")
    print(f"        size : {size_kb} KB")
    print()

print("=" * 60)
if len(paths) == expected_count:
    print(f"[PASS] 참조 자산 {expected_count}개 모두 정상 등록됨.")
else:
    print(f"[FAIL] 예상 {expected_count}개 / 실제 {len(paths)}개")

print()
print("[씬 스타일 예시 파일명 고정 목록]")
for name in _SCENE_STYLE_REF_NAMES:
    print(f"  - {name}")
print("=" * 60)

"""
01~05 씬 레퍼런스 이미지를 out/references/ 에 등록하고
reference_manifest_v4_identity_style_clean.json 을 갱신한다.
"""
from pathlib import Path
import shutil, hashlib, json

src_dir = Path(__file__).resolve().parents[4] / "final plan" / "style reference"
dst_dir = Path(__file__).resolve().parent

mapping = [
    ("01_port_emergency_항구비상.png",   "style_scene_ref_01_port.png"),
    ("02_split_stage_무대비교.png",       "style_scene_ref_02_split.png"),
    ("03_retail_shock_마트쇼크.png",      "style_scene_ref_03_retail.png"),
    ("04_weather_map_기상캐스터_v1.png",  "style_scene_ref_04_weather.png"),
    ("05_weather_map_기상캐스터_v2.png",  "style_scene_ref_05_weather_v2.png"),
]

print("=== [STEP 1] 씬 레퍼런스 파일 복사 ===")
copied = []
for src_name, dst_name in mapping:
    src = src_dir / src_name
    dst = dst_dir / dst_name
    shutil.copy2(src, dst)
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    size = dst.stat().st_size
    copied.append({"dst_name": dst_name, "sha256": sha, "size": size})
    print(f"  [OK] {dst_name}  sha256={sha[:16]}...  {size:,} bytes")

print()
print("=== [STEP 2] reference_manifest 갱신 ===")
manifest_path = dst_dir / "reference_manifest_v4_identity_style_clean.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

# 기존 2개 유지 + 씬 레퍼런스 5개 추가
existing_paths = {a["path"] for a in manifest["artifacts"]}
for item in copied:
    rel_path = "out/references/" + item["dst_name"]
    if rel_path not in existing_paths:
        manifest["artifacts"].append({
            "role": "scene_style_example",
            "path": rel_path,
            "sha256": item["sha256"],
            "description": (
                "우리 채널 확립된 씬 스타일 예시. "
                "금화 캐릭터 의상·표정·배경 텍스트 사인보드 문법을 그대로 복제할 것."
            )
        })
        print(f"  [ADD] {rel_path}")
    else:
        print(f"  [SKIP] 이미 존재: {rel_path}")

manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print()
print(f"  manifest 업데이트 완료 -> artifacts 총 {len(manifest['artifacts'])}개")
print()
print("=== [STEP 3] 파일 존재 최종 검증 ===")
for item in copied:
    p = dst_dir / item["dst_name"]
    status = "OK" if p.is_file() else "MISSING"
    print(f"  [{status}] {p.name}  ({p.stat().st_size:,} bytes)")

print()
print("=== 완료 ===")

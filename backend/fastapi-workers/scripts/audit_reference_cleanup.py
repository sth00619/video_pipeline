#!/usr/bin/env python3
"""참조 25개를 읽기 전용 조사하고 별도 증거/보존 목록을 만든다. Git 필터는 실행하지 않는다."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path


PREFIX = "backend/fastapi-workers/out/references/"
TOOL_INPUTS = {
    "character_reference_v4_identity_clean.png",
    "style_reference_v4_medium_clean.png",
    "layout_reference_v2_textless.png",
}
REASONS = {
    "runtime_required": "기본 로더가 존재를 강제하는 활성 자산. 현재 문맥별 선택 여부와 무관하게 보존.",
    "superseded_face_reference": "v2 비교·롤백 근거인 이전 얼굴 참조. 운영 기본 입력은 아니지만 삭제하지 않음.",
    "tool_input": "별도 검증/검토 스크립트가 직접 읽음. 운영 기본 참조로 재활성화하지 않고 도구 의존성으로 보존.",
    "rebuild_input": "구형 참조 재생성기의 frames[0] 픽셀 입력. 원본 영상은 외부 Windows 경로여서 대체 가능성을 단정하지 않음.",
    "unused_rebuild_output": "재생성기가 출력/캐시 목록에 넣지만 이후 픽셀 소비가 없음. 백업 후 Git 이력 정리 후보.",
    "legacy_generated": "구형 빌더/등록기의 출력 또는 역사 매니페스트 항목. 현재 확인한 호출자가 Gemini에 전달하는 목록에는 없음.",
    "no_static_consumer": "조사 범위의 직접 파일 소비 경로 없음. 동적 경로 입력까지 미사용이라고 단정하지 않음.",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_names(provider: Path) -> set[str]:
    """모듈을 import/실행하지 않고 실제 로더 상수를 읽는다."""
    values = {}
    for node in ast.parse(provider.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"_SCENE_STYLE_REF_NAMES", "_FACE_RANGE_REF_NAME"}:
                    values[target.id] = ast.literal_eval(node.value)
    return {values["_FACE_RANGE_REF_NAME"], *values["_SCENE_STYLE_REF_NAMES"]}


def classify(name: str, active: set[str]) -> str:
    if name in active:
        return "runtime_required"
    if name == "channel_character_face_range_v1.png":
        return "superseded_face_reference"
    if name in TOOL_INPUTS:
        return "tool_input"
    if name == "source_05s.png":
        return "rebuild_input"
    if name in {"source_20s.png", "source_35s.png", "source_50s.png"}:
        return "unused_rebuild_output"
    if name.startswith("style_scene_ref_") or name in {"character_reference_v2_textless.png", "style_reference_v2_textless.png"}:
        return "legacy_generated"
    if name in {"character_reference.png", "style_reference.png", "layout_reference.png"}:
        return "no_static_consumer"
    raise ValueError(f"미분류 참조는 자동 정리 후보로 넣지 않습니다: {name}")


def audit(repo: Path, old_filter: Path) -> dict:
    worker = repo / "backend/fastapi-workers"
    provider = worker / "app/v5/providers/gemini_provider.py"
    active = runtime_names(provider)
    old_manifest = repo / "docs/evidence/history_cleanup_20260826/generated-files.sha256"
    old_hashes = dict((path, digest) for line in old_manifest.read_text().splitlines()
                      for digest, path in [line.split("  ", 1)])
    historical_paths = [p.removeprefix("literal:") for p in old_filter.read_text().splitlines()
                        if p.startswith("literal:" + PREFIX)]
    if len(historical_paths) != 25 or len(set(historical_paths)) != 25:
        raise ValueError("기존 필터의 참조 25개 집합이 바뀌었습니다. 분류를 재검토하세요.")
    paths = list(historical_paths)
    for name in sorted(active - {Path(p).name for p in historical_paths}):
        active_path = PREFIX + name
        if not (repo / active_path).is_file():
            raise ValueError(f"새 활성 참조 파일이 없습니다: {active_path}")
        paths.append(active_path)
    # 코드, 보조 스크립트, 테스트, 파일럿 입력, 참조 매니페스트만 읽는다.
    # .env, 인증 헤더, DB 비밀번호 또는 임의 서비스 응답은 수집하지 않는다.
    sources = sorted({p for sub in ("app", "scripts", "tests", "pilot-inputs", "out/references")
                      for p in (worker / sub).rglob("*")
                      if p.suffix in {".py", ".json"} and "__pycache__" not in p.parts
                      and p.name not in {"audit_reference_cleanup.py", "test_reference_cleanup_audit.py"}})
    lines = {p: p.read_text(encoding="utf-8").splitlines() for p in sources}
    rows = []
    for relative in paths:
        path = repo / relative
        category = classify(path.name, active)
        hits = [{"file": str(p.relative_to(repo)), "line": n}
                for p, content in lines.items() for n, line in enumerate(content, 1) if path.name in line]
        if path.name.startswith("source_"):
            # f-string 경로라 파일명 검색만으로는 검출할 수 없다.
            builder = worker / "scripts/build_v5_gemini_references.py"
            hits.extend({"file": str(builder.relative_to(repo)), "line": n, "kind": "dynamic_builder_path"}
                        for n, line in enumerate(lines[builder], 1)
                        if 'f"source_' in line or "frames[0]" in line)
        preserve = category in {"runtime_required", "superseded_face_reference", "tool_input", "rebuild_input"}
        actual_hash = sha256(path)
        rows.append({"path": relative, "sha256": actual_hash, "bytes": path.stat().st_size,
                     "backup_manifest_sha256": old_hashes.get(relative),
                     "matches_backup_manifest": actual_hash == old_hashes.get(relative),
                     "category": category, "preserve_in_git": preserve,
                     "action": "preserve" if preserve else "archive_candidate_pending_dynamic_path_check",
                     "reason": REASONS[category], "static_mentions_not_all_consumers": hits})
    return {
        "schema_version": 2, "scope": "역사 필터의 25개 참조와 현재 활성 추가 참조를 함께 조사, Git/자산 변경 없음",
        "filter_source": str(old_filter.relative_to(repo)), "filter_source_sha256": sha256(old_filter),
        "provider_source_sha256": sha256(provider), "counts": dict(Counter(r["category"] for r in rows)),
        "preserve_count": sum(r["preserve_in_git"] for r in rows),
        "scan_files": [{"path": str(p.relative_to(repo)), "sha256": sha256(p)} for p in sources],
        "limitations": [
            "정적 이름 검색 결과는 읽기/쓰기/매니페스트 항목을 모두 포함한다. 역할 분류는 해당 호출 코드와 대조했다.",
            "app/main.py character_image_path와 CLI 명시 경로는 동적이다. 운영 DB/진행 중 요청의 전체 참조를 조회하지 않았다.",
            "후보 13개는 삭제 승인이나 확정된 죽은 파일이 아니다. 백업 및 동적 참조 대조 후에만 이력 제거 가능.",
            "기존 filter-generated-binary-paths.txt는 위험한 역사 초안으로 그대로 보존했다. 실행하면 안 된다.",
        ],
        "assets": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    report = audit(repo, repo / "docs/evidence/history_cleanup_20260826/filter-generated-binary-paths.txt")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "reference-assets.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for filename, categories in (
        ("runtime-reference-whitelist.txt", {"runtime_required"}),
        ("reference-preserve-whitelist.txt", {"runtime_required", "superseded_face_reference", "tool_input", "rebuild_input"}),
    ):
        paths = [r["path"] for r in report["assets"] if r["category"] in categories]
        (args.output / filename).write_text("\n".join(paths) + "\n", encoding="utf-8")
    table = ["# 참조 자산 분류", "", "| 파일 | 분류 | Git 보존 |", "|---|---|---|"]
    table.extend(f"| `{Path(r['path']).name}` | {r['category']} | {'보존' if r['preserve_in_git'] else '조건부 정리 후보'} |" for r in report["assets"])
    table.extend(["", *[f"- {v}" for v in report["limitations"]]])
    (args.output / "reference-assets.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "preserve_count": report["preserve_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

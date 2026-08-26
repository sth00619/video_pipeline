"""생성 산출물 백업과 해시를 검증한다. 삭제·필터·푸시는 실행하지 않는다."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOTS = ("artifacts", "backend/artifacts", "backend/fastapi-workers/out", "data_jobs_175")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".mp3", ".wav", ".zip"}


def digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for root in ROOTS:
        for path in sorted((repo / root).rglob("*")):
            if path.is_file():
                with path.open("rb") as source:
                    files[path.relative_to(repo).as_posix()] = {
                        "sha256": digest(source), "bytes": path.stat().st_size,
                    }
    archive = args.backup_dir / "generated-artifacts.tar.gz"
    verified = set()
    with tarfile.open(archive, "r|gz") as source:
        for member in source:
            if not member.isfile():
                continue
            name = member.name.removeprefix("./")
            # macOS tar의 확장 속성 부가 파일은 원본 파일과 별도로 취급한다.
            if Path(name).name.startswith("._"):
                continue
            if name not in files:
                raise RuntimeError(f"백업에만 존재하는 파일: {name}")
            with source.extractfile(member) as data:
                actual = digest(data)
            if actual != files[name]["sha256"]:
                raise RuntimeError(f"백업 해시 불일치: {name}")
            verified.add(name)
    if verified != set(files):
        raise RuntimeError(f"백업 누락: {sorted(set(files) - verified)}")
    # 현재 트리뿐 아니라 모든 로컬 ref의 과거 생성 바이너리 경로까지 목록화한다.
    # rev-list --objects는 동일 blob의 여러 경로 중 하나만 출력하므로 중복 복사 경로를 놓친다.
    historical = subprocess.check_output(
        ["git", "log", "--all", "--format=", "--name-only", "--no-renames", "-z"], text=True,
    )
    remove_paths = set()
    for raw_path in historical.split("\0"):
        path = raw_path.strip("\n")
        if any(path.startswith(root + "/") for root in ROOTS):
            if Path(path).suffix.lower() in BINARY_SUFFIXES:
                remove_paths.add(path)
    with (args.output_dir / "generated-files.sha256").open("w") as output:
        for name, value in sorted(files.items()):
            output.write(f'{value["sha256"]}  {name}\n')
    with (args.output_dir / "filter-generated-binary-paths.txt").open("w") as output:
        for name in sorted(remove_paths):
            output.write(f"literal:{name}\n")
    backups = {}
    for path in (archive, args.backup_dir / "repository-before-filter.bundle"):
        with path.open("rb") as source:
            backups[path.name] = {"bytes": path.stat().st_size, "sha256": digest(source)}
    summary = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "backup_directory": str(args.backup_dir.resolve()),
        "roots": ROOTS,
        "file_count": len(files), "total_bytes": sum(v["bytes"] for v in files.values()),
        "archive_verified_files": len(verified), "backup_files": backups,
        "historical_binary_paths": len(remove_paths),
        "preserved": "대본·원장·JSON·MD·자막 등 텍스트와 런타임 assets/ 참조 이미지는 필터 대상이 아니다.",
        "remote_rewrite_executed": False,
    }
    (args.output_dir / "backup-verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

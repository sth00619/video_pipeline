"""기존 TTS 음성에서 문자 정렬 메타데이터를 복구한다.

직접 워커 호출처럼 HTTP 응답만 받고 저장하지 못한 작업에만 사용한다.
음성을 다시 합성하지 않고, 기존 MP3와 낭독 원문으로 문자 정렬을 수행한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from app.workers.tts_worker import TtsWorker


def _clean_script_from_diff(diff_path: Path) -> str:
    content = diff_path.read_text(encoding="utf-8")
    start_marker = "=== [2] CLEANED NARRATION SCRIPT ==="
    end_marker = "=== [3] PREPROCESSED FOR TTS ==="
    try:
        start = content.index(start_marker)
        end = content.index(end_marker)
    except ValueError as exc:
        raise RuntimeError("TTS 원문 추적 로그에 정제 대본 구간이 없습니다.") from exc
    return content[content.index("\n", start) + 1:end].strip()


def recover(job_id: int, jobs_root: Path) -> dict:
    job_dir = jobs_root / str(job_id)
    tts_dir = job_dir / "tts"
    audio_path = tts_dir / "full.mp3"
    if not audio_path.is_file():
        raise RuntimeError(f"TTS 음성 파일이 없습니다: {audio_path}")
    script = _clean_script_from_diff(tts_dir / "tts_text_diff.log")

    worker = TtsWorker()
    total_duration = worker._probe_duration(str(audio_path))
    if not total_duration or total_duration <= 0:
        raise RuntimeError("기존 TTS 음성의 재생 시간을 확인하지 못했습니다.")
    output_path = tts_dir / "tts_manifest.json"
    if output_path.is_file():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if (
            existing.get("canonical_sha256") == hashlib.sha256(script.encode("utf-8")).hexdigest()
            and isinstance(existing.get("chunks"), list)
            and existing["chunks"]
        ):
            existing["total_duration"] = round(total_duration, 3)
            output_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            return {
                "output_path": str(output_path),
                "canonical_sha256": existing["canonical_sha256"],
                "subtitle_cue_count": len(existing["chunks"]),
                "alignment_mode": "character_cached",
            }

    chunks = worker._extract_timestamps_with_forced_alignment(str(audio_path), script, 18)
    if worker._last_subtitle_alignment_mode != "character":
        raise RuntimeError("기존 음성의 문자 단위 정렬을 복구하지 못했습니다.")
    chunks = worker._snap_subtitle_timings_to_render_frames(chunks, 30.0, "nearest")
    if re.sub(r"\s+", "", script) != re.sub(r"\s+", "", "".join(item["text"] for item in chunks)):
        raise RuntimeError("복구한 자막 큐가 원문과 일치하지 않습니다.")

    quality_path = job_dir / "quality" / "tts.json"
    quality_report = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.is_file() else {}
    manifest = {
        "job_id": job_id,
        "audio_path": str(audio_path),
        "total_duration": round(total_duration, 3),
        "chunks": chunks,
        "canonical_text": script,
        "canonical_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        "quality_report": quality_report,
    }
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "output_path": str(output_path),
        "canonical_sha256": manifest["canonical_sha256"],
        "subtitle_cue_count": len(chunks),
        "alignment_mode": worker._last_subtitle_alignment_mode,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id", type=int)
    parser.add_argument("--jobs-root", default="/app/data/jobs")
    args = parser.parse_args()
    print(json.dumps(recover(args.job_id, Path(args.jobs_root)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

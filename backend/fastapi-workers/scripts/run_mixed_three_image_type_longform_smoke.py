#!/usr/bin/env python3
"""세 이미지 유형을 실제 롱폼 조립 API로 함께 검증한다.

이 스모크 테스트는 외부 이미지·TTS·모션 API를 호출하지 않는다. 이미 승인된
정보형/일반형 PNG와 사람이 좌표를 검증한 기사 캡처를 입력으로 사용해,
FastAPI의 실제 ``/workers/longform/generate`` 엔드포인트가 다음을 한 요청에서
처리하는지만 검증한다.

* V5 정보형: Pillow로 완성된 PNG를 정지 장면으로 유지
* 일반형: 기존 일반 이미지 장면을 정지 장면으로 조립
* 기사 캡처형: 원본 캡처와 검증 좌표로 강조 프레임을 결정론적으로 생성

생성된 MP4는 테스트용 job_id 아래에만 기록된다. 실비 API 호출은 없다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path


DATA_ROOT = Path("/app/data")


def _copy(source: Path, destination: Path) -> Path:
    if not source.is_file() or source.stat().st_size < 100:
        raise ValueError(f"유효한 입력 파일이 아닙니다: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_silent_wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 44_100
    frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=240) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="세 이미지 유형 혼합 롱폼 스모크 테스트")
    parser.add_argument("--job-id", type=int, default=990801)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--info-image", type=Path, required=True)
    parser.add_argument("--general-image", type=Path, required=True)
    parser.add_argument("--article-image", type=Path, required=True)
    parser.add_argument("--article-capture-json", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    job_root = DATA_ROOT / "jobs" / str(args.job_id)
    info_path = _copy(args.info_image, job_root / "images" / "scene_000_info.png")
    general_path = _copy(args.general_image, job_root / "images" / "scene_001_general.png")
    article_path = _copy(args.article_image, job_root / "evidence" / "article_source.png")
    audio_path = job_root / "tts" / "smoke_silence.wav"
    _write_silent_wav(audio_path, seconds=6.0)

    capture = json.loads(args.article_capture_json.read_text(encoding="utf-8-sig"))
    capture["local_path"] = str(article_path)
    capture["annotation_preview_path"] = ""
    capture["captured_at"] = capture.get("captured_at") or datetime.now(timezone.utc).isoformat()
    capture["image_sha256"] = _sha256(article_path)

    scenes = [
        {
            "index": 0,
            "scene_id": "smoke_information",
            "scene_type": "graph",
            "archetype": "data_lab",
            "content": "검증된 수치가 포함된 정보형 장면입니다.",
            "image_path": str(info_path),
            "use_kling": False,
            "v5_render_contract": {"smoke": True},
            "v5_verified_overlays": [{"label": "검증값", "value": "사전합성완료"}],
        },
        {
            "index": 1,
            "scene_id": "smoke_general",
            "scene_type": "general",
            "archetype": "port_emergency",
            "content": "서사를 설명하는 일반 카툰 장면입니다.",
            "image_path": str(general_path),
            "use_kling": False,
        },
        {
            "index": 2,
            "scene_id": "smoke_article_evidence",
            "scene_type": "text",
            "visual_kind": "article_scene",
            "visual_type": "article_evidence",
            "content": "기사 원문에서 사람이 검증한 문장과 숫자를 강조합니다.",
            "article_capture": capture,
            "emphasis_plan": {"body": "highlight_underline"},
            "key_phrase": str(capture.get("key_phrase") or ""),
            "source_credit": f"출처: {capture.get('publisher', '')} · {capture.get('published_at', '')}",
            "use_kling": False,
        },
    ]
    tts_meta = {
        "audio_path": str(audio_path),
        "total_duration": 6.0,
        "chunks": [
            {"text": scene["content"], "start": index * 2.0, "end": (index + 1) * 2.0, "duration": 2.0}
            for index, scene in enumerate(scenes)
        ],
    }
    result = _post_json(
        f"{args.api_base.rstrip('/')}/workers/longform/generate",
        {
            "job_id": args.job_id,
            "tts_meta": json.dumps(tts_meta, ensure_ascii=False),
            "scenes_meta": json.dumps(scenes, ensure_ascii=False),
            "gifs_meta": "[]",
        },
    )
    # LongformWorker의 공개 응답 계약은 ``video_path``다. ``output_path``는
    # 내부 결과 캐시/과거 도구에서 쓰인 명칭이므로 여기서는 허용하지 않는다.
    final_video = Path(str(result.get("video_path") or ""))
    emphasized_article = job_root / "longform" / "temp" / "deterministic_scene_002.png"
    plain_article = job_root / "longform" / "temp" / "deterministic_scene_002_plain.png"
    checks = {
        "final_video_exists": final_video.is_file() and final_video.stat().st_size > 1_000,
        "information_input_exists": info_path.is_file(),
        "general_input_exists": general_path.is_file(),
        "article_plain_frame_exists": plain_article.is_file() and plain_article.stat().st_size > 1_000,
        "article_emphasized_frame_exists": emphasized_article.is_file() and emphasized_article.stat().st_size > 1_000,
        "motion_disabled_for_all_three": all(scene["use_kling"] is False for scene in scenes),
    }
    if not all(checks.values()):
        raise RuntimeError(f"혼합 롱폼 스모크 테스트 실패: {checks}")
    report = {
        "status": "passed",
        "job_id": args.job_id,
        "cost_policy": "이미 생성된 PNG, 로컬 WAV, FFmpeg만 사용 — 외부 API 호출 없음",
        "scenes": [
            {"scene_id": scene["scene_id"], "kind": scene.get("visual_kind", "generated_image"), "image_path": scene.get("image_path")}
            for scene in scenes
        ],
        "checks": checks,
        "result": result,
        "final_video": str(final_video),
        "article_plain_frame": str(plain_article),
        "article_emphasized_frame": str(emphasized_article),
    }
    report_path = args.report or job_root / "longform" / "mixed_three_image_type_smoke_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

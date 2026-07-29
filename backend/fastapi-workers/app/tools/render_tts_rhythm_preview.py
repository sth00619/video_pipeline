"""검토용 대본을 ElevenLabs 음성과 정밀 자막으로 미리 렌더링한다.

이 도구는 장면 이미지 품질을 평가하는 용도가 아니라, 문장 역할 전환·TTS 호흡·
자막 의미 단위를 함께 확인하는 용도다. API 키는 환경 변수에서만 읽는다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from dotenv import load_dotenv

# 로컬 검토 실행에서도 컨테이너와 같은 환경 변수를 사용한다. 키 값은
# 코드·결과물·로그에 포함하지 않는다.
repo_env = Path(__file__).resolve().parents[3] / ".env"
if repo_env.exists():
    load_dotenv(repo_env)

from app import runtime_config
from app.workers.longform_worker import LongformWorker
from app.workers.tts_worker import TtsWorker


def render_preview(script_path: Path, output_prefix: Path) -> dict:
    script = script_path.read_text(encoding="utf-8").strip()
    if not script:
        raise ValueError("검토용 대본이 비어 있습니다.")

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    audio_path = output_prefix.with_suffix(".mp3")
    ass_path = output_prefix.with_suffix(".ass")
    video_path = output_prefix.with_suffix(".mp4")

    tts = TtsWorker()
    success, character_timings = tts._generate_elevenlabs(
        script,
        str(audio_path),
        voice_id=str(runtime_config.value("elevenlabs_voice_id") or ""),
        job_id=728,
        tts_speed=float(runtime_config.value("tts_speed")),
        seed=728,
        thought_group_delivery=True,
    )
    if not success or not character_timings:
        raise RuntimeError("ElevenLabs 음성 또는 문자 단위 정렬을 생성하지 못했습니다.")

    source_cues = tts._split_script_into_chunks(
        script,
        max_chars=int(runtime_config.value("subtitle_max_chars")),
    )
    cues = tts._map_timestamps_by_character_alignment(source_cues, character_timings)
    cues = tts._snap_subtitle_timings_to_render_frames(cues, frame_rate=30.0)
    if not cues:
        raise RuntimeError("문자 단위 정렬로 자막 큐를 만들지 못했습니다.")

    LongformWorker()._generate_ass(cues, str(ass_path))
    # Windows 절대 경로의 드라이브 콜론은 FFmpeg 필터 옵션 구분자로 해석된다.
    # 호출자의 작업 디렉터리를 기준으로 한 상대 경로를 유지하면 이스케이프
    # 차이 없이 ass 필터가 같은 파일을 안정적으로 연다.
    ass_filter_path = ass_path.as_posix()
    command = [
        "ffmpeg", "-f", "lavfi", "-i", "color=c=0x101828:s=1920x1080:r=30",
        "-i", str(audio_path), "-vf", f"ass={ass_filter_path}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        "-y", str(video_path), "-loglevel", "error",
    ]
    subprocess.run(command, check=True)

    result = {
        "script": str(script_path),
        "audio": str(audio_path),
        "subtitles": str(ass_path),
        "video": str(video_path),
        "cue_count": len(cues),
        "cues": cues,
        "frame_rate": 30,
        "alignment": "elevenlabs_character_timestamps",
    }
    output_prefix.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TTS 리듬 검토 영상 렌더러")
    parser.add_argument("script", type=Path)
    parser.add_argument("output_prefix", type=Path)
    args = parser.parse_args()
    print(json.dumps(render_preview(args.script, args.output_prefix), ensure_ascii=False, indent=2))

#!/usr/bin/env python3
"""사람 녹음 MP4/오디오를 화면 원문 자막과 문자 단위로 정렬한다."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent.parent / ".env")

from app.tts.forced_alignment_srt import AlignmentError, SubtitleCue, align_audio_to_text_with_characters, cues_to_srt
from app.tts.splice_artifact_detector import analyze_audio
from app.workers.tts_worker import TtsWorker


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def extract_alignment_audio(media_path: Path, temp_dir: Path) -> Path:
    """MP4/WAV 등 입력을 Forced Alignment용 모노 MP3로 안전하게 변환한다."""
    if media_path.suffix.lower() == ".mp3":
        return media_path
    audio_path = temp_dir / "alignment_audio.mp3"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y", "-i", str(media_path), "-vn", "-ar", "44100",
        "-ac", "1", "-c:a", "libmp3lame", "-b:a", "192k", str(audio_path),
    ], check=True)
    return audio_path


def burn_subtitles(video: Path, srt: Path, output: Path) -> None:
    """원본 영상의 음성은 그대로 두고 자막만 번인한다."""
    style = (
        "FontName=Malgun Gothic,FontSize=30,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00122538,BorderStyle=1,Outline=2,Shadow=0,"
        "Alignment=2,MarginV=80"
    )
    srt_filter_path = str(srt.resolve()).replace("\\", "/").replace(":", r"\:")
    subtitle_filter = f"subtitles=filename='{srt_filter_path}':force_style='{style}'"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y", "-i", str(video), "-vf", subtitle_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", str(output),
    ], check=True)


def detect_video_frame_rate(media_path: Path) -> float:
    """입력 MP4의 평균 프레임레이트를 읽어 자막 시간을 같은 격자에 맞춘다."""
    if media_path.suffix.lower() not in VIDEO_EXTENSIONS:
        return 30.0
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ], check=True, capture_output=True, text=True)
    raw_rate = probe.stdout.strip()
    try:
        numerator, denominator = raw_rate.split("/", maxsplit=1)
        rate = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return 30.0
    return rate if rate > 0 else 30.0


def main() -> None:
    parser = argparse.ArgumentParser(description="사람 녹음 MP4/오디오에 원문 자막을 정밀 정렬합니다.")
    parser.add_argument("--media", required=True, help="사람 녹음 MP4, MP3 또는 WAV")
    parser.add_argument("--script", required=True, help="화면에 표시할 원문 대본 UTF-8 TXT")
    parser.add_argument("--out", required=True, help="출력 SRT 경로")
    parser.add_argument("--burned", help="선택: 자막을 번인한 최종 MP4 경로")
    parser.add_argument("--burn-source", help="선택: 번인할 무자막 영상. 생략 시 --media MP4를 사용")
    parser.add_argument("--report", help="선택: 정렬·접합부 QA JSON 경로")
    parser.add_argument("--fps", type=float, help="선택: 자막을 맞출 영상 프레임레이트(기본: 입력 MP4에서 감지)")
    parser.add_argument("--start-frame-policy", choices=("nearest", "ceil"), default="nearest", help="선택: 자막 시작 프레임 보정 방식")
    parser.add_argument(
        "--allow-word-fallback", action="store_true",
        help="문자 정렬 실패 시에만 단어 정렬 결과를 허용합니다. 기본값은 실패 처리입니다.",
    )
    args = parser.parse_args()

    media_path = Path(args.media).resolve()
    script_path = Path(args.script).resolve()
    output_srt = Path(args.out).resolve()
    if not media_path.is_file() or not script_path.is_file():
        raise FileNotFoundError("녹음 파일과 원문 대본 경로를 확인하세요.")

    display_script = script_path.read_text(encoding="utf-8").strip()
    worker = TtsWorker()
    # 녹음자는 prepare_human_recording_guide.py가 만든 낭독용 대본을 그대로 읽는다.
    spoken_script = worker._soften_korean_delivery_cadence(worker._preprocess_for_tts(display_script))

    with tempfile.TemporaryDirectory(prefix="human-alignment-") as temp_name:
        alignment_audio = extract_alignment_audio(media_path, Path(temp_name))
        try:
            words, characters = align_audio_to_text_with_characters(str(alignment_audio), spoken_script)
        except AlignmentError as exc:
            raise RuntimeError(f"강제 정렬에 실패했습니다: {exc}") from exc

        display_chunks = worker._split_script_into_chunks(display_script, max_chars=18)
        chunks = worker._map_display_chunks_to_spoken_characters(display_chunks, characters)
        alignment_mode = "character"
        if not chunks:
            if not args.allow_word_fallback:
                raise RuntimeError(
                    "문자 단위 정렬을 확보하지 못했습니다. 낭독용 대본과 실제 발화가 같은지 확인한 뒤 재녹음하세요."
                )
            chunks = worker._map_display_chunks_to_spoken_words(display_chunks, words)
            alignment_mode = "word_fallback"
        if not chunks:
            raise RuntimeError("원문 자막 타임라인을 만들 수 없습니다. 낭독 대본 준수 여부를 확인하세요.")

        frame_rate = args.fps or detect_video_frame_rate(media_path)
        chunks = worker._snap_subtitle_timings_to_render_frames(chunks, frame_rate, args.start_frame_policy)

        output_srt.parent.mkdir(parents=True, exist_ok=True)
        cues = [SubtitleCue(item["index"], item["start"], item["end"], item["text"]) for item in chunks]
        output_srt.write_text(cues_to_srt(cues), encoding="utf-8")
        splice_report = analyze_audio(alignment_audio)

    result = {
        "alignment_mode": alignment_mode,
        "cue_count": len(chunks),
        "first_start_seconds": chunks[0]["start"],
        "last_end_seconds": chunks[-1]["end"],
        "splice_artifacts": splice_report,
        "source_media": str(media_path),
        "subtitle_path": str(output_srt),
        "subtitle_frame_rate": frame_rate,
        "subtitle_start_frame_policy": args.start_frame_policy,
    }
    if args.burned:
        burn_source = Path(args.burn_source).resolve() if args.burn_source else media_path
        if burn_source.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError("--burned에는 --burn-source MP4를 지정하거나 --media로 MP4를 제공해야 합니다.")
        burned_path = Path(args.burned).resolve()
        burned_path.parent.mkdir(parents=True, exist_ok=True)
        burn_subtitles(burn_source, output_srt, burned_path)
        result["burned_video"] = str(burned_path)
    if args.report:
        report_path = Path(args.report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

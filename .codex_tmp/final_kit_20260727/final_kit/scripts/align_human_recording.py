#!/usr/bin/env python3
"""
align_human_recording.py — 사람이 녹음한 음성에 자막을 자동으로 완벽 정렬.

사용자 요구: "목소리 좋으신 분이 직접 녹음파일을 만들어서 보내주실 수 있다"
→ 사람 음성 mp3 + 스크립트 txt 를 넣으면, 실제 발화에 맞춘 .srt 를 뽑는다.
   이게 "AI 목소리 어색함" + "싱크" 두 문제를 한 번에 해결하는 가장 확실한 길.

싱크가 완벽한 이유: 스크립트 길이로 추정하지 않고, ElevenLabs Forced Alignment가
실제 오디오 파형을 분석해 각 단어가 언제 발음됐는지 측정하기 때문.

실행:
  export ELEVENLABS_API_KEY=xxx
  python scripts/align_human_recording.py \
      --audio narration.mp3 --script script.txt --out subtitles.srt \
      [--burn video.mp4 --burned out.mp4]

--burn 을 주면 FFmpeg로 자막을 영상에 구워서 최종본까지 만든다.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend_fastapi.tts.forced_alignment_srt import (
    align_audio_to_text, words_to_cues, cues_to_srt, AlignmentError,
)


def burn_subtitles(video: str, srt: str, out: str) -> None:
    """FFmpeg로 자막 번인. 한글 폰트 지정 필수."""
    # 재인코딩 최소화: 자막 필터만 적용. 화질 손실 억제 위해 crf 18.
    style = "FontName=NanumGothic,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=40"
    cmd = [
        "ffmpeg", "-y", "-i", video,
        "-vf", f"subtitles={srt}:force_style='{style}'",
        "-c:a", "copy", "-crf", "18", out,
    ]
    print("[burn] " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="사람 녹음 mp3/wav")
    ap.add_argument("--script", required=True, help="스크립트 txt (실제 낭독 텍스트)")
    ap.add_argument("--out", required=True, help="출력 srt 경로")
    ap.add_argument("--max-chars", type=int, default=20)
    ap.add_argument("--gap-split", type=float, default=0.5)
    ap.add_argument("--burn", help="(선택) 자막 구울 영상 mp4")
    ap.add_argument("--burned", help="(선택) 번인 출력 mp4")
    args = ap.parse_args()

    transcript = Path(args.script).read_text(encoding="utf-8").strip()
    # 자막 표시용 원본 유지. 정렬 입력도 원본 텍스트 그대로 (사람이 실제 읽은 대로).

    print(f"[1] Forced Alignment 요청: {args.audio}")
    try:
        words = align_audio_to_text(args.audio, transcript)
    except AlignmentError as e:
        print(f"✗ 정렬 실패: {e}")
        sys.exit(1)
    print(f"[2] 단어 {len(words)}개 타임스탬프 수신")

    cues = words_to_cues(words, max_chars=args.max_chars, gap_split=args.gap_split)
    srt = cues_to_srt(cues)
    Path(args.out).write_text(srt, encoding="utf-8")
    print(f"[3] 자막 {len(cues)}개 큐 → {args.out}")
    print(f"    첫 큐: {cues[0].start:.2f}s '{cues[0].text}'")
    print(f"    끝 큐: {cues[-1].end:.2f}s '{cues[-1].text}'")

    if args.burn and args.burned:
        print(f"[4] 자막 번인 → {args.burned}")
        burn_subtitles(args.burn, args.out, args.burned)
        print(f"✅ 완료: {args.burned}")
    else:
        print("✅ SRT 완료. --burn/--burned 주면 영상에 굽습니다.")


if __name__ == "__main__":
    main()

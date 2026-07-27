"""
sync_verifier.py — 자막-오디오 싱크 검증 및 문장 경계 드리프트 진단.

【사용자 피드백 정확히 대응】
"한 문장 단위에서 다음으로 넘어갈 때 앞뒤 싱크가 부분적으로 안 맞는 문제"

이 증상의 전형적 원인 3가지 (테스트 영상 실측으로 1번 확정):
  1. 자막 타임스탬프를 스크립트 글자수로 추정 → 한국어 숫자 확장에서 누적 오차
     ("112만 5천" 4글자가 "백십이만 오천 원" 7음절로 발음되며 뒤 문장이 밀림)
  2. 문장 분리가 소수점을 경계로 오인 ("16.5%" → "16" / "5%" 로 잘림)
  3. 문장 사이 무음(쉼)을 자막이 반영 못함 → 다음 문장 자막이 일찍 뜸

【해결】
forced_alignment_srt.py가 실제 오디오에 정렬하므로 1·3은 근본 해결.
이 파일은 (a) 기존/신규 SRT가 실제 오디오와 맞는지 검증하고,
        (b) 문장 경계마다 얼마나 어긋나는지 리포트하고,
        (c) 단순 오프셋/드리프트면 자동 보정한다.

의존성: (검증) 없음 / (오디오 파형 대조) ffmpeg
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass
class SrtCue:
    index: int
    start: float
    end: float
    text: str


def parse_srt(srt_text: str) -> list[SrtCue]:
    cues = []
    blocks = re.split(r"\n\s*\n", srt_text.strip())
    for b in blocks:
        lines = b.strip().split("\n")
        if len(lines) < 2:
            continue
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[1])
        if not m:
            continue
        g = list(map(int, m.groups()))
        start = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000
        end = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000
        text = " ".join(lines[2:]) if len(lines) > 2 else ""
        idx = int(lines[0]) if lines[0].isdigit() else len(cues)+1
        cues.append(SrtCue(idx, start, end, text))
    return cues


# ---------------------------------------------------------------------------
# 오디오 발화 구간 검출 (ffmpeg silencedetect)
# ---------------------------------------------------------------------------
def detect_speech_segments(audio_path: str, *, noise_db: int = -30,
                           min_silence: float = 0.3) -> list[tuple[float, float]]:
    """발화 구간 [(start, end), ...] 반환. 무음으로 나뉜 덩어리."""
    cmd = ["ffmpeg", "-i", audio_path, "-af",
           f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    log = r.stderr
    silence_starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", log)]
    silence_ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", log)]
    dur = _duration(audio_path)

    # 무음 구간을 뒤집어 발화 구간으로
    segments = []
    cursor = 0.0
    for ss, se in zip(silence_starts, silence_ends):
        if ss > cursor:
            segments.append((cursor, ss))
        cursor = se
    if cursor < dur:
        segments.append((cursor, dur))
    return segments


def _duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# 문장 경계 드리프트 리포트
# ---------------------------------------------------------------------------
@dataclass
class DriftReport:
    cue_index: int
    cue_start: float
    nearest_speech_start: float
    offset: float           # + 면 자막이 늦음, - 면 자막이 이름
    text_preview: str


def analyze_boundary_drift(cues: list[SrtCue],
                           speech_segments: list[tuple[float, float]],
                           *, threshold: float = 0.25) -> list[DriftReport]:
    """각 자막 시작이 가장 가까운 발화 시작과 얼마나 어긋나는지."""
    starts = [s[0] for s in speech_segments]
    reports = []
    for c in cues:
        nearest = min(starts, key=lambda s: abs(s - c.start)) if starts else c.start
        offset = c.start - nearest
        if abs(offset) >= threshold:
            reports.append(DriftReport(
                cue_index=c.index, cue_start=round(c.start, 2),
                nearest_speech_start=round(nearest, 2), offset=round(offset, 2),
                text_preview=c.text[:25],
            ))
    return reports


def classify_drift(reports: list[DriftReport], total_cues: int) -> str:
    """드리프트 유형 판정: 고정오프셋 / 점진드리프트 / 산발 / 정상."""
    if not reports:
        return "OK: 문장 경계 싱크 양호 (임계 이내)"
    offsets = [r.offset for r in reports]
    ratio = len(reports) / max(1, total_cues)

    import statistics
    mean_off = statistics.mean(offsets)
    stdev = statistics.pstdev(offsets) if len(offsets) > 1 else 0

    if ratio > 0.5 and stdev < 0.15:
        return (f"고정 오프셋: 전체가 평균 {mean_off:+.2f}s 어긋남. "
                f"→ 모든 타임스탬프를 {-mean_off:+.2f}s 시프트하면 해결.")
    # 점진 드리프트: 뒤로 갈수록 오프셋 커짐
    if len(reports) >= 3:
        first_half = statistics.mean(r.offset for r in reports[:len(reports)//2])
        second_half = statistics.mean(r.offset for r in reports[len(reports)//2:])
        if abs(second_half) > abs(first_half) + 0.2:
            return ("점진 드리프트: 뒤로 갈수록 어긋남 심해짐. "
                    "→ 글자수 비례 추정이 원인. forced_alignment로 재생성 필요.")
    return (f"산발 드리프트: {len(reports)}개 문장 경계가 개별적으로 어긋남 "
            f"(주로 숫자·긴 문장 뒤). → forced_alignment로 재생성 권장.")


def shift_cues(cues: list[SrtCue], offset: float) -> list[SrtCue]:
    """고정 오프셋 보정."""
    return [SrtCue(c.index, max(0, c.start + offset), max(0, c.end + offset), c.text)
            for c in cues]


def cues_to_srt(cues: list[SrtCue]) -> str:
    def ts(t):
        h, m = int(t//3600), int((t%3600)//60)
        s, ms = int(t%60), int(round((t-int(t))*1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    out = []
    for c in cues:
        out += [str(c.index), f"{ts(c.start)} --> {ts(c.end)}", c.text, ""]
    return "\n".join(out)


if __name__ == "__main__":
    # 데모: 가상 SRT로 드리프트 분류 로직 검증
    demo_srt = """1
00:00:00,000 --> 00:00:03,000
첫 문장입니다

2
00:00:03,500 --> 00:00:06,000
숫자 112만 5천원이 나오는 문장

3
00:00:07,200 --> 00:00:09,000
그 다음 문장"""
    cues = parse_srt(demo_srt)
    # 가상 발화 구간 (자막보다 조금씩 늦게 시작 = 자막이 이름)
    speech = [(0.3, 3.2), (4.1, 6.3), (7.5, 9.2)]
    reports = analyze_boundary_drift(cues, speech, threshold=0.25)
    print(f"드리프트 {len(reports)}건 발견:")
    for r in reports:
        print(f"  큐{r.cue_index}: 자막 {r.cue_start}s vs 발화 {r.nearest_speech_start}s "
              f"= {r.offset:+.2f}s '{r.text_preview}'")
    print("\n판정:", classify_drift(reports, len(cues)))

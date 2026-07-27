"""TTS 조각 결합에서 생기는 디지털 무음 접합부를 검사한다.

사람의 자연스러운 쉼은 낮은 레벨의 호흡·잔향이 남는 경우가 많다. 반면 여러
음성 조각을 단순히 이어 붙일 때 생기는 완전한 0 신호와 급격한 경계는 별도의
검사가 필요하다. 이 모듈은 최종 오디오를 16-bit 모노 WAV로 분석하며, 결과는
경고용 QA 정보일 뿐 자막-음성 동기 판단을 대신하지 않는다.
"""
from __future__ import annotations

import re
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_EDGE_SHARPNESS = 500.0


@dataclass(frozen=True)
class SpliceCandidate:
    """무음 구간 하나의 파형 기반 판정 결과."""

    start: float
    end: float
    duration: float
    is_flat_zero: bool
    edge_sharpness: float
    verdict: str

    @property
    def is_suspect(self) -> bool:
        return self.verdict.startswith("접합부 의심")


def _run(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffmpeg 실행 실패")
    return completed.stderr


def detect_silence(
    audio_path: str | Path,
    *,
    noise_db: int = -40,
    min_silence: float = 0.1,
) -> list[tuple[float, float]]:
    """짧은 무음도 후보로 잡되, 뒤 단계에서 디지털 0 신호인지 재검사한다."""

    log = _run([
        "ffmpeg", "-hide_banner", "-i", str(audio_path), "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-",
    ])
    starts = [float(value) for value in re.findall(r"silence_start:\s*([\d.]+)", log)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*([\d.]+)", log)]
    return list(zip(starts, ends))


def _read_wav_samples(path: str | Path, start: float, end: float) -> list[int]:
    """16-bit PCM WAV의 지정 구간을 모노 기준 샘플로 읽는다."""

    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError("16-bit PCM WAV만 분석할 수 있습니다.")
        rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        start_frame = max(0, int(start * rate))
        end_frame = max(start_frame, int(end * rate))
        wav_file.setpos(min(start_frame, wav_file.getnframes()))
        raw = wav_file.readframes(max(0, end_frame - start_frame))
    sample_count = len(raw) // 2
    if not sample_count:
        return []
    samples = struct.unpack(f"<{sample_count}h", raw[:sample_count * 2])
    return list(samples[::max(1, channels)])


def analyze_silence_quality(
    audio_path: str | Path,
    start: float,
    end: float,
    *,
    pad: float = 0.05,
    edge_threshold: float = DEFAULT_EDGE_SHARPNESS,
) -> SpliceCandidate:
    """무음의 0 신호 여부와 양쪽 경계의 급격함을 함께 측정한다."""

    samples = _read_wav_samples(audio_path, start, end)
    silent_amplitude = max((abs(sample) for sample in samples), default=0)
    is_flat_zero = bool(samples) and silent_amplitude <= 2
    before = _read_wav_samples(audio_path, max(0.0, start - pad), start)
    after = _read_wav_samples(audio_path, end, end + pad)
    edge_sharpness = max(
        max((abs(sample) for sample in before), default=0),
        max((abs(sample) for sample in after), default=0),
    ) - silent_amplitude

    if is_flat_zero and edge_sharpness > edge_threshold:
        verdict = "접합부 의심: 완전 디지털 무음과 급격한 경계가 함께 감지되었습니다."
    elif is_flat_zero:
        verdict = "완전 무음이지만 경계가 완만합니다. 원본의 긴 쉼일 수 있습니다."
    else:
        verdict = "자연스러운 저음량 구간입니다."

    return SpliceCandidate(
        start=round(start, 3),
        end=round(end, 3),
        duration=round(end - start, 3),
        is_flat_zero=is_flat_zero,
        edge_sharpness=round(edge_sharpness, 1),
        verdict=verdict,
    )


def full_report(
    wav_path: str | Path,
    *,
    noise_db: int = -40,
    min_silence: float = 0.1,
    edge_threshold: float = DEFAULT_EDGE_SHARPNESS,
) -> list[SpliceCandidate]:
    """16-bit 모노 WAV 전체의 접합 후보를 반환한다."""

    silences = detect_silence(wav_path, noise_db=noise_db, min_silence=min_silence)
    return [
        analyze_silence_quality(wav_path, start, end, edge_threshold=edge_threshold)
        for start, end in silences
    ]


def analyze_audio(
    audio_path: str | Path,
    *,
    work_dir: str | Path | None = None,
    noise_db: int = -40,
    min_silence: float = 0.1,
    edge_threshold: float = DEFAULT_EDGE_SHARPNESS,
) -> dict[str, Any]:
    """MP3 등 최종 오디오를 변환 후 분석해 직렬화 가능한 QA 보고서를 만든다."""

    source = Path(audio_path)
    if not source.is_file():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {source}")
    target_dir = Path(work_dir) if work_dir else None
    if target_dir:
        target_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="splice-qa-", dir=str(target_dir) if target_dir else None)
    wav_path = Path(temp_dir) / "analysis.wav"
    try:
        _run([
            "ffmpeg", "-hide_banner", "-y", "-i", str(source), "-vn", "-ar", "44100",
            "-ac", "1", "-c:a", "pcm_s16le", str(wav_path),
        ])
        candidates = full_report(
            wav_path,
            noise_db=noise_db,
            min_silence=min_silence,
            edge_threshold=edge_threshold,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    suspect_count = sum(candidate.is_suspect for candidate in candidates)
    return {
        "passed": suspect_count == 0,
        "candidate_count": len(candidates),
        "suspect_count": suspect_count,
        "noise_db": noise_db,
        "min_silence_seconds": min_silence,
        "edge_sharpness_threshold": edge_threshold,
        "candidates": [asdict(candidate) for candidate in candidates],
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("사용법: python splice_artifact_detector.py <16bit_mono_wav_path>")
        raise SystemExit(1)
    for candidate in full_report(sys.argv[1]):
        flag = "RED" if candidate.is_suspect else ("YELLOW" if candidate.is_flat_zero else "GREEN")
        print(
            f"[{flag}] {candidate.start:.3f}s~{candidate.end:.3f}s "
            f"flat_zero={candidate.is_flat_zero} edge={candidate.edge_sharpness:.1f}\n"
            f"  {candidate.verdict}"
        )

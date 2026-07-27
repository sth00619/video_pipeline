import struct
import tempfile
import wave
from pathlib import Path

from app.tts.splice_artifact_detector import analyze_silence_quality


def _write_digital_splice(path: Path) -> None:
    """발화 조각 사이에 0.12초의 완전 디지털 무음을 넣은 WAV를 만든다."""
    sample_rate = 10_000
    samples = ([1_500] * sample_rate) + ([0] * 1_200) + ([1_500] * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def test_digital_zero_gap_with_sharp_edges_is_reported_as_a_splice():
    with tempfile.TemporaryDirectory() as directory:
        audio_path = Path(directory) / "intentional_splice.wav"
        _write_digital_splice(audio_path)

        candidate = analyze_silence_quality(audio_path, 1.0, 1.12)

    assert candidate.is_flat_zero is True
    assert candidate.edge_sharpness > 500
    assert candidate.is_suspect is True

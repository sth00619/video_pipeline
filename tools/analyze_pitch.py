import glob
import subprocess

import numpy as np


for path in (
    glob.glob("artifacts/deep_low_preview_*.mp3")
    + glob.glob("artifacts/extra_low_preview_*.mp3")
    + glob.glob("artifacts/natural_low_preview_*.mp3")
):
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
    )
    signal = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    values = []
    for start in range(0, len(signal) - 2048, 512):
        frame = signal[start : start + 2048] * np.hanning(2048)
        if np.sqrt(np.mean(frame * frame)) < 0.01:
            continue
        autocorrelation = np.correlate(frame, frame, mode="full")[2047:]
        low_lag, high_lag = int(16000 / 300), int(16000 / 70)
        lag = low_lag + int(np.argmax(autocorrelation[low_lag:high_lag]))
        if lag:
            values.append(16000 / lag)
    print(
        path,
        "median_f0",
        round(float(np.median(values)), 1),
        "p25",
        round(float(np.percentile(values, 25)), 1),
        "p75",
        round(float(np.percentile(values, 75)), 1),
        "frames",
        len(values),
    )

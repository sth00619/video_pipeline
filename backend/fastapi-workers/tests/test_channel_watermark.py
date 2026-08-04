"""우상단 채널 워터마크가 실제 영상 파일에 결정론적으로 합성되는지 검증한다."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.services.overlay.watermark import render_channel_watermark_layer, watermark_region
from app.workers.longform_worker import _apply_channel_watermark, _verify_video


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _make_solid_video(path: Path, *, with_audio: bool) -> None:
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:d=1:r=24"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=1", "-shortest", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, capture_output=True, check=True)


def test_watermark_layer_stays_inside_the_existing_protected_region():
    from app.services.overlay.editorial_overlay import _WATERMARK

    region = watermark_region((1920, 1080))
    protected_x = _WATERMARK["x"] * 1920
    protected_y = _WATERMARK["y"] * 1080
    protected_right = protected_x + _WATERMARK["width"] * 1920
    protected_bottom = protected_y + _WATERMARK["height"] * 1080

    assert region["x"] >= protected_x
    assert region["y"] >= protected_y
    assert region["x"] + region["width"] <= protected_right
    assert region["y"] + region["height"] <= protected_bottom


def test_watermark_layer_only_draws_pixels_in_the_top_right_corner():
    layer = render_channel_watermark_layer((1920, 1080))
    alpha = layer.split()[-1]
    # 좌하단은 완전히 투명해야 한다(캐릭터/자막 영역을 침범하지 않음).
    assert alpha.getpixel((10, 1070)) == 0
    region = watermark_region((1920, 1080))
    cx, cy = region["x"] + region["width"] // 2, region["y"] + region["height"] // 2
    assert alpha.getpixel((cx, cy)) > 0


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available in this environment")
def test_apply_channel_watermark_bakes_the_badge_into_the_final_video(tmp_path: Path):
    video_path = tmp_path / "final.mp4"
    _make_solid_video(video_path, with_audio=True)

    applied = _apply_channel_watermark(str(video_path), tmp_path, job_id=0)

    assert applied is True
    assert _verify_video(str(video_path))
    frame_path = tmp_path / "frame.png"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-frames:v", "1", str(frame_path)],
        capture_output=True, check=True,
    )
    frame = Image.open(frame_path).convert("RGB")
    region = watermark_region((frame.width, frame.height))
    cx, cy = region["x"] + region["width"] // 2, region["y"] + region["height"] // 2
    def _close_to_blue(pixel: tuple[int, int, int], tolerance: int = 8) -> bool:
        r, g, b = pixel
        return r <= tolerance and g <= tolerance and b >= 255 - tolerance

    assert not _close_to_blue(frame.getpixel((cx, cy)))  # 순수 파란 배경이 아니라 배지가 그려져 있어야 한다.
    assert _close_to_blue(frame.getpixel((10, frame.height - 10)))  # 다른 영역은 그대로 유지된다(H.264 압축 오차 허용).


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available in this environment")
def test_apply_channel_watermark_preserves_audio(tmp_path: Path):
    video_path = tmp_path / "final.mp4"
    _make_solid_video(video_path, with_audio=True)

    assert _apply_channel_watermark(str(video_path), tmp_path, job_id=0) is True

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    assert "audio" in probe.stdout


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available in this environment")
def test_apply_channel_watermark_works_on_a_video_without_audio(tmp_path: Path):
    video_path = tmp_path / "final.mp4"
    _make_solid_video(video_path, with_audio=False)

    assert _apply_channel_watermark(str(video_path), tmp_path, job_id=0) is True
    assert _verify_video(str(video_path))

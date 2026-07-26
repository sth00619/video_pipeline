"""Deterministic scene-layer assembly for the editorial-cartoon pipeline.

The image model makes only the clean illustrated plate.  Verified information
is written to that plate and the channel's canonical transparent character is
then placed above it.  Keeping the character as the final foreground layer is
what makes a pointing finger or open palm reliably occlude a chart prop.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


SCENE_LAYER_PIPELINE_VERSION = "3.0"
CANVAS_SIZE = (1920, 1080)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_pose_asset(poses_dir: str, pose: str, fallback_pose: str | None = None) -> Path | None:
    """Resolve a pose deterministically; never substitute a generated mascot."""
    root = Path(poses_dir)
    for name in (pose, fallback_pose, "neutral"):
        candidate = root / f"{name}.png" if name else None
        if candidate and candidate.is_file():
            return candidate
    return None


def character_identity(poses_dir: str, pose_asset: Path) -> dict[str, str]:
    """Read the library identity lock, with a stable legacy-library fallback."""
    root = Path(poses_dir)
    manifest_path = root / "identity_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        manifest = {}
    character_id = str(manifest.get("canonical_character_id") or "")
    if not character_id:
        meta_path = root / "library_meta.json"
        try:
            description = str(json.loads(meta_path.read_text(encoding="utf-8")).get("character_description") or "")
        except (OSError, ValueError, TypeError):
            description = ""
        character_id = hashlib.sha256(f"legacy|{description}|{root.name}".encode("utf-8")).hexdigest()[:20]
    return {
        "canonical_character_id": character_id,
        "pose_asset_sha256": _sha256(pose_asset),
        "identity_manifest_version": str(manifest.get("version") or "legacy"),
    }


def compose_character_foreground(
    background_path: str,
    poses_dir: str,
    pose: str,
    output_path: str,
    *,
    fallback_pose: str | None = None,
    placement: str = "right third",
    canvas_size: tuple[int, int] = CANVAS_SIZE,
) -> dict[str, Any]:
    """Compose an alpha character layer above a prepared background surface.

    A full-frame alpha mask is emitted next to the still.  It is both an audit
    artifact and a concrete guarantee that any opaque hand/finger pixels are
    above the information surface in the final z-order.
    """
    background = Path(background_path)
    output = Path(output_path)
    pose_asset = resolve_pose_asset(poses_dir, pose, fallback_pose)
    if pose_asset is None:
        raise FileNotFoundError(f"No canonical pose asset for {pose!r} in {poses_dir}")

    with Image.open(background) as source:
        plate = source.convert("RGBA").resize(canvas_size, Image.Resampling.LANCZOS)
    with Image.open(pose_asset) as source:
        foreground = source.convert("RGBA")
    alpha_bounds = foreground.getchannel("A").getbbox()
    if not alpha_bounds:
        raise ValueError(f"Pose asset has no alpha foreground: {pose_asset}")
    foreground = foreground.crop(alpha_bounds)

    width, height = canvas_size
    is_left = "left" in placement.lower()
    max_width = int(width * (.37 if is_left else .39))
    max_height = min(int(height * .79), height - 140)
    scale = min(max_width / foreground.width, max_height / foreground.height)
    rendered_size = (max(1, round(foreground.width * scale)), max(1, round(foreground.height * scale)))
    foreground = foreground.resize(rendered_size, Image.Resampling.LANCZOS)
    x = 48 if is_left else width - foreground.width - 48
    y = height - foreground.height - 58

    foreground_canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    foreground_canvas.alpha_composite(foreground, (x, y))
    final = Image.alpha_composite(plate, foreground_canvas)
    output.parent.mkdir(parents=True, exist_ok=True)
    final.convert("RGB").save(output, "PNG" if output.suffix.lower() == ".png" else "JPEG", quality=95)

    mask_path = output.with_name(f"{output.stem}.foreground-mask.png")
    foreground_canvas.getchannel("A").save(mask_path)
    identity = character_identity(poses_dir, pose_asset)
    return {
        "version": SCENE_LAYER_PIPELINE_VERSION,
        "background_path": str(background),
        "surface_image_path": str(background),
        "foreground_asset_path": str(pose_asset),
        "foreground_mask_path": str(mask_path),
        "foreground_bounds": {"x": x, "y": y, "width": foreground.width, "height": foreground.height},
        "character_regions": [{"x": round(x / width, 5), "y": round(y / height, 5), "width": round(foreground.width / width, 5), "height": round(foreground.height / height, 5), "source": "alpha_foreground_mask"}],
        "z_order": ["clean_background", "verified_info_surface", "character_foreground", "editorial_text"],
        **identity,
    }


def write_layer_manifest(output_path: str, metadata: dict[str, Any]) -> str:
    """Persist resume-safe layer provenance beside the final still."""
    output = Path(output_path)
    manifest_path = output.with_name(f"{output.stem}.scene-layers.json")
    manifest_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return str(manifest_path)


def load_layer_manifest(output_path: str) -> dict[str, Any] | None:
    path = Path(output_path).with_name(f"{Path(output_path).stem}.scene-layers.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None

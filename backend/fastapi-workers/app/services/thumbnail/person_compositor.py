"""Approved real-person image compositing.

This module intentionally has no image-generation provider dependency.  A
photo must be approved and carry a known licence before it can reach Pillow.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter


ALLOWED_LICENSES = {
    "PRESS_KIT", "KOGL_TYPE1", "CC_BY", "CC_BY_SA", "OWNED",
    "STOCK_LICENSED", "AGENCY_LICENSED",
}
_REMBG_SESSIONS: dict[str, Any] = {}


class PhotoLicenseError(RuntimeError):
    """Raised before an unapproved or unknown photo can be rendered."""


def validate_photo(photo: dict[str, Any]) -> None:
    license_type = str(photo.get("license_type") or "UNKNOWN").upper()
    if license_type not in ALLOWED_LICENSES:
        raise PhotoLicenseError(f"PHOTO_LICENSE_MISSING: {photo.get('photo_id') or 'unknown'}")
    if not bool(photo.get("approved")):
        raise PhotoLicenseError(f"PHOTO_LICENSE_MISSING: {photo.get('photo_id') or 'unknown'} is not approved")
    if str(photo.get("rights_review_status") or "APPROVED").upper() not in {"APPROVED", "NOT_REQUIRED"}:
        raise PhotoLicenseError(f"RIGHTS_REVIEW_REQUIRED: {photo.get('photo_id') or 'unknown'}")
    if license_type == "AGENCY_LICENSED" and not str(photo.get("license_ref") or "").strip():
        raise PhotoLicenseError(f"PHOTO_LICENSE_MISSING: agency contract reference required")
    # A visual effect never substitutes for a provenance record.  Press-kit,
    # stock and Creative Commons photos must carry the source/licence record
    # that was reviewed before this renderer can publish them.  OWNED material
    # is reviewed through the explicit approval flag above.
    needs_reference = {"PRESS_KIT", "KOGL_TYPE1", "CC_BY", "CC_BY_SA", "STOCK_LICENSED", "AGENCY_LICENSED"}
    if license_type in needs_reference and not str(photo.get("license_ref") or "").strip():
        raise PhotoLicenseError(f"PHOTO_LICENSE_MISSING: source or licence reference required for {license_type}")


def _cache_path(photo: dict[str, Any], source: Path) -> Path:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    model = str(photo.get("cutout_model") or "isnet-general-use").replace("/", "-")
    return source.parent / f"{source.stem}.{model}.{digest}.cutout.png"


def ensure_cutout(photo: dict[str, Any]) -> Path:
    """Return a transparent cutout, generating it once with a local rembg session.

    The import is deliberately lazy so API startup and tests do not require an
    ONNX runtime until a newly registered person photo is actually composed.
    """
    validate_photo(photo)
    declared = Path(str(photo.get("cutout_path") or "")) if photo.get("cutout_path") else None
    # A previously reviewed cutout is a complete, immutable input for the
    # compositor.  It may be retained after an original is moved to cold
    # storage, so do not force a second background-removal run in that case.
    if declared and declared.is_file() and declared.stat().st_size > 1024:
        return declared
    source = Path(str(photo.get("original_path") or photo.get("local_path") or ""))
    if not source.is_file():
        raise PhotoLicenseError(f"PHOTO_SOURCE_MISSING: {photo.get('photo_id') or source}")
    output = _cache_path(photo, source)
    if output.is_file() and output.stat().st_size > 1024:
        return output
    try:
        from rembg import new_session, remove  # type: ignore
    except ImportError as exc:  # explicit; never silently use an opaque AI edit
        raise PhotoLicenseError("PHOTO_CUTOUT_RUNTIME_MISSING: rembg[cpu] is required") from exc

    model = str(photo.get("cutout_model") or "isnet-general-use")
    # rembg documents session reuse as the efficient multi-image path.  Keep
    # one local ONNX session per model for this worker process; the cache file
    # above still avoids inference entirely for repeat photo IDs.
    session = _REMBG_SESSIONS.get(model)
    if session is None:
        session = new_session(model)
        _REMBG_SESSIONS[model] = session
    with Image.open(source) as original:
        result = remove(original.convert("RGBA"), session=session, post_process_mask=True)
        result.save(output, "PNG")
    return output


def paste_person(canvas: Image.Image, photo: dict[str, Any], *, side: str = "right",
                 height_ratio: float = 0.72, width_ratio: float = .46,
                 outline_px: int = 5) -> dict[str, Any]:
    """Paste an approved person with mask-only styling and no generative edit."""
    cutout = ensure_cutout(photo)
    with Image.open(cutout) as loaded:
        subject = loaded.convert("RGBA")
    content = subject.getchannel("A").getbbox()
    if content:
        pad = max(8, round(min(subject.size) * .02))
        subject = subject.crop((
            max(0, content[0] - pad),
            max(0, content[1] - pad),
            min(subject.width, content[2] + pad),
            min(subject.height, content[3] + pad),
        ))
    max_height = max(1, int(canvas.height * min(max(height_ratio, .2), .9)))
    scale = min(
        max_height / max(subject.height, 1),
        (canvas.width * min(max(width_ratio, .20), .58)) / max(subject.width, 1),
    )
    subject = subject.resize((max(1, round(subject.width * scale)), max(1, round(subject.height * scale))), Image.Resampling.LANCZOS)
    alpha = subject.getchannel("A")
    expanded = alpha.filter(ImageFilter.MaxFilter(max(3, outline_px * 2 + 1)))
    # Manual entertainment/news thumbnails commonly use a hard white cutout
    # edge plus a dark drop shadow.  Keep the source face pixels untouched.
    outline = Image.new("RGBA", subject.size, (255, 255, 255, 0))
    outline.putalpha(expanded.point(lambda px: 245 if px else 0))
    shadow_alpha = expanded.filter(ImageFilter.GaussianBlur(max(3, outline_px)))
    shadow = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    shadow.putalpha(shadow_alpha.point(lambda px: min(190, round(px * .72))))
    # Colour is applied only to an expanded alpha silhouette behind the source
    # photograph. The actual face/body pixels remain the licensed original.
    # Red/gold is an editorial accent; it is never painted over the portrait.
    glow_alpha = expanded.filter(ImageFilter.GaussianBlur(max(8, outline_px * 3)))
    glow = Image.new("RGBA", subject.size, (240, 67, 41, 0))
    glow.putalpha(glow_alpha.point(lambda px: min(150, round(px * .56))))
    margin = max(18, round(canvas.width * .025))
    x = margin if side == "left" else canvas.width - subject.width - margin
    y = max(0, canvas.height - subject.height - margin)
    canvas.alpha_composite(glow, (x - outline_px * 2, y - outline_px * 2))
    canvas.alpha_composite(shadow, (x + outline_px, y + outline_px))
    canvas.alpha_composite(outline, (x, y))
    canvas.alpha_composite(subject, (x, y))
    return {
        "x": x, "y": y, "width": subject.width, "height": subject.height,
        "cutout_path": str(cutout),
        "visual_treatment": ["mask_only_red_glow", "white_outline", "drop_shadow"],
    }

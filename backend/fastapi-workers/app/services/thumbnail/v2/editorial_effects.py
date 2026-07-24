"""Non-generative editorial treatments for deterministic thumbnail layouts.

These effects operate on the background or on an alpha mask only.  They never
invent or alter a person's face, and therefore are a visual treatment rather
than a claim that image rights disappear after editing.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


def grade_mascot_backdrop(canvas: Image.Image) -> Image.Image:
    """Turn an in-video scene into a quiet editorial plate.

    Older scenes can contain an already-rendered character that has no
    keep-out metadata.  A broad blur and navy grade retain the video's colour
    and provenance while preventing that old figure from reading as a second
    mascot behind the selected channel character.
    """
    base = canvas.convert("RGBA")
    radius = max(8, round(canvas.width / 150))
    base = base.filter(ImageFilter.GaussianBlur(radius))
    base = ImageEnhance.Color(base.convert("RGB")).enhance(.62).convert("RGBA")
    base = ImageEnhance.Contrast(base.convert("RGB")).enhance(1.12).convert("RGBA")
    base = ImageEnhance.Brightness(base.convert("RGB")).enhance(.78).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (5, 12, 28, 72))
    base.alpha_composite(overlay)
    return base


def grade_photo_backdrop(canvas: Image.Image, *, subject_side: str) -> Image.Image:
    """Blur and colour-grade a scene plate so the cutout remains the focal point."""
    base = canvas.convert("RGBA")
    blurred = base.filter(ImageFilter.GaussianBlur(max(8, round(canvas.width / 180))))
    blurred = ImageEnhance.Color(blurred.convert("RGB")).enhance(.58).convert("RGBA")
    blurred = ImageEnhance.Contrast(blurred.convert("RGB")).enhance(1.20).convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = canvas.size
    # A cool-to-warm editorial wash provides separation without inserting a
    # third-party logo, a synthetic face or an unverified numerical claim.
    for x in range(width):
        focus = x / max(1, width - 1)
        if subject_side == "right":
            focus = 1 - focus
        alpha = int(150 * (focus ** 1.55))
        draw.line((x, 0, x, height), fill=(5, 10, 24, alpha))
    draw.rectangle((0, int(height * .60), width, height), fill=(0, 0, 0, 160))
    accent_x = int(width * (.08 if subject_side == "right" else .92))
    glow = max(150, int(width * .16))
    for radius in range(glow, 20, -12):
        alpha = max(0, int(1.3 * (glow - radius)))
        draw.ellipse(
            (accent_x - radius, int(height * .33) - radius, accent_x + radius, int(height * .33) + radius),
            fill=(242, 67, 43, min(38, alpha)),
        )
    blurred.alpha_composite(overlay)
    return blurred


def draw_person_accent(canvas: Image.Image, region: dict[str, int], *, side: str) -> None:
    """Place graphic accents around, never over, the approved person's face."""
    width, height = canvas.size
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y = int(region["x"]), int(region["y"])
    rw, rh = int(region["width"]), int(region["height"])
    if side == "right":
        left, right = max(20, x - int(width * .11)), max(24, x - 12)
    else:
        left, right = min(width - 24, x + rw + 12), min(width - 20, x + rw + int(width * .11))
    top, bottom = max(20, y + int(rh * .08)), min(int(height * .61), y + int(rh * .72))
    # One restrained direction marker; avoid stacking arrows, circles and
    # frames around a portrait because that competes with the facial cue.
    draw.arc((left, top, right, bottom), 208, 334, fill=(239, 48, 38, 220), width=10)
    draw.polygon([(right - 2, top + 15), (right - 34, top + 23), (right - 11, top + 47)], fill=(239, 48, 38, 220))
    canvas.alpha_composite(layer)

"""Selection-safe compositor for the channel's own mascot sprite sheet."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


_SHEET_REGIONS = {
    "neutral": (.36, .06, .66, .66),
    "highlight": (.50, .69, .72, .99),
    # The worried/surprised sprite is immediately followed by another coin in
    # the sheet; its right edge deliberately stops before that neighbour.
    "worried": (.24, .69, .395, .99),
    "surprised": (.24, .69, .395, .99),
    "happy": (.75, .69, .99, .99),
}


def _transparent_background(image: Image.Image) -> Image.Image:
    """Remove a near-uniform sprite-sheet backing without altering the mascot."""
    rgba = image.convert("RGBA")
    sample = rgba.getpixel((0, 0))[:3]
    # Difference from a flat corner colour produces a conservative alpha mask.
    background = Image.new("RGB", rgba.size, sample)
    difference = ImageChops.difference(rgba.convert("RGB"), background).convert("L")
    alpha = difference.point(lambda value: 0 if value < 16 else min(255, (value - 16) * 6))
    rgba.putalpha(alpha)
    return rgba


def load_mascot(path: str, emotion: str) -> Image.Image:
    source_path = Path(path)
    with Image.open(source_path) as loaded:
        image = loaded.convert("RGBA")
    if "sheet" in source_path.stem.lower():
        left, top, right, bottom = _SHEET_REGIONS.get(emotion, _SHEET_REGIONS["neutral"])
        image = image.crop((round(left * image.width), round(top * image.height), round(right * image.width), round(bottom * image.height)))
        image = _transparent_background(image)
        bbox = image.getchannel("A").getbbox()
        if bbox:
            pad = max(6, round(min(image.size) * .025))
            image = image.crop((
                max(0, bbox[0] - pad),
                max(0, bbox[1] - pad),
                min(image.width, bbox[2] + pad),
                min(image.height, bbox[3] + pad),
            ))
    return image


def paste_mascot(
    canvas: Image.Image,
    path: str,
    emotion: str,
    *,
    max_height_ratio: float = .26,
    max_width_ratio: float = .42,
    side: str = "right",
    safe_bottom_ratio: float = .54,
) -> dict[str, int | str]:
    mascot = load_mascot(path, emotion)
    max_height = int(canvas.height * min(max(float(max_height_ratio), .10), .58))
    max_width = int(canvas.width * min(max(float(max_width_ratio), .18), .52))
    scale = min(max_height / max(mascot.height, 1), max_width / max(mascot.width, 1))
    mascot = mascot.resize((max(1, round(mascot.width * scale)), max(1, round(mascot.height * scale))), Image.Resampling.LANCZOS)
    alpha = mascot.getchannel("A")
    outline = alpha.filter(ImageFilter.MaxFilter(17))
    halo = Image.new("RGBA", mascot.size, (255, 255, 255, 0))
    halo.putalpha(outline.point(lambda pixel: 245 if pixel else 0))
    x = (
        int(canvas.width * .055)
        if side == "left"
        else canvas.width - mascot.width - int(canvas.width * .055)
    )
    y = max(
        # A hero mascot may begin close to the top edge, but it must finish
        # before the title shelf.  This leaves room for a larger, more
        # recognisable silhouette without creating a false QA pass through
        # overlapping copy.
        int(canvas.height * .018),
        int(canvas.height * safe_bottom_ratio) - mascot.height - 12,
    )
    shadow_alpha = outline.filter(ImageFilter.GaussianBlur(10))
    shadow = Image.new("RGBA", mascot.size, (0, 0, 0, 0))
    shadow.putalpha(shadow_alpha.point(lambda pixel: min(170, round(pixel * .66))))
    canvas.alpha_composite(shadow, (x + 12, y + 16))
    canvas.alpha_composite(halo, (x, y))
    canvas.alpha_composite(mascot, (x, y))
    return {"type": "selected_mascot", "x": x, "y": y, "width": mascot.width, "height": mascot.height, "asset_path": path}

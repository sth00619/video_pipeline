"""Surface-specific deterministic texture for factual cartoon ink."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from .ink_primitives import seeded_rng


def apply_material_fx(content: Image.Image, surface_kind: str, scene_seed: int | str | None) -> Image.Image:
    """Add restrained surface response without modifying factual glyph layout."""
    image = content.convert("RGBA")
    kind = surface_kind.lower()
    rng = seeded_rng(scene_seed)
    alpha = image.getchannel("A")
    if "chalk" in kind or "board" in kind:
        # Small alpha variation makes chalk sit in the board grain while all
        # opaque core pixels remain present for readability and OCR.
        array = np.asarray(alpha, dtype=np.int16).copy()
        active = array > 20
        noise = rng.integers(-24, 9, size=array.shape, dtype=np.int16)
        array[active] = np.clip(array[active] + noise[active], 0, 255)
        image.putalpha(Image.fromarray(array.astype(np.uint8), "L"))
        return image.filter(ImageFilter.GaussianBlur(.12))
    if "monitor" in kind or "screen" in kind:
        glow = Image.new("RGBA", image.size, (246, 210, 72, 0))
        glow.putalpha(alpha.filter(ImageFilter.GaussianBlur(2)))
        return Image.alpha_composite(glow, image)
    # Paper/clipboard: a one-pixel bleed stays outside the sharp ink core.
    bleed = Image.new("RGBA", image.size, (45, 31, 18, 0))
    bleed.putalpha(alpha.filter(ImageFilter.MaxFilter(3)).point(lambda value: value // 7))
    return Image.alpha_composite(bleed, image)

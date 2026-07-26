"""Channel-scoped visual tokens for deterministic editorial overlays.

The worker receives the channel's ``reference_style_profile`` from Spring.
It must not consult process-wide environment variables: two channels rendered
by the same worker need to keep their own visual identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


_FONT_ROOT = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_BLACK_HAN = _FONT_ROOT / "BlackHanSans-Regular.ttf"


@dataclass(frozen=True)
class ChannelOverlayStyle:
    # Read from a 16:9 mobile screen: warm yellow asks the question, red flags
    # the danger, cyan/blue remain reserved for data.  These are channel-owned
    # tokens, not colours sampled from a third-party channel.
    danger_color: str = "#FF5148"
    benefit_color: str = "#FFD230"
    neutral_color: str = "#FFFFFF"
    subtitle_emphasis: str = "#FFD230"
    max_overlay_area_ratio: float = .18
    speech_max_width_ratio: float = .42
    card_max_width_ratio: float = .32
    display_font_ratio: float = .102
    # The approved comic plate already supplies strong black ink contours.
    # Display copy therefore uses a light separation edge, not a second heavy
    # outline that turns Korean glyphs into swollen black shapes.
    text_outline_ratio: float = .018
    bubble_outline_ratio: float = .0030
    font_body: Path = _BLACK_HAN
    font_display: Path = _BLACK_HAN
    font_chalk: Path = _BLACK_HAN


BLACK_HAN_SANS_V1 = ChannelOverlayStyle()


def load_channel_overlay_style(reference_style_profile: str | None) -> ChannelOverlayStyle:
    """Resolve a persisted profile name to locally bundled, licensed assets.

    New names are deliberately rejected.  Falling back to an arbitrary host
    font would make preview and production output diverge and bypass font
    licensing review.
    """
    if (reference_style_profile or "black_han_sans_v1") != "black_han_sans_v1":
        raise ValueError("UNSUPPORTED_REFERENCE_STYLE_PROFILE")
    return BLACK_HAN_SANS_V1

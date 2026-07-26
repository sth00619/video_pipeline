"""Render two deterministic typography examples onto generated cartoon plates.

The image model supplies only the cartoon setting and mascot.  All Korean copy
and figures below are deliberately rendered by Pillow, just as the production
overlay path does, so the examples demonstrate the real no-hallucinated-text
rule rather than asking an image model to spell Korean.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
GENERATED = Path(r"C:\Users\song\.codex\generated_images\019f9450-983c-72a0-b6e7-66b7df5b3bef")
OUT = ROOT / "frontend" / "public" / "thumbnail-examples"
FONT = Path(r"C:\Windows\Fonts\malgunbd.ttf")
SPLIT_REFERENCE = Path(r"C:\Users\song\AppData\Local\Temp\codex-clipboard-68400fcd-edf5-4ce0-83db-561ff3c18b02.png")
PORT_REFERENCE = Path(r"C:\Users\song\.codex\generated_images\019f9450-983c-72a0-b6e7-66b7df5b3bef\exec-b8dc8282-bfca-4227-ad77-e988cdb06f9a.png")
MAP_REFERENCE = Path(r"C:\Users\song\.codex\generated_images\019f9450-983c-72a0-b6e7-66b7df5b3bef\exec-59a6fe65-f249-477c-baf7-c5efe8b8a877.png")
TRADE_REFERENCE = Path(r"C:\Users\song\.codex\generated_images\019f9450-983c-72a0-b6e7-66b7df5b3bef\exec-85c6b5ce-a2dc-494a-bae1-b3ecbbba375c.png")
OUT.mkdir(parents=True, exist_ok=True)


def _font(size: int):
    return ImageFont.truetype(str(FONT), size)


def _center(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, size: int, fill, *, stroke: int = 0):
    face = _font(size)
    spacing = max(5, size // 9)
    bounds = draw.multiline_textbbox((0, 0), text, font=face, spacing=spacing, align="center", stroke_width=stroke)
    x = box[0] + (box[2] - box[0] - (bounds[2] - bounds[0])) / 2
    y = box[1] + (box[3] - box[1] - (bounds[3] - bounds[1])) / 2
    draw.multiline_text((x, y), text, font=face, fill=fill, spacing=spacing, align="center", stroke_width=stroke, stroke_fill="#000000")


def _subtitle(draw: ImageDraw.ImageDraw, text: str):
    _center(draw, (210, 835, 1485, 917), text, 37, "#FFFFFF")


def market_explainer():
    image = Image.open(GENERATED / "exec-026048cf-5793-40eb-8d4d-a3b49f0647f3.png").convert("RGBA")
    draw = ImageDraw.Draw(image)
    # One question in yellow, factual labels in white/dark only, and the fixed black subtitle bar.
    _center(draw, (55, 23, 515, 144), "왜 장중에\n반등했나?", 58, "#FFD230", stroke=6)
    _center(draw, (305, 311, 572, 404), "금리\n부담", 43, "#FFFFFF", stroke=4)
    _center(draw, (805, 417, 1070, 505), "수급\n개선", 42, "#FFFFFF", stroke=4)
    _subtitle(draw, "원인을 함께 봐야 숫자가 보입니다")
    image.save(OUT / "rule-example-speech-explainer-v1.png")


def chalkboard_data():
    image = Image.open(GENERATED / "exec-45aa8d07-ed03-448c-8335-77b44ea0a4fe.png").convert("RGBA")
    draw = ImageDraw.Draw(image)
    # These are sample values.  In production the same placements use only the collector payload.
    _center(draw, (135, 185, 420, 365), "외국인\n순매수", 43, "#FFFFFF", stroke=3)
    _center(draw, (485, 204, 770, 354), "8,864.24", 46, "#FFFFFF", stroke=3)
    _center(draw, (785, 195, 1080, 355), "▲ 1.58%", 46, "#FFD230", stroke=3)
    _subtitle(draw, "수치는 흐름 안에서 설명합니다")
    image.save(OUT / "rule-example-verified-data-v1.png")


def cinematic_split_information():
    """Use the approved high-detail cartoon grammar with deterministic copy."""
    image = Image.open(SPLIT_REFERENCE).convert("RGBA")
    draw = ImageDraw.Draw(image)
    # Two concise causal panels.  The only red is the adverse exact value;
    # the burst uses the channel's single warm-yellow question emphasis.
    _center(draw, (88, 92, 600, 332), "관세 12.5%\n비용 압박", 52, "#171717", stroke=1)
    _center(draw, (1090, 92, 1608, 332), "최대 10%\n부담 완화", 52, "#171717", stroke=1)
    _center(draw, (674, 86, 995, 306), "차이는\n여기서!", 53, "#171717", stroke=1)
    draw.rectangle((0, 824, image.width, image.height), fill="#000000")
    _center(draw, (150, 833, 1515, 924), "같은 수출이라도 조건에 따라 비용은 달라집니다", 35, "#FFFFFF")
    image.save(OUT / "rule-example-cinematic-split-data-v2.png")


def cinematic_split_graph():
    """A data-first variant: exact values and a compact graph on scene props."""
    image = Image.open(SPLIT_REFERENCE).convert("RGBA")
    draw = ImageDraw.Draw(image)
    # Left paper: downside rate card.  Right paper: an intentionally simple
    # four-period comparison bar chart.  The source production renderer uses
    # collected values in these same slots instead of the sample values here.
    _center(draw, (95, 84, 590, 156), "수입 비용", 34, "#383838")
    _center(draw, (95, 138, 590, 257), "+12.5%", 67, "#D53434", stroke=0)
    _center(draw, (95, 264, 590, 332), "관세 적용 시", 30, "#454545")
    _center(draw, (1085, 82, 1610, 150), "비용 상한 비교", 34, "#383838")
    # Minimal bars: black measurement rule, one muted bar, one yellow key bar.
    draw.line((1140, 305, 1555, 305), fill="#373737", width=3)
    for x, height, color, label in ((1185, 88, "#8D8D8D", "기준"), (1330, 150, "#D53434", "12.5%"), (1475, 120, "#FFD230", "10.0%")):
        draw.rectangle((x, 305 - height, x + 76, 305), fill=color, outline="#373737", width=1)
        _center(draw, (x - 20, 314, x + 96, 356), label, 22, "#383838")
    _center(draw, (674, 103, 995, 275), "숫자는\n비교해서 봐야", 42, "#171717", stroke=1)
    draw.rectangle((0, 824, image.width, image.height), fill="#000000")
    _center(draw, (150, 833, 1515, 924), "같은 이슈도 숫자를 비교하면 차이가 보입니다", 35, "#FFFFFF")
    image.save(OUT / "rule-example-cinematic-graph-v1.png")


def cinematic_split_trend():
    """Trend-plus-metric layout for longer factual explanations."""
    image = Image.open(SPLIT_REFERENCE).convert("RGBA")
    draw = ImageDraw.Draw(image)
    _center(draw, (92, 76, 602, 140), "지수 추이", 36, "#383838")
    # Minimal five-point trend: one yellow key line, no terminal-style grid.
    chart = [(130, 293), (220, 265), (310, 282), (400, 206), (510, 166)]
    draw.line(chart, fill="#FFD230", width=10, joint="curve")
    for x, y in chart:
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill="#FFD230", outline="#3A3A3A", width=1)
    draw.line((122, 310, 548, 310), fill="#555555", width=2)
    for x, label in ((130, "1월"), (310, "3월"), (510, "5월")):
        _center(draw, (x - 30, 314, x + 30, 350), label, 18, "#4A4A4A")
    _center(draw, (1090, 76, 1610, 140), "핵심 수치", 36, "#383838")
    _center(draw, (1090, 142, 1610, 242), "8,864.24", 58, "#171717")
    _center(draw, (1090, 250, 1610, 312), "기간 변화  +1.58%", 30, "#D53434")
    _center(draw, (677, 105, 990, 274), "추세와\n숫자를 같이", 44, "#171717", stroke=1)
    draw.rectangle((0, 824, image.width, image.height), fill="#000000")
    _center(draw, (150, 833, 1515, 924), "한 번의 등락보다 흐름을 먼저 확인합니다", 35, "#FFFFFF")
    image.save(OUT / "rule-example-cinematic-trend-v1.png")


def port_cost_data_story():
    """Different scene, same reusable story-board + exact-data grammar."""
    image = Image.open(PORT_REFERENCE).convert("RGBA")
    draw = ImageDraw.Draw(image)
    # White burst with light, black display lettering: the speech shape carries
    # separation, so the glyphs do not need the former heavy outline.
    burst = [(65, 85), (118, 55), (195, 65), (245, 42), (305, 78), (360, 63), (400, 125), (382, 193), (405, 245), (330, 268), (276, 312), (220, 285), (155, 306), (112, 255), (50, 225), (76, 163)]
    draw.polygon(burst, fill="#FFFFFF", outline="#111111", width=5)
    _center(draw, (86, 85, 370, 250), "관세가\n왜 중요해?", 43, "#171717", stroke=0)

    # Right parchment: one readable graph and two exact values.  This is a
    # layout sample; production replaces only the payload, not the geometry.
    _center(draw, (875, 90, 1600, 148), "수입 비용 변화", 39, "#242424")
    points = [(920, 470), (1100, 382), (1280, 318), (1470, 345)]
    draw.line(points, fill="#D53434", width=8, joint="curve")
    draw.line((900, 495, 1515, 495), fill="#545454", width=2)
    for x, y in points:
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill="#D53434", outline="#171717", width=1)
    for x, label in ((920, "기준"), (1100, "관세"), (1280, "12.5%"), (1470, "상한")):
        _center(draw, (x - 46, 502, x + 46, 538), label, 20, "#343434")
    _center(draw, (900, 560, 1190, 644), "+12.5%", 55, "#D53434")
    _center(draw, (1235, 565, 1570, 640), "상한 10.0%", 34, "#242424")
    draw.rectangle((0, 842, image.width, image.height), fill="#000000")
    _center(draw, (190, 850, 1480, 930), "관세는 수입 비용의 흐름을 바꿉니다", 35, "#FFFFFF")
    image.save(OUT / "rule-example-port-cost-data-v1.png")


def map_tariff_comparison():
    """Two policy rates are a direct comparison, never a time-series graph."""
    image = Image.open(MAP_REFERENCE).convert("RGBA")
    draw = ImageDraw.Draw(image)
    _center(draw, (104, 230, 445, 408), "기준 관세\n12.5%", 45, "#FFFFFF", stroke=1)
    _center(draw, (770, 230, 1105, 408), "임시 상한\n10.0%", 43, "#FFFFFF", stroke=1)
    draw.rectangle((0, 792, image.width, image.height), fill="#000000")
    _center(draw, (160, 804, 1510, 890), "관세율이 다르면 같은 수입품도 비용이 달라집니다", 35, "#FFFFFF")
    image.save(OUT / "rule-example-map-tariff-comparison-v1.png")


def trade_scale_comparison():
    """Data-rich comparison with a shared base and matching values."""
    image = Image.open(TRADE_REFERENCE).convert("RGBA")
    draw = ImageDraw.Draw(image)
    # The circular paper at left is a *normalisation token*, not decorative
    # empty space: every other number in the scene is explicitly anchored to
    # this same baseline.  It remains an in-world paper rather than another
    # permanent dashboard card.
    draw.rounded_rectangle((83, 128, 357, 274), radius=14, fill="#EEDDBD", outline="#3A3026", width=2)
    _center(draw, (102, 143, 338, 183), "비교 기준", 24, "#242424")
    _center(draw, (102, 178, 338, 244), "100", 51, "#242424")
    _center(draw, (100, 242, 340, 270), "같은 조건으로 환산", 16, "#55504A")

    # A cream tag physically attached to the weight keeps white text from
    # colliding with its dark texture while preserving the scale metaphor.
    draw.rounded_rectangle((848, 412, 1050, 502), radius=10, fill="#F3E5C7", outline="#352B22", width=2)
    _center(draw, (860, 420, 1038, 494), "기준 지수\n100", 25, "#242424")
    _center(draw, (1180, 404, 1415, 500), "상한\n110.0", 34, "#242424")
    _center(draw, (80, 70, 360, 122), "같은 기준에서", 28, "#242424")

    # Explicit chart card: it occludes incidental generated marks and keeps
    # every coordinate inside a named safe rectangle.  The y-axis is a
    # documented 95--115 truncated range, so 100 / 112.5 / 110.0 bars are
    # proportionate rather than visually exaggerated from an unstated zero.
    card = (1360, 78, 1642, 380)
    draw.rounded_rectangle(card, radius=12, fill="#F3E5C7", outline="#352B22", width=3)
    _center(draw, (1380, 88, 1620, 124), "비용 지수 비교", 25, "#242424")
    _center(draw, (1380, 120, 1620, 148), "지수 기준 = 100", 16, "#55504A")
    plot_left, plot_top, plot_right, plot_bottom = 1400, 170, 1612, 305
    minimum, maximum = 95.0, 115.0
    for tick in (95, 100, 105, 110, 115):
        y = round(plot_bottom - (tick - minimum) / (maximum - minimum) * (plot_bottom - plot_top))
        draw.line((plot_left, y, plot_right, y), fill="#B8AA91", width=1)
        _center(draw, (1365, y - 11, 1395, y + 11), str(tick), 13, "#55504A")
    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill="#343434", width=2)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill="#343434", width=2)
    for x, value, color, label in ((1420, 100.0, "#969696", "기준"), (1490, 112.5, "#D53434", "관세"), (1560, 110.0, "#FFD230", "상한")):
        y = round(plot_bottom - (value - minimum) / (maximum - minimum) * (plot_bottom - plot_top))
        draw.rectangle((x, y, x + 42, plot_bottom), fill=color, outline="#242424", width=1)
        _center(draw, (x - 4, y - 27, x + 47, y - 4), f"{value:.1f}", 13, "#242424")
        _center(draw, (x - 7, 314, x + 49, 340), label, 14, "#242424")
    draw.rectangle((0, 756, image.width, image.height), fill="#000000")
    _center(draw, (140, 770, 1510, 850), "수치는 반드시 같은 기준으로 비교합니다", 35, "#FFFFFF")
    image.save(OUT / "rule-example-trade-scale-comparison-v1.png")


if __name__ == "__main__":
    market_explainer()
    chalkboard_data()
    cinematic_split_information()
    cinematic_split_graph()
    cinematic_split_trend()
    port_cost_data_story()
    map_tariff_comparison()
    trade_scale_comparison()

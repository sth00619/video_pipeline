import os
import logging
from PIL import Image, ImageDraw, ImageFont
import math

logger = logging.getLogger(__name__)

# W=1920, H=1080
PANEL_CENTER_X = 1382
PANEL_CENTER_Y = 540
PANEL_RADIUS = 410

FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "DejaVuSans.ttf" # Fallback if nanum is missing locally

def get_font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def draw_cream_panel(draw: ImageDraw.ImageDraw):
    """Draws a safe fallback cream panel in case AI QC fails or for strict overlay consistency."""
    left = PANEL_CENTER_X - PANEL_RADIUS
    top = PANEL_CENTER_Y - PANEL_RADIUS
    right = PANEL_CENTER_X + PANEL_RADIUS
    bottom = PANEL_CENTER_Y + PANEL_RADIUS
    
    # Outer dark teal frame
    draw.ellipse([left - 6, top - 6, right + 6, bottom + 6], fill=(20, 50, 60))
    # Cream panel body
    draw.ellipse([left, top, right, bottom], fill=(245, 243, 235))

def render_chart_to_overlay(payload: dict) -> Image.Image:
    """
    Renders a deterministic chart on a 1920x1080 transparent canvas based on the payload.
    Types: donut, bar_hcompare, line_trend, big_number
    """
    img = Image.Image()._new(Image.new("RGBA", (1920, 1080), (0, 0, 0, 0)))
    draw = ImageDraw.Draw(img)
    
    # Always render the cream panel on the overlay to guarantee contrast and neat borders
    draw_cream_panel(draw)
    
def format_value_with_unit(val: float, unit: str) -> str:
    try:
        val = float(val)
    except (TypeError, ValueError):
        return str(val)
    if unit == "달러":
        return f"${val:,.2f}"
    elif unit == "원":
        return f"₩{val:,.0f}"
    elif unit == "%":
        return f"{val:.1f}%"
    elif unit == "pt":
        return f"{val:,.2f}pt"
    else:
        return f"{val:,.0f}{unit}"


def render_chart_to_overlay(payload: dict) -> Image.Image:
    """
    Renders a standard chart directly inside the 78% cream circular panel coordinate system.
    """
    img = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Always render the cream panel on the overlay to guarantee contrast and neat borders
    draw_cream_panel(draw)
    
    title = payload.get("title", "데이터 지표")
    as_of = payload.get("as_of", "2026-07-20")
    items = payload.get("items", [])
    unit = payload.get("unit", "")
    chart_type = payload.get("type", "big_number")
    
    # Colors
    text_color = (30, 30, 30)
    teal_color = (20, 80, 90)
    red_color = (220, 60, 60)   # Up / Positive in KR
    blue_color = (40, 100, 200)  # Down / Negative in KR
    
    # Title
    font_title = get_font(32)
    draw.text((PANEL_CENTER_X, PANEL_CENTER_Y - 300), title, fill=text_color, font=font_title, anchor="ms")
    
    # Stamp (as_of)
    font_stamp = get_font(18)
    stamp_text = f"기준일 {as_of} · 검증 데이터만 표시"
    draw.text((PANEL_CENTER_X, PANEL_CENTER_Y + 320), stamp_text, fill=(120, 120, 120), font=font_stamp, anchor="ms")
    
    if chart_type == "donut":
        # Donut Chart
        if items:
            total_val = sum(float(item.get("value", 0)) for item in items)
            if total_val == 0:
                total_val = 1
            
            # Draw slices
            left = PANEL_CENTER_X - 160
            top = PANEL_CENTER_Y - 180
            right = PANEL_CENTER_X + 160
            bottom = PANEL_CENTER_Y + 140
            
            colors_list = [
                (220, 80, 80), (80, 180, 120), (80, 120, 220), 
                (220, 180, 80), (160, 80, 220), (120, 120, 120)
            ]
            
            start_angle = -90
            for idx, item in enumerate(items[:5]):
                val = float(item.get("value", 0))
                pct = val / total_val
                sweep = pct * 360
                fill_color = colors_list[idx % len(colors_list)]
                
                # Draw arc slice
                draw.pieslice([left, top, right, bottom], start=start_angle, end=start_angle + sweep, fill=fill_color)
                start_angle += sweep
                
            # Inner circle to make it a donut
            draw.ellipse([PANEL_CENTER_X - 90, PANEL_CENTER_Y - 110, PANEL_CENTER_X + 90, PANEL_CENTER_Y + 70], fill=(245, 243, 235))
            
            # Legend
            font_legend = get_font(20)
            legend_start_y = PANEL_CENTER_Y + 180
            for idx, item in enumerate(items[:5]):
                val = float(item.get("value", 0))
                name = item.get("name", "")
                fill_color = colors_list[idx % len(colors_list)]
                
                leg_x = PANEL_CENTER_X - 180 + (idx % 3) * 130
                leg_y = legend_start_y + (idx // 3) * 35
                
                draw.rectangle([leg_x, leg_y + 4, leg_x + 15, leg_y + 19], fill=fill_color)
                val_text = format_value_with_unit(val, unit)
                draw.text((leg_x + 22, leg_y), f"{name} {val_text}", fill=text_color, font=font_legend)

    elif chart_type == "bar_hcompare":
        # Horizontal Bar Chart
        if items:
            max_val = max(float(item.get("value", 0)) for item in items) or 1
            start_y = PANEL_CENTER_Y - 150
            font_bar = get_font(22)
            
            for idx, item in enumerate(items[:4]):
                name = item.get("name", "")
                val = float(item.get("value", 0))
                bar_y = start_y + idx * 80
                
                # Label
                draw.text((PANEL_CENTER_X - 250, bar_y), name, fill=text_color, font=font_bar, anchor="lm")
                
                # Bar background
                draw.rectangle([PANEL_CENTER_X - 100, bar_y - 12, PANEL_CENTER_X + 150, bar_y + 12], fill=(220, 220, 220))
                
                # Filled bar
                bar_width = int(250 * (val / max_val))
                draw.rectangle([PANEL_CENTER_X - 100, bar_y - 12, PANEL_CENTER_X - 100 + bar_width, bar_y + 12], fill=teal_color)
                
                # Value label
                val_text = format_value_with_unit(val, unit)
                draw.text((PANEL_CENTER_X + 170, bar_y), val_text, fill=text_color, font=font_bar, anchor="lm")

    elif chart_type == "line_trend":
        # Simple Line Chart
        if items:
            vals = [float(item.get("value", 0)) for item in items]
            min_val = min(vals)
            max_val = max(vals)
            val_range = max_val - min_val or 1
            
            # Chart area bounds
            c_left = PANEL_CENTER_X - 200
            c_right = PANEL_CENTER_X + 200
            c_top = PANEL_CENTER_Y - 150
            c_bottom = PANEL_CENTER_Y + 150
            
            # Axes
            draw.line([c_left, c_bottom, c_right, c_bottom], fill=text_color, width=3)
            draw.line([c_left, c_top, c_left, c_bottom], fill=text_color, width=3)
            
            points = []
            num_pts = len(items)
            for idx, item in enumerate(items):
                val = float(item.get("value", 0))
                x = c_left + int((c_right - c_left) * idx / max(num_pts - 1, 1))
                y = c_bottom - int((c_bottom - c_top) * (val - min_val) / val_range)
                points.append((x, y))
            
            # Draw line
            for i in range(len(points) - 1):
                draw.line([points[i], points[i+1]], fill=red_color, width=4)
                
            # Labels for min/max
            font_axis = get_font(18)
            max_text = format_value_with_unit(max_val, unit)
            min_text = format_value_with_unit(min_val, unit)
            draw.text((c_left - 15, c_top), max_text, fill=text_color, font=font_axis, anchor="rm")
            draw.text((c_left - 15, c_bottom), min_text, fill=text_color, font=font_axis, anchor="rm")

    else:
        # big_number or fallback
        val_str = payload.get("value_str")
        if not val_str and items:
            val_str = format_value_with_unit(items[0].get('value', 0), unit)
        elif val_str:
            try:
                numeric_val = float(str(val_str).replace(",", "").replace("$", "").replace("₩", ""))
                val_str = format_value_with_unit(numeric_val, unit)
            except (ValueError, TypeError):
                pass
            
        change_direction = payload.get("change", "stable") # up, down, stable
        change_val = payload.get("change_value", "")
        
        font_big = get_font(84)
        draw.text((PANEL_CENTER_X, PANEL_CENTER_Y - 30), val_str or "0", fill=text_color, font=font_big, anchor="ms")
        
        # Change indicator
        if change_val:
            font_change = get_font(36)
            change_text = f"{change_val}"
            
            if change_direction == "up":
                # Red upward triangle + text
                draw.polygon([
                    (PANEL_CENTER_X - 100, PANEL_CENTER_Y + 80),
                    (PANEL_CENTER_X - 85, PANEL_CENTER_Y + 50),
                    (PANEL_CENTER_X - 70, PANEL_CENTER_Y + 80)
                ], fill=red_color)
                draw.text((PANEL_CENTER_X - 50, PANEL_CENTER_Y + 65), f"▲ {change_text}", fill=red_color, font=font_change, anchor="lm")
            elif change_direction == "down":
                # Blue downward triangle + text
                draw.polygon([
                    (PANEL_CENTER_X - 100, PANEL_CENTER_Y + 50),
                    (PANEL_CENTER_X - 85, PANEL_CENTER_Y + 80),
                    (PANEL_CENTER_X - 70, PANEL_CENTER_Y + 50)
                ], fill=blue_color)
                draw.text((PANEL_CENTER_X - 50, PANEL_CENTER_Y + 65), f"▼ {change_text}", fill=blue_color, font=font_change, anchor="lm")
            else:
                draw.text((PANEL_CENTER_X, PANEL_CENTER_Y + 65), change_text, fill=text_color, font=font_change, anchor="ms")
                
    return img

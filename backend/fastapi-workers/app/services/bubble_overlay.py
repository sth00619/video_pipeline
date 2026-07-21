import os
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "DejaVuSans.ttf"

def get_font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def draw_speech_bubble(image_path: str, bubble_text: str, output_path: str, character_side: str = "right"):
    """
    Renders a clean speech bubble with bubble_text and pastes it onto the image.
    Place it near the mascot character.
    """
    if not bubble_text:
        return
        
    try:
        img = Image.open(image_path).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        font = get_font(28)
        
        # Calculate text bounding box
        left, top, right, bottom = draw.textbbox((0, 0), bubble_text, font=font)
        text_w = right - left
        text_h = bottom - top
        
        # Bubble bounds
        padding_x = 24
        padding_y = 16
        box_w = text_w + padding_x * 2
        box_h = text_h + padding_y * 2
        
        # Center of bubble box
        if character_side == "left":
            bubble_x = 450
            bubble_y = 200
        else:
            bubble_x = 1000
            bubble_y = 200
        
        b_left = bubble_x - box_w // 2
        b_top = bubble_y - box_h // 2
        b_right = bubble_x + box_w // 2
        b_bottom = bubble_y + box_h // 2
        
        # Draw bubble background & black border (rounded rectangle)
        border_width = 4
        try:
            draw.rounded_rectangle([b_left, b_top, b_right, b_bottom], radius=16, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=border_width)
        except AttributeError:
            draw.rectangle([b_left, b_top, b_right, b_bottom], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=border_width)
            
        # Draw tail pointing to character head
        if character_side == "left":
            tail_points = [
                (b_left + 30, b_bottom - 2),
                (b_left - 15, b_bottom + 25),
                (b_left + 10, b_bottom - 2)
            ]
            draw.polygon(tail_points, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
            draw.line([b_left + 10, b_bottom - 2, b_left + 30, b_bottom - 2], fill=(255, 255, 255, 255), width=4)
        else:
            tail_points = [
                (b_right - 30, b_bottom - 2),
                (b_right + 15, b_bottom + 25),
                (b_right - 10, b_bottom - 2)
            ]
            draw.polygon(tail_points, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
            draw.line([b_right - 30, b_bottom - 2, b_right - 10, b_bottom - 2], fill=(255, 255, 255, 255), width=4)
        
        # Draw text
        draw.text((bubble_x, bubble_y - 2), bubble_text, fill=(30, 30, 30, 255), font=font, anchor="mm")
        
        # Composite overlay
        composited = Image.alpha_composite(img, overlay)
        composited.convert("RGB").save(output_path, "JPEG")
        logger.info(f"Successfully overlaid speech bubble '{bubble_text}' on {output_path}")
    except Exception as e:
        logger.error(f"Failed to overlay speech bubble: {e}")

"""Article evidence scene: paper frame, green quote highlight, red boxes."""
from __future__ import annotations

from dataclasses import dataclass

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.models.article_evidence import NormalizedBBox
from app.services.annotate import highlight_multiply, rect, underline
from app.services.article.frame_editor import ArticleFrame
from .emphasis_policy import BodyEmphasis, EmphasisPlan, TitleEmphasis
from .frame_spec import FRAME_16_9, SafeAreas, subtitle_zone


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/app/assets/fonts/NanumGothicBold.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ):
        try:
            return ImageFont.truetype(
                path,
                size,
                index=16 if path.endswith("AppleSDGothicNeo.ttc") else 0,
            )
        except OSError:
            continue
    return ImageFont.load_default()


@dataclass(frozen=True)
class ArticleSceneSpec:
    evidence_quote: str
    emphasis: EmphasisPlan
    key_phrase: str = ""
    channel_watermark_path: str | None = None


@dataclass
class ScenePNGs:
    plain: Image.Image
    emphasized: Image.Image
    audit: dict[str, str | bool] | None = None


class ArticleSceneRenderer:
    def render(self, frame: ArticleFrame, spec: ArticleSceneSpec, size: tuple[int, int] = FRAME_16_9) -> ScenePNGs:
        canvas = Image.new("RGB", size, "#FAFAFA")
        subtitle_top, _ = subtitle_zone(size[1])
        margin = int(size[0] * SafeAreas.CONTENT_MARGIN)
        headline_box = self._draw_headline(canvas, frame, margin)
        # Give the source body the central reading area.  Low-resolution DOM
        # text is re-typeset verbatim; scaling its pixels would remain blurry.
        body_top = headline_box[3] + 42
        if frame.retype_body:
            quote_boxes, key_boxes = self._draw_verbatim_quote(canvas, frame.quote, spec.key_phrase, body_top, margin, subtitle_top)
        else:
            quote_boxes, key_boxes = self._place_source_capture(
                canvas, frame, body_top, margin, subtitle_top
            )

        requested_body = spec.emphasis.body
        effective_body = requested_body
        downgraded = False
        if requested_body == BodyEmphasis.RECT and not key_boxes:
            # Never approximate a phrase rectangle with the first quote line.
            # The safe downgrade remains grounded in exact quote coordinates.
            effective_body = BodyEmphasis.HIGHLIGHT
            downgraded = True

        plain = canvas.copy()
        emphasized = canvas.copy()
        # Pass 1: multiply highlighter. Pass 2: opaque red editorial strokes.
        if effective_body in {BodyEmphasis.HIGHLIGHT, BodyEmphasis.HIGHLIGHT_UNDERLINE}:
            emphasized = highlight_multiply(emphasized, quote_boxes)
        if effective_body in {BodyEmphasis.UNDERLINE, BodyEmphasis.HIGHLIGHT_UNDERLINE}:
            underline(emphasized, quote_boxes, color="#E5241D", stroke_width=7, offset=4)
        elif effective_body == BodyEmphasis.RECT:
            for box in key_boxes:
                rect(emphasized, box, color="#E5241D", stroke_width=7)
        if spec.emphasis.title == TitleEmphasis.RECT_TEXT_EXTENT:
            rect(
                emphasized,
                NormalizedBBox(
                    x=headline_box[0] / size[0],
                    y=headline_box[1] / size[1],
                    width=(headline_box[2] - headline_box[0]) / size[0],
                    height=(headline_box[3] - headline_box[1]) / size[1],
                ),
                color="#E5241D",
                stroke_width=8,
            )
        self._credit(plain, frame)
        self._credit(emphasized, frame)
        self._watermark(plain, spec.channel_watermark_path)
        self._watermark(emphasized, spec.channel_watermark_path)
        return ScenePNGs(
            plain=plain,
            emphasized=emphasized,
            audit={
                "requested_body": requested_body.value,
                "effective_body": effective_body.value,
                "rect_downgraded": downgraded,
            },
        )

    @staticmethod
    def _place_source_capture(
        canvas: Image.Image,
        frame: ArticleFrame,
        body_top: int,
        margin: int,
        subtitle_top: int,
    ) -> tuple[list[NormalizedBBox], list[NormalizedBBox]]:
        """Zoom the real capture to reading width and map its DOM rectangles."""
        area_left = margin
        area_top = body_top
        area_width = canvas.width - margin * 2
        area_height = subtitle_top - body_top - 30
        if area_width <= 0 or area_height <= 0:
            raise ValueError("ARTICLE_OVEREXPOSED: no article reading area")
        scale = area_width / max(frame.width, 1)
        rendered_size = (
            max(1, round(frame.width * scale)),
            max(1, round(frame.height * scale)),
        )
        source = frame.image.resize(rendered_size, Image.Resampling.LANCZOS)
        union_center = sum(
            (box.y + box.height / 2) for box in frame.quote_bboxes
        ) / max(1, len(frame.quote_bboxes))
        crop_top = 0
        if source.height > area_height:
            focus_y = round(union_center * source.height)
            crop_top = min(
                max(0, focus_y - area_height // 2),
                source.height - area_height,
            )
            source = source.crop((0, crop_top, source.width, crop_top + area_height))
        paste_y = area_top + max(0, (area_height - source.height) // 2)
        canvas.paste(source.convert("RGB"), (area_left, paste_y))

        def map_boxes(boxes: list[NormalizedBBox]) -> list[NormalizedBBox]:
            mapped: list[NormalizedBBox] = []
            for box in boxes:
                left = area_left + box.x * rendered_size[0]
                top = paste_y + box.y * rendered_size[1] - crop_top
                width = box.width * rendered_size[0]
                height = box.height * rendered_size[1]
                clipped_left = max(0.0, left)
                clipped_right = min(float(canvas.width), left + width)
                clipped_top = max(area_top, top)
                clipped_bottom = min(subtitle_top - 2, top + height)
                if clipped_bottom <= clipped_top or clipped_right <= clipped_left:
                    continue
                mapped.append(NormalizedBBox(
                    x=clipped_left / canvas.width,
                    y=clipped_top / canvas.height,
                    width=(clipped_right - clipped_left) / canvas.width,
                    height=(clipped_bottom - clipped_top) / canvas.height,
                ))
            return mapped

        mapped_quotes = map_boxes(frame.quote_bboxes)
        if not mapped_quotes:
            raise ValueError("ARTICLE_QUOTE_OUTSIDE_FRAME")
        return mapped_quotes, map_boxes(frame.key_phrase_bboxes)

    @staticmethod
    def _draw_verbatim_quote(image: Image.Image, quote: str, key_phrase: str, top: int, margin: int, subtitle_top: int) -> tuple[list[NormalizedBBox], list[NormalizedBBox]]:
        """Re-typeset only the captured quote; no summary or added claim."""
        draw = ImageDraw.Draw(image)
        font = _font(66)
        max_width = image.width - margin * 2 - 80
        words = quote.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            proposal = word if not current else f"{current} {word}"
            if current and draw.textlength(proposal, font=font) > max_width:
                lines.append(current)
                current = word
            else:
                current = proposal
        if current:
            lines.append(current)
        y = top + 46
        boxes: list[NormalizedBBox] = []
        key_boxes: list[NormalizedBBox] = []
        draw.text((margin + 20, top), "기사 원문 발췌", font=_font(28), fill=(100, 100, 100))
        for line in lines[:2]:
            draw.text((margin + 20, y), line, font=font, fill=(15, 15, 15))
            box = draw.textbbox((margin + 20, y), line, font=font)
            boxes.append(NormalizedBBox(x=box[0] / image.width, y=box[1] / image.height, width=(box[2] - box[0]) / image.width, height=(box[3] - box[1]) / image.height))
            if key_phrase and key_phrase in line:
                start = line.index(key_phrase)
                left = margin + 20 + draw.textlength(line[:start], font=font)
                right = left + draw.textlength(key_phrase, font=font)
                key_boxes.append(NormalizedBBox(x=left / image.width, y=box[1] / image.height, width=(right - left) / image.width, height=(box[3] - box[1]) / image.height))
            y += int(font.size * 1.38)
        if y > subtitle_top:
            raise ValueError("ARTICLE_OVEREXPOSED: quote intrudes into subtitle safe area")
        return boxes, key_boxes

    @staticmethod
    def _draw_headline(image: Image.Image, frame: ArticleFrame, margin: int) -> tuple[int, int, int, int]:
        draw = ImageDraw.Draw(image)
        title = frame.source_title
        max_width = image.width - margin * 2 - 32
        # Keep a news title within two deliberate lines.  A smaller headline
        # is preferable to a dangling single Hangul syllable below the box.
        lines: list[str] = []
        font = _font(66)
        # Choose a balanced two-line split, rather than accepting a technically
        # valid first-line-plus-one-syllable orphan.
        for size in range(66, 35, -2):
            font = _font(size)
            options = []
            # Prefer a Korean word boundary.  The character-level fallback is
            # retained only for a title with no spaces at all.
            word_cuts = [cut for cut in range(4, len(title) - 3) if title[cut - 1].isspace() or title[cut].isspace()]
            for cut in word_cuts or range(4, len(title) - 3):
                first, second = title[:cut].rstrip(), title[cut:].lstrip()
                first_w, second_w = draw.textlength(first, font=font), draw.textlength(second, font=font)
                if first_w <= max_width and second_w <= max_width:
                    options.append((abs(first_w - second_w), first, second))
            if options:
                _, first, second = min(options, key=lambda value: value[0])
                lines = [first, second]
                break
        if not lines:
            midpoint = max(1, len(title) // 2)
            lines = [title[:midpoint], title[midpoint:]]
        top = 100
        text_boxes = []
        for line in lines:
            draw.text((margin + 16, top), line, font=font, fill=(18, 18, 18))
            text_boxes.append(draw.textbbox((margin + 16, top), line, font=font))
            top += int(font.size * 1.25)
        # Keep the editorial frame tight to the actual rendered glyph range.
        # The accepted visual contract allows at most 14 px breathing room.
        left = min(box[0] for box in text_boxes) - 12
        right = max(box[2] for box in text_boxes) + 12
        upper = min(box[1] for box in text_boxes) - 12
        lower = max(box[3] for box in text_boxes) + 12
        return left, upper, right, lower

    @staticmethod
    def _credit(image: Image.Image, frame: ArticleFrame) -> None:
        date = (frame.published_at or "")[:10].replace("-", ".")
        label = f"출처: {frame.publisher}" + (f" · {date}" if date else "")
        d = ImageDraw.Draw(image)
        font = _font(24)
        width = max(220, int(d.textlength(label, font=font)) + 36)
        d.rounded_rectangle((42, 30, 42 + width, 72), radius=12, fill=(255, 255, 255))
        d.text((60, 38), label, font=font, fill=(30, 30, 30))

    @staticmethod
    def _watermark(image: Image.Image, path: str | None) -> None:
        if not path or not Path(path).is_file():
            return
        with Image.open(path) as loaded:
            mark = loaded.convert("RGBA")
        mark.thumbnail(
            (int(image.width * .18), int(image.height * .10)),
            Image.Resampling.LANCZOS,
        )
        layer = image.convert("RGBA")
        layer.alpha_composite(
            mark,
            (image.width - mark.width - 42, 26),
        )
        image.paste(layer.convert("RGB"))

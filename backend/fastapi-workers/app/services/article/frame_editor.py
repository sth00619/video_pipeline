"""Turn a raw DOM crop into a compact, attribution-ready article frame.

The editor never guesses text geometry: every emphasis coordinate comes from
the Range rectangles persisted by ``EvidenceCaptureService``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PIL import Image

from app.models.article_evidence import ArticleCapture, NormalizedBBox


class ArticleOverexposedError(ValueError):
    code = "ARTICLE_OVEREXPOSED"


@dataclass
class ArticleFrame:
    image: Image.Image
    quote_bboxes: list[NormalizedBBox]
    key_phrase_bboxes: list[NormalizedBBox]
    title_text_bbox: NormalizedBBox
    source_title: str
    publisher: str
    published_at: str | None
    source_url: str
    quote: str
    retype_body: bool = False
    capture_mode: str = "dom"

    @property
    def width(self) -> int:
        return self.image.width

    @property
    def height(self) -> int:
        return self.image.height

    def scaled(self, scale: float) -> "ArticleFrame":
        scale = min(1.0, max(.05, float(scale)))
        resized = self.image.resize((max(1, round(self.width * scale)), max(1, round(self.height * scale))), Image.Resampling.LANCZOS)
        return ArticleFrame(
            resized, self.quote_bboxes, self.key_phrase_bboxes, self.title_text_bbox, self.source_title,
            self.publisher, self.published_at, self.source_url, self.quote,
            self.retype_body, self.capture_mode,
        )


class ArticleFrameEditor:
    """Crop around no more than two quoted sentences and retain their boxes."""

    def from_capture(self, capture: ArticleCapture, *, include_title: bool = True, max_visible_sentences: int = 4) -> ArticleFrame:
        # Decimal points in figures such as 394.50 or 5.85% are not sentence
        # boundaries. Only punctuation outside numeric tokens counts here.
        sentence_parts = [
            part for part in re.split(r"(?<!\d)[.!?]+(?!\d)", capture.quote)
            if part.strip()
        ]
        if len(sentence_parts) > 2:
            raise ArticleOverexposedError("ARTICLE_OVEREXPOSED: quote exceeds two sentences")
        if not capture.local_path or not Path(capture.local_path).is_file():
            raise FileNotFoundError("article capture image is unavailable")
        with Image.open(capture.local_path) as loaded:
            image = loaded.convert("RGB")
        if not capture.quote_bboxes:
            raise ValueError("article capture has no DOM quote_bboxes")
        # EvidenceCaptureService already creates a reviewed article-container
        # crop. Keep its full vertical context, but trim side whitespace around
        # the DOM quote so the real article glyphs read at broadcast size.
        min_x = min(box.x for box in capture.quote_bboxes)
        max_x = max(box.x + box.width for box in capture.quote_bboxes)
        left = max(0.0, min_x - .06)
        right = min(1.0, max_x + .06)
        if right - left < .75:
            expand = (.75 - (right - left)) / 2
            left, right = max(0.0, left - expand), min(1.0, right + expand)
        crop_left, crop_right = round(left * image.width), round(right * image.width)
        image = image.crop((crop_left, 0, crop_right, image.height))
        span_x = right - left
        boxes = [NormalizedBBox(
            x=max(0.0, (box.x - left) / span_x),
            y=box.y,
            width=min(1.0, box.width / span_x),
            height=box.height,
        ) for box in capture.quote_bboxes]
        key_boxes = [NormalizedBBox(
            x=max(0.0, (box.x - left) / span_x),
            y=box.y,
            width=min(1.0, box.width / span_x),
            height=box.height,
        ) for box in capture.key_phrase_bboxes]
        return ArticleFrame(
            image=image,
            quote_bboxes=boxes,
            key_phrase_bboxes=key_boxes,
            # A separate title panel owns its geometry; keeping a neutral box
            # here prevents a source-image caption from being highlighted.
            title_text_bbox=capture.title_text_bbox or NormalizedBBox(x=.02, y=.02, width=.96, height=.12),
            source_title=capture.source_title.removesuffix(" | 연합뉴스").strip(),
            publisher=capture.publisher,
            published_at=capture.published_at,
            source_url=capture.source_url,
            quote=capture.quote,
            # DOM capture is authoritative and must remain visibly recognisable
            # as the source article. Retyping is reserved for user/PDF evidence
            # that is genuinely too small to read.
            retype_body=(
                capture.capture_mode != "dom"
                and max(box.height for box in capture.quote_bboxes) * image.height < 64
            ),
            capture_mode=capture.capture_mode,
        )

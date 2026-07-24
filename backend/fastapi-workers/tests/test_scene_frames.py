from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.models.article_evidence import ArticleCapture, NormalizedBBox
from app.services.annotate import highlight_multiply
from app.services.article.frame_editor import ArticleFrameEditor
from app.services.scene_frames.article_scene import ArticleSceneRenderer, ArticleSceneSpec
from app.services.scene_frames.emphasis_policy import BodyEmphasis, EmphasisPlan
from app.services.scene_frames.frame_spec import subtitle_zone
from app.services.scene_frames.infographic.schemas import TimelineCardSpec
from app.services.scene_frames.infographic.timeline import CardOverflowError, InfographicRenderer


def test_multiply_highlight_preserves_black_text():
    base = Image.new("RGB", (120, 60), "white")
    ImageDraw.Draw(base).rectangle((20, 20, 70, 35), fill="black")
    result = highlight_multiply(base, [NormalizedBBox(x=.05, y=.2, width=.85, height=.5)])
    assert result.getpixel((30, 25)) == (0, 0, 0)
    assert result.getpixel((10, 30))[1] > result.getpixel((10, 30))[0]


def test_article_scene_reserves_subtitle_area(tmp_path):
    source = tmp_path / "article.png"
    Image.new("RGB", (1000, 700), "white").save(source)
    capture = ArticleCapture(source_url="https://www.yna.co.kr/x", source_title="기사 제목", publisher="연합뉴스", captured_at="2026-07-23T00:00:00Z", capture_mode="dom", quote="한국어 인용문입니다.", image_sha256="a" * 64, target_bbox=NormalizedBBox(x=.1, y=.4, width=.6, height=.1), quote_bboxes=[NormalizedBBox(x=.1, y=.4, width=.6, height=.1)], local_path=str(source))
    frame = ArticleFrameEditor().from_capture(capture)
    assert frame.capture_mode == "dom"
    assert frame.retype_body is False
    assert frame.image.height == 700
    assert frame.image.width < 1000
    rendered = ArticleSceneRenderer().render(
        frame,
        ArticleSceneSpec(
            evidence_quote=capture.quote,
            emphasis=EmphasisPlan(body=BodyEmphasis.HIGHLIGHT_UNDERLINE),
        ),
    )
    assert rendered.emphasized.size == (1920, 1080)
    # The reserved lower zone remains the paper background, not article pixels.
    assert rendered.emphasized.getpixel((960, subtitle_zone(1080)[0] + 20)) == (250, 250, 250)


def test_decimal_points_do_not_count_as_extra_article_sentences(tmp_path):
    source = tmp_path / "decimal-article.png"
    Image.new("RGB", (1000, 700), "white").save(source)
    quote_box = NormalizedBBox(x=.1, y=.4, width=.75, height=.1)
    capture = ArticleCapture(
        source_url="https://www.yna.co.kr/x",
        source_title="수치 기사",
        publisher="연합뉴스",
        captured_at="2026-07-23T00:00:00Z",
        capture_mode="dom",
        quote="코스피는 394.50포인트(5.85%) 상승한 7,142.45다.",
        image_sha256="c" * 64,
        target_bbox=quote_box,
        quote_bboxes=[quote_box],
        local_path=str(source),
    )
    assert ArticleFrameEditor().from_capture(capture).quote == capture.quote


def _article_frame(tmp_path, *, with_key: bool):
    source = tmp_path / f"article-{'key' if with_key else 'plain'}.png"
    Image.new("RGB", (1000, 700), "white").save(source)
    quote_box = NormalizedBBox(x=.12, y=.42, width=.64, height=.12)
    capture = ArticleCapture(
        source_url="https://www.yna.co.kr/x",
        source_title="반도체 시장 핵심 제목",
        publisher="연합뉴스",
        captured_at="2026-07-23T00:00:00Z",
        capture_mode="dom",
        quote="반도체 지수가 12.5% 상승했습니다.",
        key_phrase="12.5% 상승" if with_key else None,
        image_sha256="b" * 64,
        target_bbox=quote_box,
        quote_bboxes=[quote_box],
        key_phrase_bboxes=[
            NormalizedBBox(x=.40, y=.42, width=.18, height=.12)
        ] if with_key else [],
        local_path=str(source),
    )
    return ArticleFrameEditor().from_capture(capture)


def _body_color_counts(image):
    red = green = 0
    for r, g, b in image.crop((0, 300, image.width, 900)).getdata():
        if r > 220 and g < 70 and b < 70:
            red += 1
        if g > r * 1.35 and g > b * 1.35 and g > 120:
            green += 1
    return red, green


def test_article_body_underline_does_not_add_highlight(tmp_path):
    frame = _article_frame(tmp_path, with_key=False)
    rendered = ArticleSceneRenderer().render(
        frame,
        ArticleSceneSpec(
            evidence_quote=frame.quote,
            emphasis=EmphasisPlan(body=BodyEmphasis.UNDERLINE),
        ),
    )
    red, green = _body_color_counts(rendered.emphasized)
    assert red > 0
    assert green == 0


def test_highlight_then_underline_keeps_opaque_red(tmp_path):
    frame = _article_frame(tmp_path, with_key=False)
    rendered = ArticleSceneRenderer().render(
        frame,
        ArticleSceneSpec(
            evidence_quote=frame.quote,
            emphasis=EmphasisPlan(body=BodyEmphasis.HIGHLIGHT_UNDERLINE),
        ),
    )
    red, green = _body_color_counts(rendered.emphasized)
    assert red > 0
    assert green > 0
    # The opaque second pass must retain exact renderer red, not brown multiply.
    assert (229, 36, 29) in set(rendered.emphasized.crop((0, 300, 1920, 900)).getdata())


def test_missing_key_bbox_downgrades_rect_to_highlight(tmp_path):
    frame = _article_frame(tmp_path, with_key=False)
    rendered = ArticleSceneRenderer().render(
        frame,
        ArticleSceneSpec(
            evidence_quote=frame.quote,
            emphasis=EmphasisPlan(body=BodyEmphasis.RECT),
        ),
    )
    red, green = _body_color_counts(rendered.emphasized)
    assert red == 0
    assert green > 0
    assert rendered.audit == {
        "requested_body": "rect",
        "effective_body": "highlight",
        "rect_downgraded": True,
    }


def test_rect_uses_only_key_phrase_geometry(tmp_path):
    frame = _article_frame(tmp_path, with_key=True)
    rendered = ArticleSceneRenderer().render(
        frame,
        ArticleSceneSpec(
            evidence_quote=frame.quote,
            emphasis=EmphasisPlan(body=BodyEmphasis.RECT),
            key_phrase="12.5% 상승",
        ),
    )
    red, green = _body_color_counts(rendered.emphasized)
    assert red > 0
    assert green == 0
    assert rendered.audit["rect_downgraded"] is False


def test_title_rect_tracks_actual_text_extent_with_tight_padding(tmp_path):
    frame = _article_frame(tmp_path, with_key=False)
    probe = Image.new("RGB", (1920, 1080), "#FAFAFA")
    expected = ArticleSceneRenderer()._draw_headline(probe, frame, int(1920 * .045))
    rendered = ArticleSceneRenderer().render(
        frame,
        ArticleSceneSpec(
            evidence_quote=frame.quote,
            emphasis=EmphasisPlan(body=BodyEmphasis.UNDERLINE),
        ),
    ).emphasized
    red_pixels = [
        (x, y)
        for y in range(75, 300)
        for x in range(0, rendered.width)
        if (lambda rgb: rgb[0] > 220 and rgb[1] < 70 and rgb[2] < 70)(rendered.getpixel((x, y)))
    ]
    assert red_pixels
    actual = (
        min(x for x, _ in red_pixels),
        min(y for _, y in red_pixels),
        max(x for x, _ in red_pixels),
        max(y for _, y in red_pixels),
    )
    assert all(abs(left - right) <= 2 for left, right in zip(actual, expected))


def test_timeline_renders_box_and_rejects_overflow():
    card = TimelineCardSpec.model_validate({"entries": [{"date_label": "2월 28일", "lines": ["미국·이스라엘", "이란 선제 타격"], "source_refs": ["facts[0]"], "emphasis_line_range": [0, 1]}, {"date_label": "3월 2일", "lines": ["후르무즈 봉쇄"], "source_refs": ["facts[1]"]}]})
    rendered = InfographicRenderer().timeline(card, [{}, {}])
    assert rendered.plain.size == (1920, 1080)
    assert rendered.plain.tobytes() != rendered.emphasized.tobytes()
    bad = {"entries": [{"date_label": str(i), "lines": ["한 줄" for _ in range(5)], "source_refs": ["facts[0]"]} for i in range(4)]}
    with pytest.raises(CardOverflowError):
        InfographicRenderer().timeline(TimelineCardSpec.model_validate(bad), [{}])

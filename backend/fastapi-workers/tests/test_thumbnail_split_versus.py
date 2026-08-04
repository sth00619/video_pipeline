"""split_versus 썸네일 preset: comparison_mode 선택 배선과 좌우 대비 렌더 검증."""
from pathlib import Path

from PIL import Image, ImageChops

from app.services.thumbnail.v2.compose import ThumbnailV2Composer
from app.services.thumbnail.v2.templates.base import AssetBundle, TEMPLATE_REGISTRY
from app.services.thumbnail.v2.templates.chart_warning import ChartWarningTemplate
from app.services.thumbnail.v2.templates.split_versus import SplitVersusTemplate
from app.workers.script_worker import _is_comparison_narrative


def _scene(tmp_path: Path) -> dict:
    path = tmp_path / "chart.png"
    Image.new("RGB", (1920, 1080), (25, 70, 95)).save(path)
    return {
        "scene_id": "s1", "image_path": str(path), "clean_plate_path": str(path),
        "scene_kind": "chart", "used_in_final_video": True,
        "asset_layout_metadata": {"clean_plate_path": str(path), "duplicate_character_count": 0},
    }


def _brief(**overrides) -> dict:
    base = {
        "template": "chart_warning",
        "headline": [{"text": "반도체 주가", "tone": "white"}, {"text": "지금 확인할 핵심", "tone": "yellow"}],
        "primary_subject": {"kind": "chart", "asset_id": "chart", "source_ref": "facts[0]"},
        "secondary_subject": {"allowed": False},
    }
    base.update(overrides)
    return base


def test_split_versus_is_registered():
    assert TEMPLATE_REGISTRY["split_versus"] is SplitVersusTemplate


def test_comparison_mode_selects_split_versus_for_every_chart_led_variant(tmp_path):
    scene = _scene(tmp_path)
    result = ThumbnailV2Composer().render(
        output_path=str(tmp_path / "thumb.png"),
        format_name="longform",
        candidates=[scene],
        brief=_brief(comparison_mode=True),
    )
    assert result["variants"]
    for variant in result["variants"]:
        assert variant["template_id"] == "split_versus"


def test_without_comparison_mode_still_uses_chart_warning(tmp_path):
    scene = _scene(tmp_path)
    result = ThumbnailV2Composer().render(
        output_path=str(tmp_path / "thumb.png"),
        format_name="longform",
        candidates=[scene],
        brief=_brief(comparison_mode=False),
    )
    for variant in result["variants"]:
        assert variant["template_id"] == "chart_warning"


def test_split_versus_background_tints_left_red_and_right_gold(tmp_path):
    scene = _scene(tmp_path)
    bundle = AssetBundle(scene, [scene], [], None, None, None)
    canvas = SplitVersusTemplate().collage_background(bundle, (1920, 1080))
    left = canvas.convert("RGB").getpixel((10, 10))
    right = canvas.convert("RGB").getpixel((1910, 10))
    # 좌측은 빨강 성분이, 우측은 금색(빨강+초록, 파랑 낮음) 성분이 두드러져야 한다.
    assert left[0] > left[2]
    assert right[0] > right[2] and right[1] > right[2]


def test_split_versus_changes_pixels_relative_to_plain_chart_warning(tmp_path):
    scene = _scene(tmp_path)
    bundle = AssetBundle(scene, [scene], [], None, None, None)
    plain = ChartWarningTemplate().collage_background(bundle, (1920, 1080)).convert("RGB")
    split = SplitVersusTemplate().collage_background(bundle, (1920, 1080)).convert("RGB")
    assert ImageChops.difference(plain, split).getbbox() is not None


def test_is_comparison_narrative_detects_versus_markers():
    assert _is_comparison_narrative("중국 vs 한국 관세", [])
    assert _is_comparison_narrative("", [{"content": "이번 정책은 지난달 대비 어떻게 다른가"}])
    assert not _is_comparison_narrative("코스피 마감 시황", [{"content": "오늘 코스피는 상승 마감했습니다."}])

from __future__ import annotations

from PIL import Image, ImageDraw

from .base import AssetBundle, register
from .chart_warning import ChartWarningTemplate


@register
class SplitVersusTemplate(ChartWarningTemplate):
    """좌(위험/빨강) vs 우(합의/금색) 대비 구도.

    경제사냥꾼 채널 대표 썸네일(``ref_04``, CHINA vs KOREA)이 쓰는 좌우
    대비 톤을 재현한다. 인물/마스코트 배치, 자막 패널, 배지, 워터마크는
    이미 QA 기준(subject_area·copy_fill·overlaps 등)을 통과하는
    ``ChartWarningTemplate``의 지오메트리를 그대로 상속한다. 이 템플릿이
    다르게 그리는 부분은 배경의 좌우 컬러 그레이딩뿐이라, 새 템플릿을
    추가해도 검증된 레이아웃 계약을 다시 조정할 필요가 없다.
    """

    template_id = "split_versus"

    _DANGER_TINT = (176, 24, 20, 92)  # 좌측: 위험/하락/관세 톤(빨강)
    _SAFE_TINT = (214, 158, 20, 92)  # 우측: 합의/보호/성공 톤(금색)
    _SEAM_COLOR = (255, 226, 130, 130)

    def collage_background(self, assets: AssetBundle, size: tuple[int, int]) -> Image.Image:
        canvas = super().collage_background(assets, size)
        width, height = canvas.size
        split = round(width * .5)
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw_ctx = ImageDraw.Draw(overlay)
        draw_ctx.rectangle((0, 0, split, height), fill=self._DANGER_TINT)
        draw_ctx.rectangle((split, 0, width, height), fill=self._SAFE_TINT)
        # 중앙 경계선을 살짝 밝혀 두 톤이 뭉개지지 않고 무대 스포트라이트처럼
        # 분리되게 한다(07 문서 §8 "좌우 스포트라이트" 구도 관찰과 일치).
        seam_width = max(3, round(width * .004))
        draw_ctx.rectangle(
            (split - seam_width, 0, split + seam_width, height),
            fill=self._SEAM_COLOR,
        )
        canvas.alpha_composite(overlay)
        return canvas

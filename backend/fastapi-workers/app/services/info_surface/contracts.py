"""Contracts shared by scene planning, detection, compositing, and provenance."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .hero_stat import HeroStatPlan, hero_stat_from_chart


# These are deliberately explicit inputs to the final-image cache key.  A
# rendering change must never let a previously composited still masquerade as
# the current result during job resume.
INFO_SURFACE_PLAN_VERSION = "3.0"
INFO_SURFACE_DETECTOR_VERSION = "2.2"
INFO_SURFACE_COMPOSITOR_VERSION = "3.0"
INFO_SURFACE_CHART_STYLE_VERSION = "3.0"
INFO_SURFACE_PHASE_B_VERSION = "1.0"
# Chart ink is rendered at 1.7x then warped down.  Below this physical prop
# size its numerical x-height cannot meet the 1080p readability contract.
MIN_DIEGETIC_CHART_SHORT_SIDE_PX = 360.0


SurfaceGeometry = Literal["planar_quad", "irregular_mask", "curved_surface"]
RenderMode = Literal["DIEGETIC_WARP", "GRAPHIC_LAYER", "BAKED_LABEL", "DATA_CUTAWAY", "METRIC_SUMMARY"]
InfoRole = Literal["metric", "chart", "label", "speech", "burst", "reaction", "title", "subtitle", "callout"]


class SurfaceContract(BaseModel):
    surface_kind: str
    geometry: SurfaceGeometry = "planar_quad"
    marker_rgb: tuple[int, int, int] | None = None
    marker_delta_e_max: float = Field(default=12.0, gt=0, le=80)
    marker_scene_delta_e_min: float = Field(default=20.0, gt=0, le=100)
    border_rgb: tuple[int, int, int] | None = None
    border_delta_e_max: float = Field(default=18.0, gt=0, le=100)
    area_ratio_min: float = Field(default=.06, gt=0, lt=1)
    area_ratio_max: float = Field(default=.30, gt=0, le=1)
    preferred_side: Literal["left", "right", "center"] = "right"
    preferred_region: dict[str, float] = Field(default_factory=lambda: {"x": .50, "y": .08, "width": .42, "height": .58})
    candidate_iou_min: float = Field(default=.30, ge=0, le=1)
    tilt_hint: str = "slightly tilted like a real prop"
    inset_ratio: float = Field(default=.06, ge=.02, le=.18)

    @model_validator(mode="after")
    def validate_marker(self):
        if self.geometry == "planar_quad" and self.marker_rgb is None:
            raise ValueError("planar_quad requires marker_rgb")
        if self.area_ratio_min >= self.area_ratio_max:
            raise ValueError("area_ratio_min must be smaller than area_ratio_max")
        return self


class InfoItem(BaseModel):
    item_id: str
    role: InfoRole
    text: str | None = None
    chart_payload_ref: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    max_chars: int = Field(default=20, ge=1, le=48)
    requested_mode: RenderMode | None = None
    resolved_mode: RenderMode | None = None
    fallback_reason: str | None = None
    fallback_cost_krw: int = 0


class InfoSurfacePlan(BaseModel):
    scene_id: str
    render_mode: RenderMode
    surface: SurfaceContract | None = None
    items: list[InfoItem] = Field(default_factory=list)
    fallback_chain: list[str] = Field(default_factory=list)
    detection: dict | None = None
    timeline_mode: Literal["original", "one_to_one_replace"] = "original"
    chart_semantics_reduced: bool = False
    replacement_of_scene_id: str | None = None
    source_image_path: str | None = None
    final_image_path: str | None = None
    hero_stat: HeroStatPlan | None = None
    chart_render_metadata: dict | None = None
    phase_b: dict | None = None
    # v4는 템플릿 장면의 빈 보드에 서사 다이어그램을 합성한다.
    template_id: str | None = None
    diagram_kind: str | None = None
    # Never overwrite a failed detector/fallback attempt with a later retry.
    # The worker appends a compact audit event each time it finalizes a scene.
    render_attempts: list[dict] = Field(default_factory=list)


def plan_from_scene(scene: dict) -> InfoSurfacePlan | None:
    """Create the P0 plan without ever deriving facts from narration text."""
    chart = scene.get("market_chart")
    direction = scene.get("art_direction") or {}
    raw_contract = direction.get("surface_contract")
    if not isinstance(chart, dict) or chart.get("verified") is not True:
        return None
    # The plan owns a precomputed hero hierarchy. A bad indexed payload is
    # rejected before a renderer can present it as an absolute market quote.
    hero = hero_stat_from_chart(chart)
    # 템플릿이 있는 경우에만 v4가 v3 위에 올라간다. 비교/추세는
    # select_template()이 None을 반환하므로 기존 HeroStat 경로를 유지한다.
    template = None
    try:
        from .info_scene_templates import select_template
        template = select_template(scene, scene.get("proposed_template_id"))
    except (ImportError, ValueError):
        template = None
    if template and template.diagram_kind not in {"none", "hero_stat"}:
        # v4 보드의 실제 생성 계약: 칠판만 어둡고, 금고 패널·설계도·날씨
        # 스크린은 그림을 넣기 위한 밝은 무문자 매트 표면이다.
        marker = (43, 72, 57) if template.surface_kind == "chalkboard" else (246, 244, 210)
        raw_contract = {
            "surface_kind": template.surface_kind, "geometry": "planar_quad", "marker_rgb": marker,
            "border_rgb": (7, 26, 58), "preferred_side": template.board_side,
            "preferred_region": {"x": .05 if template.board_side == "left" else .53, "y": .08, "width": .42, "height": .70},
            "area_ratio_min": .10, "area_ratio_max": .55,
        }
    try:
        contract = SurfaceContract.model_validate(raw_contract) if isinstance(raw_contract, dict) else None
    except ValueError:
        # Older jobs can contain a partial surface payload.  It must take the
        # same safe fallback as an absent contract, not skip verified data.
        contract = None
    role: InfoRole = "chart" if str(chart.get("visual_kind") or "") not in {"change_arrow"} else "metric"
    # P0 only owns planar warps.  Treat every other geometry as a typed
    # fallback, rather than pretending a rectangular chart belongs on it.
    if contract is None or contract.geometry != "planar_quad":
        mode: RenderMode = "DATA_CUTAWAY" if role == "chart" else "GRAPHIC_LAYER"
        reason = "surface_contract_missing" if contract is None else f"{contract.geometry}_p0"
        return InfoSurfacePlan(
            scene_id=str(scene.get("scene_id") or scene.get("index") or "scene"), render_mode=mode,
            items=[InfoItem(item_id="verified_data", role=role, chart_payload_ref="market_chart", source_refs=[str(chart.get("source_ref") or chart.get("source") or "")], requested_mode="DIEGETIC_WARP", resolved_mode=mode, fallback_reason=reason)],
            fallback_chain=[reason], chart_semantics_reduced=mode == "METRIC_SUMMARY",
            timeline_mode="one_to_one_replace" if mode == "DATA_CUTAWAY" else "original",
            hero_stat=hero,
        )
    return InfoSurfacePlan(
        scene_id=str(scene.get("scene_id") or scene.get("index") or "scene"), render_mode="DIEGETIC_WARP", surface=contract,
        items=[InfoItem(item_id="verified_data", role=role, chart_payload_ref="market_chart", source_refs=[str(chart.get("source_ref") or chart.get("source") or "")], requested_mode="DIEGETIC_WARP", resolved_mode="DIEGETIC_WARP")], hero_stat=hero,
        template_id=template.template_id if template else None,
        diagram_kind=template.diagram_kind if template else None,
    )

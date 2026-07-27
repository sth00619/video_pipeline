"""v4 정보 장면 템플릿: 검증된 주장 구조로 장면 연출을 결정한다."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator

ClaimShape = Literal["stages", "structure", "external_rate", "causal_chain", "comparison", "trend_hero", "alert"]


class CharacterContract(BaseModel):
    costume: str
    pose_asset: str
    gaze: Literal["board", "camera"] = "board"
    hand: Literal["points_board", "presents_board", "none"] = "points_board"
    side: Literal["left", "right", "center"]


class LabelSlot(BaseModel):
    slot_id: str
    role: Literal["stage", "callout", "cloud_value", "node", "title", "meaning"]
    max_chars: int = Field(default=8, ge=1, le=24)
    x: float; y: float; w: float; h: float


class InfoSceneTemplate(BaseModel):
    template_id: str
    claim_shape: ClaimShape
    diagram_kind: Literal["stage_locks", "blueprint_callouts", "map_clouds", "flow_chalk", "hero_stat", "none"]
    character: CharacterContract
    surface_kind: str
    board_side: Literal["left", "right", "center"]
    min_items: int = 1
    max_items: int = 4
    label_slots: list[LabelSlot] = Field(default_factory=list)
    prompt_en: str
    allow_regen_on_quad_fail: bool = True

    @model_validator(mode="after")
    def _reject_same_side(self):
        if self.board_side in {"left", "right"} and self.board_side == self.character.side:
            raise ValueError("보드와 캐릭터는 같은 쪽에 둘 수 없습니다")
        return self


_BLANK = "The board interior is a single blank matte marker surface with a dark physical border. ABSOLUTELY NO text, letters, numbers, charts, icons or symbols anywhere on it."
REGISTRY = {
    "vault_stages": InfoSceneTemplate(template_id="vault_stages", claim_shape="stages", diagram_kind="stage_locks", character=CharacterContract(costume="knight armor with channel-color cape and shield", pose_asset="present_right", side="left"), surface_kind="monitor", board_side="right", min_items=2, max_items=4, prompt_en="A sturdy cartoon bank vault room, {setting_detail}, with a huge vault door on the right and a large flat glowing status panel mounted on it. " + _BLANK),
    "blueprint_board": InfoSceneTemplate(template_id="blueprint_board", claim_shape="structure", diagram_kind="blueprint_callouts", character=CharacterContract(costume="yellow hard hat, tool belt, drafting compass", pose_asset="present_left", side="right"), surface_kind="desk_report", board_side="left", min_items=2, max_items=3, prompt_en="A bright architect studio at sunrise, {setting_detail}, with a large wooden drafting board tilted on a stand on the left. " + _BLANK),
    "weather_map_studio": InfoSceneTemplate(template_id="weather_map_studio", claim_shape="external_rate", diagram_kind="map_clouds", character=CharacterContract(costume="broadcast blazer with headset microphone", pose_asset="point_left_up", side="right"), surface_kind="monitor", board_side="left", min_items=1, max_items=3, prompt_en="A cartoon TV weather studio, {setting_detail}, with a huge curved wall screen on the left showing a single flat pale-blue matte field with no coastline, labels, text or symbols. "+_BLANK),
    "chalk_logic_class": InfoSceneTemplate(template_id="chalk_logic_class", claim_shape="causal_chain", diagram_kind="flow_chalk", character=CharacterContract(costume="graduation cap and tweed jacket, wooden pointer", pose_asset="point_left_mid", side="right"), surface_kind="chalkboard", board_side="left", min_items=2, max_items=5, prompt_en="A warm cartoon classroom, {setting_detail}, with a very large dark green chalkboard covering the left two thirds. " + _BLANK),
    "field_alert": InfoSceneTemplate(template_id="field_alert", claim_shape="alert", diagram_kind="none", character=CharacterContract(costume="safety vest and helmet, megaphone", pose_asset="alarmed_run", gaze="camera", hand="none", side="center"), surface_kind="none", board_side="center", min_items=0, max_items=0, prompt_en="A dramatic cartoon storm crisis scene matching {setting_detail}, with no boards, no signs and no readable text anywhere."),
}


def claim_shape_from_payload(scene: dict) -> ClaimShape:
    chart = scene.get("market_chart") or {}
    if 2 <= len(scene.get("stage_items") or []) <= 4: return "stages"
    if len(scene.get("causal_nodes") or []) >= 2: return "causal_chain"
    if chart.get("external_rates"): return "external_rate"
    if chart.get("market_cap_pie") or len(scene.get("structure_items") or []) >= 2: return "structure"
    if chart.get("comparison_values"): return "comparison"
    if chart.get("points") or chart.get("latest") is not None: return "trend_hero"
    return "alert" if str(scene.get("section") or "") == "intro" else "trend_hero"


def select_template(scene: dict, proposed_id: str | None = None) -> InfoSceneTemplate | None:
    """제안값이 아닌 검증 payload의 claim_shape가 템플릿을 결정한다."""
    shape = claim_shape_from_payload(scene)
    proposed = REGISTRY.get(str(proposed_id)) if proposed_id else None
    if proposed and proposed.claim_shape == shape: return proposed
    return next((item for item in REGISTRY.values() if item.claim_shape == shape), None)

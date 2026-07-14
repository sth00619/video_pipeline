"""Turn finance narration into a repeatable, brand-safe visual performance."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SceneSpec:
    scene_id: str
    narration: str
    headline: str
    metaphor: str
    character_role: str
    character_costume: str
    character_action: str
    character_emotion: str
    setting: str
    props: list[str] = field(default_factory=list)
    camera: str = "dynamic cinematic angle"
    side_characters: str = ""
    mood: str = "neutral"

    def to_dict(self) -> dict:
        return asdict(self)


_ROLES = [
    ("detective", "tan detective coat, deerstalker cap, magnifying glass", "inspecting a glowing clue board"),
    ("factory mechanic", "safety-yellow mechanic coveralls, tool belt, hard hat", "tightening a huge industrial valve with a wrench"),
    ("chef", "white chef jacket, tall chef hat, gold-trimmed apron", "carefully plating a dramatic financial recipe"),
    ("cleanroom engineer", "white cleanroom suit, clear visor, blue gloves", "examining a luminous semiconductor wafer"),
    ("miner", "headlamp helmet, work vest, pickaxe", "discovering a glowing seam in a chart-shaped mine"),
    ("professor", "navy cardigan, round glasses, pointer", "explaining an oversized illustrated board"),
    ("explorer", "field explorer vest, utility cap, compass", "crossing a rugged market terrain with a map"),
    ("referee", "striped referee jacket, whistle", "calling a decisive market play"),
]

_SYSTEM = """You are the scene director for an original Korean finance YouTube channel.
Goldie is an anthropomorphic GOLD COIN mascot: embossed dot rim, expressive cartoon eyes,
rosy cheeks, white-gloved hands and thin dark legs. Do not copy any existing channel mascot.
Convert each narration line into a physical visual metaphor Goldie performs. Never draw a literal
number/chart as the main idea. Every scene needs a different role costume, concrete action, a
rich themed setting, and 3-6 relevant props. Do not request a screen, dashboard, chart, sign, document,
or anything with readable markings: all facts and Korean typography are post-production graphics. The entire frame is a 2D Korean webtoon illustration.
Return ONLY a JSON array, one object per requested scene, preserving scene_id. Keys: scene_id,
headline (Korean, 2-8 characters), metaphor (Korean), character_role, character_costume,
character_action, character_emotion, setting, props (English string array), camera,
side_characters, mood (positive|negative|alert|neutral). No text must be placed inside the image."""

_SCENE_TOOL = {
    "name": "record_scene_directions",
    "description": "Return the visual direction for every supplied narration scene.",
    "input_schema": {
        "type": "object",
        "properties": {"scenes": {"type": "array", "items": {"type": "object", "properties": {
            "scene_id": {"type": "string"}, "headline": {"type": "string"}, "metaphor": {"type": "string"},
            "character_role": {"type": "string"}, "character_costume": {"type": "string"}, "character_action": {"type": "string"},
            "character_emotion": {"type": "string"}, "setting": {"type": "string"}, "props": {"type": "array", "items": {"type": "string"}},
            "camera": {"type": "string"}, "side_characters": {"type": "string"}, "mood": {"type": "string"},
        }, "required": ["scene_id", "headline", "metaphor", "character_role", "character_costume", "character_action", "character_emotion", "setting", "props", "camera", "mood"]}}},
        "required": ["scenes"],
    },
}


def fallback_spec(scene_id: str, narration: str, index: int = 0) -> SceneSpec:
    role, costume, action = _ROLES[index % len(_ROLES)]
    negative = any(word in narration for word in ("하락", "폭락", "위험", "부족", "경고", "매도"))
    positive = any(word in narration for word in ("상승", "성장", "호재", "개선", "돌파", "증가"))
    mood = "negative" if negative else ("positive" if positive else "neutral")
    headline = "경고!" if negative else ("기회다!" if positive else "핵심은?!")
    return SceneSpec(
        scene_id=scene_id, narration=narration, headline=headline,
        metaphor="Goldie physically investigates the hidden mechanism behind the market move.",
        character_role=role, character_costume=costume, character_action=action,
        character_emotion="focused expression with expressive cartoon eyebrows",
        setting="a densely detailed Korean finance webtoon stage",
        props=["unlabeled market arrows", "stacked sealed folders", "industrial finance machinery"],
        camera="dynamic low-angle editorial shot", mood=mood,
    )


class SceneDirector:
    """Uses one Claude request for a video so role diversity is globally coordinated."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = os.getenv("SCENE_DIRECTOR_MODEL", "claude-sonnet-4-6")

    def direct_batch(self, lines: list[tuple[str, str]], topic_context: str = "") -> list[SceneSpec]:
        fallbacks = [fallback_spec(scene_id, narration, index) for index, (scene_id, narration) in enumerate(lines)]
        if not self.api_key or not lines:
            return fallbacks
        try:
            import anthropic
            payload = [{"scene_id": scene_id, "narration": narration} for scene_id, narration in lines]
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model, max_tokens=min(16000, max(1800, 520 * len(payload))), system=_SYSTEM,
                messages=[{"role": "user", "content": f"Topic: {topic_context or 'Korean finance'}\nScenes: {json.dumps(payload, ensure_ascii=False)}"}],
                tools=[_SCENE_TOOL], tool_choice={"type": "tool", "name": "record_scene_directions"},
            )
            tool_result = next((block.input for block in response.content if getattr(block, "type", "") == "tool_use"), None)
            if not tool_result:
                raise RuntimeError("Claude did not return the scene-direction tool payload")
            parsed = tool_result.get("scenes", [])
            by_id = {str(item.get("scene_id")): item for item in parsed if isinstance(item, dict)}
            specs: list[SceneSpec] = []
            for index, (scene_id, narration) in enumerate(lines):
                data = by_id.get(str(scene_id), {})
                base = fallbacks[index]
                props = [str(value) for value in data.get("props", []) if str(value).strip()][:6]
                specs.append(SceneSpec(
                    scene_id=scene_id, narration=narration,
                    headline=str(data.get("headline") or base.headline).strip()[:16],
                    metaphor=str(data.get("metaphor") or base.metaphor),
                    character_role=str(data.get("character_role") or base.character_role),
                    character_costume=str(data.get("character_costume") or base.character_costume),
                    character_action=str(data.get("character_action") or base.character_action),
                    character_emotion=str(data.get("character_emotion") or base.character_emotion),
                    setting=str(data.get("setting") or base.setting),
                    props=(props + base.props)[:max(3, len(props))] if len(props) < 3 else props,
                    camera=str(data.get("camera") or base.camera),
                    side_characters=str(data.get("side_characters") or ""),
                    mood=str(data.get("mood") or base.mood).lower(),
                ))
            return specs
        except Exception as exc:
            logger.warning("Scene director failed; using deterministic visual directions: %s", exc)
            return fallbacks

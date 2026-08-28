"""Turn finance narration into a repeatable, brand-safe visual performance."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)
from app.utils.anthropic_cache import cached_system, log_cache_usage


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
    # Overlay affordances are semantic hints only. Pixel geometry remains the
    # deterministic compositor's responsibility after image generation.
    thumbnail_anchor: str = ""
    thumbnail_copy_zone: str = "auto"
    thumbnail_overlay_zone: str = "auto"
    thumbnail_target: str = ""
    diegetic_surface_kind: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_ROLES = [
    ("finance analyst", "scene-appropriate business outfit", "presenting the scene's central relationship"),
    ("field reporter", "reporter outfit suited to the location and weather", "reporting from within the event"),
    ("professor", "academic outfit chosen for this explanation", "using one pointer toward the teaching prop"),
    ("semiconductor researcher", "laboratory coat and optional scene-appropriate goggles", "examining one semiconductor object"),
    ("market investigator", "investigator-inspired outfit without police insignia", "inspecting one market clue"),
    ("factory engineer", "industrial workwear suited to the machinery", "operating one relevant mechanism"),
    ("stage host", "formal presentation outfit suited to the event", "revealing the result to an audience"),
]

_SYSTEM = """You are the scene director for an original Korean finance YouTube channel.
Goldie is an anthropomorphic GOLD COIN mascot: one round coin disc forms the complete head-and-torso,
with an embossed dot rim, expressive cartoon eyes, white-gloved hands, two short compact arms, and two short compact legs. Do not copy any existing channel mascot.
Convert each narration line into the most suitable 2D editorial scene. Preserve the channel's shared
gold-coin mascot drawing language, but do not freeze one face, navy outfit, hat, character size, or
presenter pose across the video. Costume and expression may change substantially when the metaphor
or location supports them. Never use an unrelated police, safety, academic, or laboratory costume
merely to manufacture variety. Choose a coherent physical action and natural anatomy.
Composition may be object-led, character-led, chart-led, split comparison, classroom, laboratory,
control room, stage, or environmental storytelling. Use only the props needed by that scene; do not
force a fixed prop count or a board into every frame. Background people are allowed when they explain
the market mechanism. Text, numbers, bubbles, and their surfaces are planned separately, so do not
invent them here. The entire frame remains within the same 2D Korean editorial-comic visual range.
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
    if any(word in narration for word in ("반도체", "웨이퍼", "칩", "장비", "소재")):
        role, costume, action = _ROLES[3]
    elif any(word in narration for word in ("뜻", "개념", "원리", "설명", "왜")):
        role, costume, action = _ROLES[2]
    elif any(word in narration for word in ("공장", "생산", "공급망", "설비")):
        role, costume, action = _ROLES[5]
    elif any(word in narration for word in ("발표", "기록", "결과", "순위")):
        role, costume, action = _ROLES[6]
    elif any(word in narration for word in ("함정", "의문", "확인", "찾", "왜")):
        role, costume, action = _ROLES[4]
    elif any(word in narration for word in ("현장", "폭락", "급락", "항구", "수출")):
        role, costume, action = _ROLES[1]
    else:
        role, costume, action = _ROLES[0]
    negative = any(word in narration for word in ("하락", "폭락", "위험", "부족", "경고", "매도"))
    positive = any(word in narration for word in ("상승", "성장", "호재", "개선", "돌파", "증가"))
    mood = "negative" if negative else ("positive" if positive else "neutral")
    # 헤드라인은 메타데이터용이며 이미지에 자동으로 쓰거나 말풍선으로 만들지 않는다.
    headline = "경고" if negative else ("회복" if positive else "핵심")
    return SceneSpec(
        scene_id=scene_id, narration=narration, headline=headline,
        metaphor="Goldie physically investigates the hidden mechanism behind the market move.",
        character_role=role, character_costume=costume, character_action=action,
        character_emotion="focused expression with expressive cartoon eyebrows",
        setting="a densely detailed Korean finance webtoon stage",
        props=["one scene-specific evidence prop", "one contextual economic mechanism"],
        camera="dynamic low-angle editorial shot", mood=mood,
    )


class SceneDirector:
    """Uses one Claude request for a video so role diversity is globally coordinated."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = "claude-sonnet-4-6"

    def direct_batch(self, lines: list[tuple[str, str]], topic_context: str = "") -> list[SceneSpec]:
        fallbacks = [fallback_spec(scene_id, narration, index) for index, (scene_id, narration) in enumerate(lines)]
        if not self.api_key or not lines:
            return fallbacks
        try:
            import anthropic
            payload = [{"scene_id": scene_id, "narration": narration} for scene_id, narration in lines]
            # 장면 지시는 품질 보강 단계이며 결정론적 폴백이 있다.
            # SDK 기본 재시도로 동일 대형 요청을 수 분간 반복해 이미지
            # 재개를 막지 않도록 단일 150초 마감 후 폴백한다.
            client = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=150.0,
                max_retries=0,
            )
            response = client.messages.create(
                model=self.model, max_tokens=min(16000, max(1800, 520 * len(payload))), system=cached_system(_SYSTEM),
                messages=[{"role": "user", "content": f"Topic: {topic_context or 'Korean finance'}\nScenes: {json.dumps(payload, ensure_ascii=False)}"}],
                tools=[_SCENE_TOOL], tool_choice={"type": "tool", "name": "record_scene_directions"},
            )
            log_cache_usage(response, "scene_director")
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
                    props=props or base.props,
                    camera=str(data.get("camera") or base.camera),
                    side_characters=str(data.get("side_characters") or ""),
                    mood=str(data.get("mood") or base.mood).lower(),
                ))
            return specs
        except Exception as exc:
            logger.warning("Scene director failed; using deterministic visual directions: %s", exc)
            return fallbacks

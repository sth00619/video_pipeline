"""Rule-based art direction for varied, coherent finance-video scenes.

This is intentionally deterministic: the LLM supplies the factual narration,
while this module turns it into a repeatable visual brief without inventing
facts or copying a reference channel's branded assets.
"""
from __future__ import annotations

from typing import Any


FAMILY_BY_SECTION = {
    "intro": ["hero_metaphor", "news_headline", "topic_stage"],
    "background": ["industry_environment", "news_context", "history_classroom"],
    "data": ["data_lab", "factory_dashboard", "market_arena"],
    "scenario": ["cause_effect", "split_outcomes", "character_role"],
    "action": ["comparison_board", "analyst_desk", "investor_arena"],
    "conclusion": ["takeaway_stage", "classroom_takeaway", "contract_room"],
}

CAMERAS = ["wide establishing shot", "medium editorial shot", "low-angle hero shot", "over-the-shoulder explanation shot"]
LIGHTING = ["soft studio key light", "dramatic rim light", "bright editorial daylight", "cinematic practical lights"]

TOPICS = [
    ("semiconductor", ("HBM", "반도체", "메모리", "칩", "파운드리"),
     "semiconductor factory and server infrastructure", ["memory chip", "server rack", "wafer", "robot arm"]),
    ("ai_cloud", ("AI", "클라우드", "데이터센터", "서버"),
     "AI data-center and cloud infrastructure", ["server rack", "glowing compute chip", "data stream"]),
    ("market_flow", ("외국인", "기관", "수급", "매수", "매도"),
     "stock-market trading floor and flow of capital", ["order board", "market arrows", "trading tickets"]),
    ("earnings", ("실적", "매출", "영업이익", "가이던스"),
     "earnings briefing room and business dashboard", ["earnings report", "growth bar", "briefing screen"]),
    ("macro", ("금리", "환율", "유가", "인플레이션", "FOMC"),
     "global macroeconomic control room", ["interest-rate dial", "currency globe", "oil gauge"]),
    ("contract", ("계약", "수주", "주문", "납품", "공급"),
     "commercial contract and supply-chain setting", ["contract folder", "handshake", "shipping container"]),
]

PALETTES = {
    "positive": {"name": "growth_teal", "colors": "teal, mint, deep navy, small gold accents"},
    "risk": {"name": "risk_crimson", "colors": "crimson, orange, charcoal, controlled purple shadows"},
    "neutral": {"name": "editorial_blue", "colors": "cobalt blue, cyan, slate, white highlights"},
    "industrial": {"name": "industrial_teal", "colors": "steel gray, teal, safety yellow, dark navy"},
}

EDITORIAL_COMIC_STYLE = (
    "Original 2D Korean finance editorial comic, not an imitation of any existing channel or mascot. "
    "Use confident variable-width black ink contours, simple 2-to-3 tone cel shading, and a subtle printed-comic texture. "
    "Build a readable foreground, midground, and detailed background; use one dominant visual idea, intentional asymmetry, "
    "and an expressive silhouette. Keep colors saturated but organized by the supplied palette. "
    "Avoid photorealism, Pixar-like glossy 3D, plastic toy material, empty dark studio backgrounds, generic gold coin characters, "
    "and generic gold piles, explosions, rockets, fire, or space metaphors unless explicitly required."
)

WARDROBE_BY_FAMILY = {
    "hero_metaphor": ("hero_business", "tailored navy analyst suit with a gold accent"),
    "news_headline": ("analyst", "clean broadcaster jacket and notebook"),
    "topic_stage": ("explaining", "smart casual presenter outfit"),
    "industry_environment": ("engineer", "industrial safety helmet and workwear"),
    "news_context": ("analyst", "clean broadcaster jacket and notebook"),
    "history_classroom": ("teacher", "teacher cardigan with a pointer"),
    "data_lab": ("scientist", "white lab coat and data goggles"),
    "factory_dashboard": ("engineer", "industrial safety helmet and workwear"),
    "market_arena": ("analyst", "sporty market referee jacket"),
    "cause_effect": ("explaining", "smart casual presenter outfit"),
    "split_outcomes": ("thinking", "neutral analyst outfit with contrasting light"),
    "character_role": ("explorer", "field explorer vest and utility cap"),
    "comparison_board": ("explaining", "analyst suit with a presentation clicker"),
    "analyst_desk": ("thinking", "navy analyst suit at a desk"),
    "investor_arena": ("pointing", "market coach jacket"),
    "takeaway_stage": ("happy", "tailored navy analyst suit with a gold accent"),
    "classroom_takeaway": ("teacher", "teacher cardigan with a pointer"),
    "contract_room": ("analyst", "formal business suit with contract folder"),
}


def _topic(text: str) -> tuple[str, str, list[str]]:
    for name, keywords, setting, props in TOPICS:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return name, setting, props
    return "finance", "premium Korean finance editorial studio", ["financial chart silhouette", "briefing screen", "document folder"]


def _mood(text: str) -> str:
    risk = ("하락", "급락", "위험", "우려", "부족", "경고", "악화", "매도", "둔화")
    positive = ("상승", "성장", "증가", "호재", "개선", "돌파", "수주", "회복")
    if any(word in text for word in risk):
        return "risk"
    if any(word in text for word in positive):
        return "positive"
    return "neutral"


def direct_scenes(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add a unique visual brief to every scene while avoiding adjacent repeats."""
    directed: list[dict[str, Any]] = []
    previous_families: list[str] = []
    previous_palettes: list[str] = []
    for index, original in enumerate(scenes):
        scene = dict(original)
        text = str(scene.get("content") or scene.get("text") or "")
        section = str(scene.get("section") or "scenario").lower()
        candidates = FAMILY_BY_SECTION.get(section, FAMILY_BY_SECTION["scenario"])
        family = next((item for item in candidates if item not in previous_families[-2:]), candidates[index % len(candidates)])
        topic_name, setting, props = _topic(text)
        mood = _mood(text)
        palette_key = "industrial" if family in {"industry_environment", "factory_dashboard", "data_lab"} else mood
        if previous_palettes and palette_key == previous_palettes[-1] and len(candidates) > 1:
            palette_key = "neutral" if palette_key != "neutral" else "positive"
        wardrobe_key, wardrobe = WARDROBE_BY_FAMILY[family]
        character_required = family not in {"news_headline", "news_context"}
        if family == "data_lab":
            character_required = False
        elif family in {"factory_dashboard", "market_arena"}:
            character_required = True
        pose = scene.get("pose") or wardrobe_key
        camera = CAMERAS[index % len(CAMERAS)]
        direction = {
            "family": family,
            "topic": topic_name,
            "setting": setting,
            "props": props,
            "palette": PALETTES[palette_key],
            "wardrobe": wardrobe,
            "pose_asset": wardrobe_key,
            "character_required": character_required,
            "camera": camera,
            "lighting": LIGHTING[(index + 1) % len(LIGHTING)],
            # Data scenes are composed around a real in-world monitor.  The
            # generator only supplies the empty surface; deterministic code
            # fills it with the factual chart after generation.
            "character_placement": "left third" if section == "data" and character_required else ("right third" if character_required else "none"),
            "overlay_strategy": "integrated_market_surface" if section == "data" else ("headline_card" if family == "news_headline" else "none"),
            "data_surface": {"x": 880, "y": 120, "width": 900, "height": 520} if section == "data" else None,
            "negative_constraints": ["no readable text", "no watermark", "no generic gold pile", "no unrelated fire or space scene"],
            # AI가 그려내는 장식용 표지/라벨은 선택적으로 허용하되, 사실값은 항상 별도 검증 오버레이로 렌더링한다.
            "decorative_text_allowed": bool(scene.get(
                "decorative_text_allowed",
                family in {"news_headline", "news_context", "comparison_board", "factory_dashboard", "data_lab"},
            )),
        }
        scene["pose"] = pose
        scene["art_direction"] = direction
        scene["style_profile"] = "editorial_comic_2d"
        scene["visual_type"] = scene.get("visual_type") or family
        plan = dict(scene.get("visual_plan") or {})
        plan.update({"family": family, "character_required": character_required, "art_direction": direction})
        scene["visual_plan"] = plan
        directed.append(scene)
        previous_families.append(family)
        previous_palettes.append(palette_key)
    return directed


def plan_image_quality_tiers(scenes: list[dict[str, Any]], tier: str, pro_limit: int) -> list[dict[str, Any]]:
    """Assign expensive Pro generations to editorial anchor scenes only.

    This makes quality deliberate: the scenes that carry factual proof, the
    hook, comparisons, and conclusion get the most composition budget while
    connective scenes remain fast and affordable.
    """
    normalized = str(tier or "hybrid").lower()
    if normalized not in {"flash", "hybrid", "pro"}:
        normalized = "hybrid"
    limit = max(0, int(pro_limit or 0))
    ranked: list[tuple[int, int]] = []
    for index, scene in enumerate(scenes):
        direction = scene.get("art_direction") or {}
        family = str(direction.get("family") or "")
        section = str(scene.get("section") or "")
        score = 0
        if index == 0:
            score += 100
        if section == "data":
            score += 90
        if family in {"news_headline", "news_context", "comparison_board", "factory_dashboard", "industry_environment"}:
            score += 70
        if section == "conclusion":
            score += 50
        if family in {"cause_effect", "split_outcomes"}:
            score += 30
        ranked.append((score, index))

    if normalized == "pro":
        pro_indices = {index for _, index in ranked}
    elif normalized == "flash" or limit == 0:
        pro_indices = set()
    else:
        ranked.sort(key=lambda item: (-item[0], item[1]))
        pro_indices = {index for score, index in ranked[:limit] if score > 0}

    planned: list[dict[str, Any]] = []
    for index, original in enumerate(scenes):
        scene = dict(original)
        use_pro = index in pro_indices
        scene["image_profile"] = {
            "tier": "pro" if use_pro else "flash",
            "model": "gemini-3-pro-image" if use_pro else "gemini-3.1-flash-image",
            "image_size": "2K" if use_pro else "1K",
            "reason": "editorial_anchor" if use_pro else "supporting_scene",
        }
        planned.append(scene)
    return planned


def compile_editorial_prompt(scene: dict[str, Any], base_prompt: str) -> str:
    direction = scene.get("art_direction") or {}
    palette = (direction.get("palette") or {}).get("colors", "editorial blue and teal")
    props = ", ".join(direction.get("props") or [])
    character_clause = "no mascot character; focus on the real-world context and props"
    if direction.get("character_required"):
        character_clause = (
            f"the fixed channel mascot on the {direction.get('character_placement', 'right third')}, "
            f"wearing {direction.get('wardrobe', 'a professional analyst outfit')}, "
            f"using the {direction.get('pose_asset', 'explaining')} pose"
        )
    text_clause = (
        "Decorative, non-factual labels or signage may be integrated naturally into the illustration; "
        "do not render exact prices, percentages, dates, tickers, or claims. "
        if direction.get("decorative_text_allowed") else
        "No readable text, no caption, no number, no logo, no watermark. "
    )
    data_surface_clause = ""
    if scene.get("market_chart"):
        visual_theme = str((scene.get("market_chart") or {}).get("visual_theme") or "chalkboard")
        visual_kind = str((scene.get("market_chart") or {}).get("visual_kind") or "trend_dashboard")
        surface = direction.get("data_surface") or {}
        surface_by_theme = {
            "chalkboard": "a blank hand-drawn charcoal chalkboard panel, with subtle chalk dust and a thick uneven white outline",
            "paper_poster": "a blank warm-cream paper infographic poster pinned naturally to the scene, with hand-inked border and paper texture",
            "factory_panel": "a blank painted factory control panel with bolts, warning stripes, and a clean central display area",
        }
        visual_by_kind = {
            "trend_dashboard": "a wide price-trend, short bar-movement, and composition-chart layout",
            "change_arrow": "a bold rising or falling arrow with a short factual number block",
            "composition_pie": "one large circular composition chart with a compact legend",
            "comparison": "two tall comparison columns with room above each for an exact value",
        }
        data_surface_clause = (
            f"Build {surface_by_theme.get(visual_theme, surface_by_theme['chalkboard'])} in the {surface.get('anchor', 'right-side')}, "
            f"with enough unobstructed space for {visual_by_kind.get(visual_kind, visual_by_kind['trend_dashboard'])}. "
            "The blank information surface MUST be a wide landscape-oriented rectangular board, roughly 16:9 and clearly wider than tall, "
            "mounted flat and front-facing in the upper-right third of the frame; never a circle, porthole, tall vertical frame, tilted easel, or curved screen. "
            "The information surface must have no letters, no digits, no chart marks, "
            "no glare, no hands, and no objects covering it; it will receive a verified Korean chart in compositing. "
        )
    return (
        f"{base_prompt}. Editorial scene family: {direction.get('family', 'character_role')}. "
        f"Setting: {direction.get('setting', 'finance studio')}. Key props: {props}. "
        f"Composition: {direction.get('camera', 'medium editorial shot')}; {character_clause}. "
        f"Color script: {palette}. Lighting: {direction.get('lighting', 'soft studio key light')}. "
        f"{EDITORIAL_COMIC_STYLE} "
        "Specific real-world business props, strong visual storytelling, saturated but controlled colors. "
        f"{text_clause}"
        f"{data_surface_clause}"
        "Reserve the lower 22 percent of the frame for separately rendered Korean subtitles."
    )


def assess_art_diversity(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    families = [str((s.get("art_direction") or {}).get("family") or "") for s in scenes]
    palettes = [str(((s.get("art_direction") or {}).get("palette") or {}).get("name") or "") for s in scenes]
    poses = [str((s.get("art_direction") or {}).get("pose_asset") or s.get("pose") or "") for s in scenes]
    warnings: list[str] = []
    if len(scenes) >= 6 and len(set(families)) < 5:
        warnings.append("low_scene_family_diversity")
    if len(scenes) >= 6 and len(set(palettes)) < 3:
        warnings.append("low_palette_diversity")
    for name, values in (("family", families), ("palette", palettes), ("pose", poses)):
        for i in range(2, len(values)):
            if values[i] and values[i] == values[i - 1] == values[i - 2]:
                warnings.append(f"three_consecutive_{name}:{i-2}-{i}")
                break
    score = max(0, 100 - 20 * len(warnings))
    return {"score": score, "warnings": warnings, "families": families, "palettes": palettes, "pose_assets": poses}

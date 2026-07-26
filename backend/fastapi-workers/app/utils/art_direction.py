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
    "positive": {"name": "growth_gold", "colors": "mostly deep navy and white, one warm yellow emphasis, muted gray"},
    "risk": {"name": "risk_crimson", "colors": "mostly charcoal and white, one deep crimson warning, muted gray"},
    "neutral": {"name": "editorial_blue", "colors": "mostly deep navy, white, and muted blue-gray; at most one warm yellow emphasis"},
    "industrial": {"name": "industrial_navy", "colors": "mostly steel gray and dark navy, one safety-yellow cue, white highlights"},
}

EDITORIAL_COMIC_STYLE = (
    "NON-NEGOTIABLE: Original 2D Korean finance editorial cartoon, not an imitation of any existing channel or mascot. "
    "Use confident variable-width black ink contours, simple 2-to-3 tone cel shading, and a subtle printed-comic texture. "
    "Build a readable foreground, midground, and detailed background; use one dominant visual idea, intentional asymmetry, "
    "and an expressive silhouette. The mascot, background, props, blank chart board, and future overlay-safe areas must be one cohesive cartoon illustration. "
    "Use a restrained, scene-led colour script: one dominant background palette, white/black typography, and at most one warm emphasis colour. "
    "Never use rainbow data colours, neon UI gradients, glowing dashboard grids, decorative colour coding, or several competing coloured cards. "
    "Only a verified data scene may contain a simple in-world board; it must read as a physical cartoon prop, not a technology studio. "
    "Every scene must be a fresh, story-specific illustration rather than a reused set: use a detailed location, tangible props, foreground depth, dramatic weather or lighting only when the narration warrants it, and expressive character acting. "
    "Aim for polished Korean editorial-animation key art: energetic hand-inked contours, layered painted scenery, rich prop detail, and cinematic but readable staging; never flat vector clip art or generic corporate stock illustration. "
    "Do not add a blank circle, empty chart, empty sign, or generic panel merely as decoration. Every information surface must be a justified object in the scene and must be filled by verified post-production data, otherwise omit it. "
    "Avoid photorealism, Pixar-like glossy 3D, plastic toy material, empty dark studio backgrounds, generic gold coin characters, "
    "and generic gold piles, explosions, rockets, fire, or space metaphors unless explicitly required."
)

# A data visual is a prop selected by the story, not a permanent chalkboard.
# The renderer still receives one rectangular safe region, while the image
# generator is told what that region physically is in the current scene.
DATA_SURFACE_BY_FAMILY = {
    "data_lab": ("monitor", "a large blank wall monitor or desk terminal, with a matte non-glowing screen"),
    "factory_dashboard": ("inspection_clipboard", "a blank clipped inspection sheet attached to a machine guard"),
    "market_arena": ("trading_ticket", "a blank printed market ticket or referee score card held beside the action"),
    "comparison_board": ("ledger_card", "a blank cream ledger card pinned beside the compared physical objects"),
    "analyst_desk": ("desk_report", "a blank printed analyst report lying flat on the desk"),
    "news_context": ("map_cloud", "one or two blank illustrated cloud labels anchored directly over the relevant map locations"),
    "industry_environment": ("product_label", "a blank inspection tag attached directly to the relevant product or container"),
}

# Marker surfaces are deliberately scene props, not generic beige cards.  The
# detector later verifies the real generated geometry before any exact copy is
# rendered.  Map clouds are irregular masks and are therefore never quad-warped.
SURFACE_CONTRACT_BY_KIND = {
    "monitor": {"geometry": "planar_quad", "marker_rgb": (65, 86, 102), "border_rgb": (15, 27, 42), "preferred_side": "left", "preferred_region": {"x": .05, "y": .10, "width": .42, "height": .60}, "tilt_hint": "nearly front-facing matte monitor"},
    "inspection_clipboard": {"geometry": "planar_quad", "marker_rgb": (225, 210, 175), "border_rgb": (76, 53, 34), "preferred_side": "right", "preferred_region": {"x": .52, "y": .11, "width": .42, "height": .60}, "tilt_hint": "slightly tilted clipped inspection sheet"},
    "trading_ticket": {"geometry": "planar_quad", "marker_rgb": (205, 220, 214), "border_rgb": (21, 42, 51), "preferred_side": "left", "preferred_region": {"x": .06, "y": .12, "width": .40, "height": .56}, "tilt_hint": "slightly tilted printed score ticket"},
    "ledger_card": {"geometry": "planar_quad", "marker_rgb": (231, 214, 177), "border_rgb": (82, 54, 30), "preferred_side": "left", "preferred_region": {"x": .05, "y": .12, "width": .42, "height": .57}, "tilt_hint": "slightly tilted ledger card pinned to the compared prop"},
    "desk_report": {"geometry": "planar_quad", "marker_rgb": (219, 225, 218), "border_rgb": (44, 53, 51), "preferred_side": "left", "preferred_region": {"x": .08, "y": .42, "width": .48, "height": .36}, "tilt_hint": "a report lying at a real desk perspective"},
    "product_label": {"geometry": "planar_quad", "marker_rgb": (217, 200, 159), "border_rgb": (65, 48, 31), "preferred_side": "right", "preferred_region": {"x": .56, "y": .20, "width": .32, "height": .42}, "tilt_hint": "a small hanging inspection tag on the product"},
    "map_cloud": {"geometry": "irregular_mask", "marker_rgb": None, "border_rgb": None, "preferred_side": "left", "preferred_region": {"x": .08, "y": .16, "width": .36, "height": .26}, "tilt_hint": "a blank illustrated cloud label anchored to the map"},
    "scene_card": {"geometry": "planar_quad", "marker_rgb": (213, 220, 212), "border_rgb": (45, 55, 56), "preferred_side": "right", "preferred_region": {"x": .52, "y": .14, "width": .40, "height": .54}, "tilt_hint": "a real physical information card attached to the key prop"},
}


def _surface_contract(kind: str, character_placement: str) -> dict[str, Any]:
    contract = {"surface_kind": kind, **SURFACE_CONTRACT_BY_KIND.get(kind, SURFACE_CONTRACT_BY_KIND["scene_card"])}
    preferred = dict(contract["preferred_region"])
    # Place the prop opposite the mascot when the family permits it.  This is
    # a planning hint only; detector ambiguity always fails safely.
    if "right" in character_placement and preferred.get("x", 0) > .5:
        preferred["x"] = .08
    elif "left" in character_placement and preferred.get("x", 0) < .5:
        preferred["x"] = .52
    contract["preferred_region"] = preferred
    return contract

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

# Phase 2: role costumes are concrete library keys, not prose-only direction.
# Every role has neutral/highlight/worried variants. Older generic libraries
# retain a fallback pose until the channel opts in to generating the new set.
ROLE_COSTUME_BY_FAMILY = {
    "hero_metaphor": "field_reporter", "news_headline": "anchor", "topic_stage": "anchor",
    "industry_environment": "field_reporter", "news_context": "anchor", "history_classroom": "professor",
    "data_lab": "analyst", "factory_dashboard": "analyst", "market_arena": "referee",
    "cause_effect": "anchor", "split_outcomes": "referee", "character_role": "field_reporter",
    "comparison_board": "referee", "analyst_desk": "analyst", "investor_arena": "referee",
    "takeaway_stage": "anchor", "classroom_takeaway": "professor", "contract_room": "analyst",
}

# The reference frames supplied for review show that the character should not
# always occupy the same side or the same amount of the image.  These are
# reusable *composition grammar* tokens, not a copy of any channel branding:
# they describe where an original mascot, a real in-world information surface,
# and a later deterministic text layer may safely coexist in a 16:9 cartoon.
REFERENCE_COMPOSITION_BY_FAMILY = {
    "hero_metaphor": {"id": "hero_reaction", "character_placement": "left third", "character_area_target": .48, "information_area_target": .26},
    "news_headline": {"id": "headline_reaction", "character_placement": "right third", "character_area_target": .46, "information_area_target": .30},
    "topic_stage": {"id": "topic_explainer", "character_placement": "right third", "character_area_target": .42, "information_area_target": .28},
    "industry_environment": {"id": "field_alert", "character_placement": "center foreground", "character_area_target": .52, "information_area_target": .25},
    "news_context": {"id": "news_map", "character_placement": "right third", "character_area_target": .44, "information_area_target": .31},
    "history_classroom": {"id": "chalkboard_lesson", "character_placement": "right third", "character_area_target": .43, "information_area_target": .40},
    "data_lab": {"id": "data_lab", "character_placement": "right third", "character_area_target": .44, "information_area_target": .42},
    "factory_dashboard": {"id": "factory_panel", "character_placement": "left third", "character_area_target": .42, "information_area_target": .42},
    "market_arena": {"id": "market_scoreboard", "character_placement": "right third", "character_area_target": .46, "information_area_target": .38},
    "cause_effect": {"id": "cause_effect", "character_placement": "left third", "character_area_target": .48, "information_area_target": .30},
    "split_outcomes": {
        "id": "split_comparison", "character_placement": "center foreground", "character_area_target": .30, "information_area_target": .48,
        "scene_recipe": "a dramatic left-versus-right physical world split: one stressed environment and one stabilised environment, the mascot mediating in the foreground; two large blank illustrated parchment notices at upper left and upper right, with one blank white burst between them",
        "information_surfaces": [
            {"kind": "parchment", "x": .05, "y": .07, "width": .32, "height": .28},
            {"kind": "burst", "x": .40, "y": .05, "width": .20, "height": .25},
            {"kind": "parchment", "x": .63, "y": .07, "width": .32, "height": .28},
        ],
    },
    "character_role": {"id": "role_story", "character_placement": "left third", "character_area_target": .50, "information_area_target": .25},
    "comparison_board": {"id": "comparison_board", "character_placement": "right third", "character_area_target": .42, "information_area_target": .42},
    "analyst_desk": {"id": "analyst_take", "character_placement": "right third", "character_area_target": .42, "information_area_target": .28},
    "investor_arena": {"id": "decision_arena", "character_placement": "left third", "character_area_target": .46, "information_area_target": .30},
    "takeaway_stage": {"id": "takeaway", "character_placement": "center foreground", "character_area_target": .48, "information_area_target": .24},
    "classroom_takeaway": {"id": "chalkboard_takeaway", "character_placement": "right third", "character_area_target": .42, "information_area_target": .40},
    "contract_room": {"id": "contract_explainer", "character_placement": "left third", "character_area_target": .45, "information_area_target": .30},
}


def _costume_state(section: str, mood: str) -> str:
    if mood == "risk" or section == "intro":
        return "worried"
    if mood == "positive" or section == "conclusion":
        return "highlight"
    return "neutral"


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
        costume_role = ROLE_COSTUME_BY_FAMILY[family]
        costume_state = _costume_state(section, mood)
        # The channel mascot is a visual narrator, not an optional decoration.
        # Keeping it in every scene prevents generic background-only frames.
        character_required = True
        pose = scene.get("pose") or wardrobe_key
        camera = CAMERAS[index % len(CAMERAS)]
        composition = dict(REFERENCE_COMPOSITION_BY_FAMILY[family])
        character_placement = composition["character_placement"] if character_required else "none"
        # The opposite side of the mascot remains visually quiet so a cloud or
        # target-bound label can be added without covering either narration or
        # the character. Coordinates are normalized for the final compositor.
        overlay_target = (
            {"x": .53, "y": .16, "width": .36, "height": .25}
            if "left" in character_placement else
            {"x": .10, "y": .16, "width": .36, "height": .25}
        )
        data_surface = None
        data_surface_kind = None
        data_surface_prompt = None
        surface_contract = None
        if section == "data":
            # An explanation panel gets the broad side opposite the mascot.
            # Center-foreground comparison scenes receive a full-width upper
            # board and retain the middle for the referee/mediator pose.
            data_surface = (
                {"x": 110, "y": 115, "width": 780, "height": 525}
                if "right" in character_placement else
                ({"x": 1030, "y": 115, "width": 780, "height": 525}
                    if "left" in character_placement else
                    {"x": 300, "y": 80, "width": 1320, "height": 350})
            )
            data_surface_kind, data_surface_prompt = DATA_SURFACE_BY_FAMILY.get(
                family,
                ("scene_card", "one blank physical information card naturally attached to the key prop"),
            )
            surface_contract = _surface_contract(data_surface_kind, character_placement)
        direction = {
            "family": family,
            "topic": topic_name,
            "setting": setting,
            "props": props,
            "palette": PALETTES[palette_key],
            "wardrobe": wardrobe,
            "role_costume": costume_role,
            "costume_state": costume_state,
            "pose_asset": f"{costume_role}_{costume_state}",
            "fallback_pose": wardrobe_key,
            "character_required": character_required,
            "camera": camera,
            "lighting": LIGHTING[(index + 1) % len(LIGHTING)],
            "reference_composition": composition,
            # Data scenes are composed around a real in-world monitor.  The
            # generator only supplies the empty surface; deterministic code
            # fills it with the factual chart after generation.
            "character_placement": character_placement,
            # This is an executable scene grammar, not merely a prompt hint.
            # The clean plate receives the factual surface first; the locked
            # alpha character is always the foreground layer so hands/fingers
            # naturally occlude the prop instead of being covered by it.
            "layer_pipeline": {
                "version": "3.0",
                "render_clean_plate": True,
                "canonical_character_required": character_required,
                "z_order": ["clean_background", "verified_info_surface", "character_foreground", "editorial_text"],
            },
            "overlay_strategy": "integrated_market_surface" if section == "data" else ("headline_card" if family == "news_headline" else "none"),
            "data_surface": data_surface,
            "data_surface_kind": data_surface_kind,
            "data_surface_prompt": data_surface_prompt,
            "surface_contract": surface_contract,
            # Classroom scenes reserve a genuine blank board.  This is the
            # only non-data surface on which the overlay grammar may render
            # explanatory Korean directly as chalk instead of a floating card.
            "editorial_text_surface": {"x": .10, "y": .16, "width": .55, "height": .42} if family in {"history_classroom", "classroom_takeaway"} else None,
            "editorial_overlay_target": overlay_target,
            "negative_constraints": ["no readable text", "no watermark", "no generic gold pile", "no unrelated fire or space scene", "no photorealism", "no mixed art styles"],
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
    # Even decorative model text becomes unstable pseudo-Korean at video
    # resolution.  A cartoon frame may contain texture, chalk dust, abstract
    # data glows, and blank illustrated props, but every readable character
    # comes from a deterministic overlay after generation.
    text_clause = "No readable text, no caption, no number, no logo, no watermark, no decorative labels. "
    data_surface_clause = ""
    composition_recipe = str(direction.get("reference_composition", {}).get("scene_recipe") or "")
    if scene.get("market_chart"):
        visual_theme = str((scene.get("market_chart") or {}).get("visual_theme") or "chalkboard")
        visual_kind = str((scene.get("market_chart") or {}).get("visual_kind") or "trend_dashboard")
        surface = direction.get("data_surface") or {}
        surface_by_theme = {
            "chalkboard": "a blank hand-drawn cartoon charcoal chalkboard panel, with subtle chalk dust, hand-inked edge highlights, and a thick uneven white outline",
            "paper_poster": "a blank warm-cream torn-paper notice pinned naturally to the scene, with a hand-inked irregular border, tape and paper texture; reserve a simple graph baseline inside",
            "factory_panel": "a blank painted factory score board with bolts and one large cream data card, never a glowing technology dashboard",
        }
        surface_by_kind = {
            "monitor": "a large blank physical monitor with a matte screen and no UI glow",
            "inspection_clipboard": "a large blank clipboard or inspection sheet physically attached to the relevant machine",
            "trading_ticket": "a large blank printed market ticket or referee score card integrated with the scene",
            "ledger_card": "a large blank warm-cream ledger card pinned beside the compared physical objects",
            "desk_report": "a large blank printed analyst report lying naturally on the desk",
            "map_cloud": "one or two blank illustrated gray cloud labels anchored to the relevant map locations",
            "product_label": "a large blank inspection tag physically attached to the relevant product or container",
            "scene_card": "a large blank physical information card naturally attached to the key prop",
        }
        visual_by_kind = {
            "trend_dashboard": "a wide price-trend, short bar-movement, and composition-chart layout",
            "change_arrow": "a bold rising or falling arrow with a short factual number block",
            "composition_pie": "one large circular composition chart with a compact legend",
            "comparison": "two tall comparison columns with room above each for an exact value",
        }
        board_side = "left" if "right" in str(direction.get("character_placement")) else "right"
        prop_description = surface_by_kind.get(
            str(direction.get("data_surface_kind") or ""),
            surface_by_theme.get(visual_theme, surface_by_theme["chalkboard"]),
        )
        contract = direction.get("surface_contract") or {}
        marker_rgb = contract.get("marker_rgb")
        marker_clause = ""
        if marker_rgb:
            marker_clause = (
                f" Its writable interior is a single matte RGB({marker_rgb[0]}, {marker_rgb[1]}, {marker_rgb[2]}) colour, "
                "surrounded by its own dark hand-inked material border; it has no writing or markings."
            )
        data_surface_clause = (
            f" Include {prop_description}; it is a fully illustrated in-world prop. "
            f"{marker_clause} "
            f"The mascot character stands entirely within the {str(direction.get('character_placement') or 'left third').upper()}. Keep the {board_side}-side board completely blank inside: "
            "no text, numbers, chart, UI, or character parts overlap it. Deterministic post-production will add the exact cartoon data graphic."
        )
    elif direction.get("editorial_text_surface"):
        data_surface_clause = (
            " Include a large blank green classroom chalkboard in the left and center of the frame. "
            "Keep its writing surface completely empty: no generated words, labels, numbers, chart marks, or character parts overlap it. "
            "Deterministic post-production will write one exact Korean explanatory chalk note on this board."
        )
    section = str(scene.get("section") or "scenario")
    recipe_clause = f"Scene recipe: {composition_recipe}. " if composition_recipe else ""
    affordance_clause = {
        "intro": " Keep the upper area as simple continuous atmosphere with low-detail texture for a later alert overlay.",
        "background": " Leave a natural low-detail area beside the map, factory, or policy prop for a later explanatory cloud overlay.",
        "scenario": " Make one physical decision prop clearly visible, with open continuous background around it for a later target-bound overlay.",
        "action": " Keep the mascot hand or pointer and its target prop unobstructed for a later decision chip.",
        "conclusion": " Keep one strong focal stage or spotlight with open upper space for a small takeaway overlay.",
    }.get(section, "")
    return (
        f"{base_prompt}. Editorial scene family: {direction.get('family', 'character_role')}. "
        f"Setting: {direction.get('setting', 'finance studio')}. Key props: {props}. "
        f"Composition: {direction.get('camera', 'medium editorial shot')}; {character_clause}. "
        f"{recipe_clause}"
        f"Color script: {palette}. Lighting: {direction.get('lighting', 'soft studio key light')}. "
        f"{EDITORIAL_COMIC_STYLE} "
        "Specific real-world business props, one clear focal relationship, restrained cartoon colours, and generous empty space around the factual information. Make all writable props look like part of this exact illustrated world. "
        f"{text_clause}"
        f"{data_surface_clause}"
        f"{affordance_clause}"
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

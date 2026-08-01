"""V5 정보 장면의 무문자 이미지 프롬프트를 구성한다."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.v5.scene.scene_type_archetypes import ArchetypeSelection


MASCOT_STYLE_BIBLE = (
    "a friendly anthropomorphic GOLD COIN mascot character, round gold coin body with an embossed rim, "
    "expressive cartoon face, large round eyes with visible white sclera, small confident smile, "
    "white four-finger cartoon gloves, short stubby legs with brown shoes, thick clean black ink outline, "
    "flat cel-shading, warm rim light. Keep the exact same round coin silhouette, rim thickness, face proportions, "
    "eye shape, iris style, eyebrows, and ink-line weight as the fixed channel mascot in every scene; only wardrobe, "
    "pose, and facial expression may change. Never restyle the mascot as a flat token, a different cartoon character, "
    "or a different illustration medium"
)


# 기존 8종 승인본의 미감을 현재 실전 경로에서도 명시적으로 고정한다. 이 계약은
# 사실값·수치의 생성 지시가 아니라 선·명암·무대 밀도에 관한 그림체 계약이다.
V5_STYLE_CONTRACT_VERSION = "2026-08-02-cinematic-cartoon-recovery"
V5_CINEMATIC_CARTOON_STYLE_CONTRACT = (
    "NON-NEGOTIABLE VISUAL STYLE CONTRACT: hand-illustrated 2D Korean economic-explainer cartoon, not a premium semi-realistic illustration. "
    "Use a uniform, bold dark-brown ink outline on the mascot, props, and set; keep the line weight deliberately clean and consistent rather than variable or painterly. "
    "Use clear cel-shading with readable, discrete shadow shapes. Soft gradients are allowed only for controlled rim light, metal shine, holographic glow, rain glow, or stage haze; they must not replace the cel-shaded forms. "
    "Build a theatrical three-depth stage with dense scene-native props, strong foreground-to-background separation, and an intentional limited vivid palette chosen for the scene. "
    "Preserve the playful round gold-coin mascot proportions and the simple broadcast-cartoon readability of the approved V5 benchmark images. "
    "Avoid glossy 3D-toy rendering, painterly editorial illustration, airbrushed facial modelling, thin sketchy outlines, muted corporate infographic styling, or a generic premium concept-art finish."
)

EMOTION_MAP = {
    "surprise": "shocked wide-eyed expression, open mouth, sweat drop",
    "happy": "bright cheerful smile, sparkling eyes, one hand waving",
    "explain": "calm friendly explaining expression, gentle smile",
    "confidence": "smug confident half-lidded eyes, subtle smirk",
    "concern": "worried frightened face, spiral or wide eyes, sweat drops",
    "alarm": "panicked alarmed face, mouth open shouting",
}
COSTUME_MAP = {
    "analyst": "wearing a brown fedora hat and a call-center headset with mic, brown blazer",
    "professor": "wearing a black graduation cap and round glasses, tweed jacket",
    "reporter": "wearing a brown fedora and a navy TV-anchor suit",
    "formal": "wearing an elegant black tuxedo with red bow tie, holding a cane",
    "safety_vest": "wearing an orange hard hat and a reflective yellow safety vest",
    "vest": "wearing a navy waistcoat over a shirt, sleeves visible",
}
POSE_MAP = {
    "point_left": "holding a wooden pointer, pointing to the left toward the visual explanation",
    "present": "one arm extended presenting, open palm gesture",
    "alarmed_run": "running forward in panic, holding a red megaphone",
    "calculator_hold": "holding up a large chunky calculator-shaped prop with a shocked look",
    "think": "hand on chin in a thinking pose, holding a pen",
}


@dataclass(frozen=True)
class Archetype:
    stage: str
    props: str
    lighting: str
    visual_detail: str


ARCHETYPES = {
    "port_emergency": Archetype(
        "a stormy shipping port at night, container cranes and a cargo ship in the background, wet reflective dock",
        "stacked shipping containers, a large cargo ship, harbor cranes, red warning beacons, crashing waves",
        "dark stormy sky, lightning strike, heavy rain, red emergency light glow",
        "rain streaks, beacon glows, container color blocks, and wave silhouettes",
    ),
    "retail_shock": Archetype(
        "a bright modern grocery store checkout counter, shelves of products behind, a conveyor belt",
        "a large chunky checkout device with color buttons, a conveyor belt, densely stocked product shelves",
        "bright clean fluorescent store lighting, a red alert glow around the checkout device",
        "product silhouettes, alert-color light rings, and color-coded shelf and package blocks without glyphs; no extra monitors or digital signage",
    ),
    "classroom": Archetype(
        "a cozy university lecture classroom with a large green teaching wall and wooden desks",
        "a big teaching wall with a world map silhouette and arrows, a wooden pointer, green banker lamps, an open book",
        "warm indoor classroom light, soft glow from desk lamps, subtle sparkles",
        "chalk-like map outlines, arrows, circles, and connected geometric marks without glyphs",
    ),
    "weather_map": Archetype(
        "a TV weather studio with a large curved illuminated map wall and broadcast cameras on tripods",
        "a giant map wall, storm clouds over the map, a pointer, studio cameras, ceiling spotlights",
        "cool blue studio lighting, map-wall glow, spotlight beams",
        "storm-cloud icons, directional arrows, and colored weather bands without glyphs",
    ),
    "risk_control_room": Archetype(
        "a unified high-end market risk control room with one continuous curved operations wall and a broad central floor",
        "a cracked shipping crate beside a closed golden umbrella, analog risk gauges, color-only chart silhouettes, alert lamps, and a large physical console",
        "a continuous cool-blue ambient room light with localized red warning glow and warm protective gold highlights, without a dividing line",
        "connected circuit paths, curved signal arcs, red-to-gold light gradients, gauge needles, and abstract non-linguistic chart forms in one uninterrupted space",
    ),
    "trade_calculator": Archetype(
        "a dark blue high-tech analysis room with luminous abstract connections floating in the air",
        "a large golden balance scale, floating pie and bar silhouettes without axes, glowing connection paths, a stack of documents",
        "dark navy background with neon cyan and orange glow, dramatic spotlight on the character",
        "floating geometric lines, colored bar silhouettes, and luminous connection paths",
    ),
    "data_lab": Archetype(
        "a futuristic control-room with a holographic map wall and abstract data light forms",
        "a holographic map with node lights, floating bar and line silhouettes without axes, a control console, glowing data streams",
        "cool holographic blue-cyan glow, soft ambient room light",
        "holographic map nodes, luminous lines, color blocks, and color-only data streams",
    ),
    "earnings_stage": Archetype(
        "a premium corporate earnings presentation stage with one broad briefing surface embedded flush into the center back wall behind a podium",
        "a central podium, fixed microphones, audience seating, broadcast cameras, ceiling spotlights, stage floor lines, and plain unadorned side walls",
        "deep navy presentation lighting with a warm spotlight on the presenter and restrained cyan wall glow",
        "one chart silhouette only inside the central briefing surface, camera outlines, seat rows, podium material, plain wall texture, and light gradients",
    ),
    "briefing_podium": Archetype(
        "a formal policy and CEO press briefing room with one broad briefing surface embedded flush into the center back wall behind a central podium",
        "a central podium, fixed microphones, press seating, broadcast cameras, ceiling lights, flag-color ribbons without emblems, and floor cables",
        "calm neutral press-room lighting with a focused warm key light and soft blue wall illumination",
        "non-writing briefing diagrams, microphone forms, camera silhouettes, ribbon colors, and cable lines",
    ),
    "real_estate_office": Archetype(
        "a refined real-estate and interest-rate consultation office with one broad guidance board fixed flush to the wall behind the consultation desk",
        "a consultation desk, loose papers, file folders, a physical calculator, a house model, a window with exterior home silhouettes, and banker lamps",
        "warm professional office lighting with soft window light and a subtle cool reflection on the wall board",
        "non-writing house silhouettes, material-rich folders, blank calculator display, color-only guidance icons, and desk-light glow",
    ),
    "job_market_hall": Archetype(
        "a public employment consultation hall with one broad employment-trend guidance board fixed flush to the wall behind a central consultation counter",
        "a consultation counter, booth dividers, a small mechanical paper ticket dispenser with no display, closed resume folders, bags, guide lights, job seekers, and color-only career icons",
        "bright civic interior lighting with a calm welcoming glow and restrained accent colors",
        "non-writing career icons, queue-machine shapes, folder materials, divider lines, and color-only employment silhouettes",
    ),
}


@dataclass
class SceneSpec:
    scene_id: str
    archetype: str
    emotion: str
    costume: str
    pose: str
    frame_occupancy: float = 0.42
    character_position: Literal["left", "center", "right"] = "right"

    def validate(self) -> None:
        for value, mapping, name in (
            (self.archetype, ARCHETYPES, "archetype"),
            (self.emotion, EMOTION_MAP, "emotion"),
            (self.costume, COSTUME_MAP, "costume"),
            (self.pose, POSE_MAP, "pose"),
        ):
            if value not in mapping:
                raise ValueError(f"지원하지 않는 {name}: {value}")
        if not 0.25 <= self.frame_occupancy <= 0.50:
            raise ValueError("frame_occupancy는 0.25~0.50만 허용")
        if self.character_position not in OCCUPANCY_PHRASE:
            raise ValueError(f"지원하지 않는 캐릭터 위치: {self.character_position}")


OCCUPANCY_PHRASE = {
    "right": "The mascot occupies the right third of the frame in the foreground",
    "center": "The mascot stands centered in the foreground",
    "left": "The mascot occupies the left third of the frame in the foreground",
}


VisualTextPolicy = Literal["diegetic_decorative", "strict_textless"]


# 신규 archetype의 1차 병렬 검증에서 비문자 보조 모니터가 primary 대체물로
# 산개했다. 기존 7개 규칙은 동결하고, 신규 4개에만 화면형 소품 자체를 금지한다.
SCREENLESS_PRIMARY_SURFACE_ARCHETYPES = frozenset({
    "earnings_stage", "briefing_podium", "real_estate_office", "job_market_hall",
})


# V5의 장식 문자도 프레임 위 UI가 아니라 세트의 일부여야 한다. 이 지시는
# 사실 수치를 AI에게 만들게 하는 용도가 아니며, 검증 수치는 별도 렌더러가
# 나중에 같은 물리 표면 안에서 교체한다.
DIEGETIC_TEXT_GUIDANCE = {
    "port_emergency": (
        "Paint short decorative English stencils only inside the broad flat FRONT panel of the single largest foreground shipping container "
        "nearest the center dock; keep every readable mark wholly inside that one front panel, never on its side wall, end door, roof, or any "
        "other container. Make the wet paint perspective-correct and affected by rain and red beacon light."
    ),
    "retail_shock": (
        "Put short decorative English labels and sample figures only in the built-in receipt window recessed into the upper face of the single "
        "large checkout device; make every mark inherit the device bevel, fluorescent light, and red alert reflection, never on shelf tags or product packaging."
    ),
    "classroom": (
        "Put short decorative English chalk words, arrows, and figures only in the broad central chalk-writing area of the large green "
        "teaching wall; make them dusty chalk integrated with the wall's map outline and diagram marks, never ink on a pinned note or a "
        "digital presentation overlay."
    ),
    "weather_map": (
        "Place short decorative English weather callouts and sample percentages only within the broad central geographic region "
        "of the single curved illuminated map wall; integrate them with map contours, cloud icons, and directional arrows on that same wall. "
        "Warp the lettering with the map perspective and let the cloud, rain, and studio light interact with it."
    ),
    "risk_control_room": (
        "Engrave short decorative English warning words and sample percentages into brass-and-red control plaques, analog gauge faces, and painted floor markings; "
        "make every mark part of the metal, glass, paint, glow, and room perspective."
    ),
    "trade_calculator": (
        "Integrate short decorative English labels, sample figures, and formula fragments into the balance-scale base, printed papers, and glowing wall diagrams; "
        "make them physical ink, engraving, or projected light that follows each prop's perspective."
    ),
    "data_lab": (
        "Embed short decorative English labels, sample figures, and axis ticks into holographic map paths, translucent gauge faces, and console etchings; "
        "make them obey the cyan glow, reflection, depth, and perspective of the physical set."
    ),
    "earnings_stage": (
        "Put short decorative English earnings callouts and sample figures only inside the single broad earnings-briefing surface embedded flush "
        "into the center back wall directly behind the presentation podium; integrate them with the wall illumination, perspective, and chart silhouettes."
    ),
    "briefing_podium": (
        "Put short decorative English policy callouts and one simple diagram only inside the single broad policy-briefing surface embedded flush "
        "into the center back wall immediately behind the central podium; make them inherit the room lighting and perspective."
    ),
    "real_estate_office": (
        "Put short decorative English market callouts and sample figures only on the single broad market-and-loan guidance board fixed flush to the wall "
        "directly behind the consultation desk; make them painted or printed into that board's material and perspective."
    ),
    "job_market_hall": (
        "Put short decorative English employment callouts and one simple chart silhouette only inside the single broad employment-trend guidance board "
        "fixed flush to the wall directly behind the central consultation counter."
    ),
}


def _primary_substitute_ban(scene_type_selection: "ArchetypeSelection | None") -> str:
    """특정 무대에서 primary를 그럴듯한 다른 소품으로 바꾸는 현상을 막는다."""
    if scene_type_selection and scene_type_selection.archetype == "trade_calculator":
        return (
            " For this trade-calculator scene, do not substitute the designated plinth with a freestanding information plaque, "
            "desk display, framed dashboard, separate board, podium sign, or any other standalone panel."
        )
    if scene_type_selection and scene_type_selection.archetype == "risk_control_room":
        return (
            " For this risk-control-room scene, do not substitute the designated gauge dial face with a separate warning plaque, "
            "independent console screen, floating alert panel, desk display, framed dashboard, standalone sign, or any other panel. "
            "Every secondary gauge, warning plaque, console screen, control dial, signal lamp, floor marking, wall indicator, "
            "shipping crate, and closed umbrella must remain non-textual. "
        )
    if scene_type_selection and scene_type_selection.archetype == "weather_map":
        return (
            " For this weather-map scene, do not substitute the designated central map-wall region with a freestanding forecast board, "
            "separate weather card, side monitor, desk display, camera-mounted label, lower-third banner, or independent alert panel. "
            "Every studio camera, tripod, pointer, ceiling spotlight, studio floor device, and every map-wall area outside the designated "
            "central region, including cloud icons, directional arrows, and weather bands, must remain non-textual. "
        )
    if scene_type_selection and scene_type_selection.archetype == "classroom":
        return (
            " For this classroom scene, do not substitute the designated central chalk-writing area with a pinned paper note, framed wall "
            "poster, hanging chart, separate blackboard, desk display, open-book page, or independent teaching card. Every wooden desk, "
            "open book, wooden pointer, green banker lamp, pinned paper note, classroom door, clock, and every teaching-wall area outside "
            "the designated central chalk-writing area, including map silhouettes, arrows, circles, and connected marks, must remain non-textual. "
        )
    if scene_type_selection and scene_type_selection.archetype == "port_emergency":
        return (
            " For this port-emergency scene, the designated primary surface is ONLY the broad flat FRONT panel of the single largest foreground "
            "shipping container nearest the center dock. Never place readable marks on that container's side wall, end door, roof, corner post, "
            "or locking bar. Do not substitute the designated front panel with a dock warning plate, customs sign, cargo manifest, ship-name "
            "marking, crane label, freestanding emergency board, separate shipping card, or independent alert panel. Every other stacked shipping "
            "container, every non-front face of the designated container, cargo-ship hull, harbor-crane beam, red warning beacon, dock surface, "
            "customs sign, wave, storm cloud, lightning strike, and rain streak must remain non-textual. "
        )
    if scene_type_selection and scene_type_selection.archetype == "retail_shock":
        return (
            " For this retail-shock scene, do not substitute the designated recessed receipt window with a shelf price tag, product package, "
            "freestanding total-price card, separate POS display, calculator screen, sale placard, desk display, independent checkout panel, "
            "extra wall display, overhead promotional screen, digital signage, or secondary monitor. "
            "Every product shelf, price tag, package, conveyor-belt item, checkout button, receipt roll, secondary screen, store sign, aisle marker, "
            "and alert light must remain non-textual. "
        )
    if scene_type_selection and scene_type_selection.archetype == "earnings_stage":
        return (
            " For this earnings-stage scene, do not substitute the designated flush wall surface with an independent LED board, podium nameplate, "
            "freestanding slide, side screen, audience badge, camera label, ticker strip, or separate report card. Every podium front, fixed microphone, "
            "broadcast camera, audience seat, ceiling spotlight, stage floor line, and secondary chart silhouette must remain non-textual. "
        )
    if scene_type_selection and scene_type_selection.archetype == "briefing_podium":
        return (
            " For this briefing-podium scene, do not substitute the designated flush wall surface with a podium nameplate, teleprompter, press badge, "
            "microphone logo, flag emblem, freestanding briefing board, side screen, lower-third banner, or floating alert panel. Every podium plaque, "
            "fixed microphone, press seat, camera, ceiling light, flag-color ribbon, floor cable, and secondary screen must remain non-textual. "
        )
    if scene_type_selection and scene_type_selection.archetype == "real_estate_office":
        return (
            " For this real-estate-office scene, do not substitute the designated wall-fixed guidance board with a window listing, desk calculator display, "
            "property sign, sale card, loose paper, clipboard, desk monitor, price tag, or freestanding rate panel. The desk calculator display must remain "
            "completely blank and empty, showing no digits, symbols, labels, bars, chart marks, or pseudo-writing; it is a physical calculator, not a second "
            "information surface. Every consultation desk, loose paper, file folder, house model, window, exterior home, lamp, and desk device must remain non-textual. "
        )
    if scene_type_selection and scene_type_selection.archetype == "job_market_hall":
        return (
            " For this job-market-hall scene, do not substitute the designated wall-fixed guidance board with a job-posting sheet, company logo, queue-ticket "
            "display, resume text, kiosk screen, counter placard, vacancy card, freestanding hiring board, or separate notice cluster. Every consultation counter, "
            "booth divider, queue-ticket machine, resume folder, bag, guide light, job seeker, career icon, and secondary wall notice must remain non-textual. "
            "The queue-ticket machine must be a mechanical paper dispenser with no screen or display, and all resume folders must stay closed with no visible paper face. "
        )
    return ""


def _screenless_nonprimary_contract(scene_type_selection: "ArchetypeSelection | None") -> str:
    """신규 4개에서 primary 외 화면형 소품을 형태 자체로 금지한다."""
    if not scene_type_selection or scene_type_selection.archetype not in SCREENLESS_PRIMARY_SURFACE_ARCHETYPES:
        return ""
    return (
        " Outside the designated primary surface, do not create any monitor, screen, display, dashboard, kiosk, digital signage, "
        "teleprompter, or screen-shaped rectangular information device at all, even when blank or filled only with color blocks. "
        "Use only scene-native physical objects, lighting, material texture, abstract geometry, and non-screen silhouettes for background density. "
    )


def _third_attempt_layout_ban(scene_type_selection: "ArchetypeSelection | None") -> str:
    """P2-F가 두 번 반복된 신규 두 무대의 구체적 화면형 대체물을 막는다."""
    if not scene_type_selection:
        return ""
    if scene_type_selection.archetype == "earnings_stage":
        return (
            " Do not create any additional wall-mounted chart frame, bordered graph panel, or rectangular data display on either side wall, "
            "even without text. Both side walls must remain plain continuous wall material with only lighting, shadow, and non-rectangular texture; "
            "the single central embedded briefing surface is the only chart-bearing wall area. "
        )
    if scene_type_selection.archetype == "job_market_hall":
        return (
            " Do not create any ceiling-mounted or wall-mounted monitor, and the area in front of the consultation counter must not contain any kiosk, "
            "screen-bearing terminal, or digital display of any kind. Keep that area limited to a physical counter edge, closed folders, bags, people, "
            "and a small mechanical paper ticket dispenser without any display. "
        )
    return ""


def _fact_surface_contract(
    spec: SceneSpec,
    scene_type_selection: "ArchetypeSelection | None",
    visual_text_policy: VisualTextPolicy,
) -> str:
    """검증 사실을 장면 속 물리 소품에만 배치하도록 프롬프트 계약을 만든다."""
    if scene_type_selection is None:
        return ""
    if scene_type_selection.archetype != spec.archetype:
        raise ValueError(
            "scene_type archetype 추천과 SceneSpec archetype이 일치하지 않습니다: "
            f"{scene_type_selection.archetype} != {spec.archetype}"
        )
    if scene_type_selection.scene_type == "general":
        return ""
    if not scene_type_selection.physical_surfaces or not scene_type_selection.primary_physical_surface:
        raise ValueError("정보형 씬에는 최소 한 개의 물리 정보 표면이 필요합니다.")

    primary_surface = scene_type_selection.primary_physical_surface
    substitute_ban = _primary_substitute_ban(scene_type_selection)
    screenless_nonprimary_contract = _screenless_nonprimary_contract(scene_type_selection)
    third_attempt_layout_ban = _third_attempt_layout_ban(scene_type_selection)
    nonprimary_surface_types = "gauge, map, placard, document, and console"
    if not screenless_nonprimary_contract:
        nonprimary_surface_types = "gauge, screen, map, placard, document, and console"
    base = (
        f"IN-SCENE FACT-SURFACE CONTRACT: this is a {scene_type_selection.scene_type} scene. "
        f"The only permitted information-bearing prop is {primary_surface}. "
        "Compose one substantial, unobstructed, perspective-correct information area inside that exact prop; it is part of the set, "
        "not an overlay placed on top of the frame. "
        f"Every other {nonprimary_surface_types} must show only needles, color blocks, abstract shapes, "
        "or non-writing material texture: no readable text, letters, numbers, formula fragments, labels, axis ticks, or chart annotations. "
        f"{substitute_ban}{screenless_nonprimary_contract}{third_attempt_layout_ban}"
    )
    if visual_text_policy == "strict_textless":
        return base + (
            "Do not draw text, digits, symbols, chart labels, or factual values there. Instead render a fully finished, "
            "unlabelled physical material surface with subtle non-textual detail and enough calm contrast for later deterministic compositing. "
            "Never create a blank monitor, detached UI card, floating panel, or separate number display."
        )
    return base + (
        "The designated primary prop MUST visibly include at least two or three short, clearly readable decorative English labels "
        "or sample figures, engraved, painted, chalked, printed, or projected directly inside that same physical prop. "
        "Those marks must inherit its material, outline, lighting, occlusion, and perspective. "
        "Never place a number or text in a floating card, detached rectangular UI, separate LCD widget, or pasted-on panel. "
        "AI-drawn marks are decorative only; exact verified facts are composited later by deterministic rendering."
    )


def build_prompt(
    spec: SceneSpec, *, character_position: str | None = None, layout_instruction: str | None = None,
    visual_text_policy: VisualTextPolicy = "diegetic_decorative",
    scene_type_selection: "ArchetypeSelection | None" = None,
) -> str:
    """검증 수치는 후처리로 유지하고, 장식 표기는 선택된 물리 표면에만 요청한다."""
    spec.validate()
    if visual_text_policy not in {"diegetic_decorative", "strict_textless"}:
        raise ValueError(f"Unsupported visual_text_policy: {visual_text_policy}")
    fact_surface_contract = _fact_surface_contract(spec, scene_type_selection, visual_text_policy)
    is_general_scene = bool(scene_type_selection and scene_type_selection.scene_type == "general")
    is_selected_information_scene = bool(scene_type_selection and not is_general_scene)
    archetype = ARCHETYPES[spec.archetype]
    character = f"{MASCOT_STYLE_BIBLE}, {EMOTION_MAP[spec.emotion]}, {COSTUME_MAP[spec.costume]}, {POSE_MAP[spec.pose]}"
    resolved_position = character_position or spec.character_position
    composition = (
        "Premium economic-explainer cartoon illustration. "
        f"{OCCUPANCY_PHRASE[resolved_position]}, "
        "taking up a large but not dominant part of the frame. Clear foreground, midground, and background depth."
    )
    if spec.archetype == "data_lab":
        composition += (
            " For this wide control-room view, show the mascot from hat to shoes at the same full-body scale as the other "
            "economic-explainer scenes; keep the character within the right-side foreground and leave the control room, "
            "map wall, and console visibly spacious around it. Do not use a close portrait crop."
        )
    scene = (
        f"STAGE: {archetype.stage}. KEY PROPS: {archetype.props}. "
        f"LIGHTING: {archetype.lighting}. DECORATIVE DETAIL: {archetype.visual_detail}."
    )
    art_direction = (
        f"{V5_CINEMATIC_CARTOON_STYLE_CONTRACT} "
        "ART STYLE: bold thick black ink outlines, flat cel-shading, high contrast, rich prop density, "
        "theatrical composition, editorial cartoon quality, limited vivid palette. "
        "FRAME CONTINUITY: make one continuous full-bleed illustrated scene from edge to edge. Do not use a split screen, "
        "comic-panel gutter, inset picture, internal frame border, filmstrip, collage, or a large rectangular overlay that "
        "visually divides the composition. Physical props may be detailed, but they must be naturally integrated into one stage."
    )
    if visual_text_policy == "diegetic_decorative" and is_general_scene:
        background_information_density = (
            "BACKGROUND INFORMATION DENSITY: build a fully dressed narrative set, not a simple backdrop. "
            "Use scene-native objects, warning lights, weather, tools, documents, and non-quantitative visual texture. "
            "This general scene does not request numbers, chart ticks, metric displays, or factual data readouts. "
            "Do not leave an empty screen or a blank placeholder."
        )
        exclusions = (
            "DO NOT INCLUDE Korean text, Korean subtitles, a channel logo, watermark, numbers, chart labels, metric displays, "
            "or a generic floating dashboard card. Do not create a detached rectangular UI widget, free-floating data card, "
            "isolated LCD panel, presentation slide, or separate POS-style number screen. "
            "Do not make a split screen, comic panels, inset images, picture-in-picture windows, framing gutters, or a collage. "
            "The gold coin mascot is the only anthropomorphic character; all props must be inanimate."
        )
    elif visual_text_policy == "diegetic_decorative" and is_selected_information_scene:
        primary_surface = scene_type_selection.primary_physical_surface
        substitute_ban = _primary_substitute_ban(scene_type_selection)
        screenless_nonprimary_contract = _screenless_nonprimary_contract(scene_type_selection)
        third_attempt_layout_ban = _third_attempt_layout_ban(scene_type_selection)
        nonprimary_surface_types = "gauges, maps, placards, documents, signs, and consoles"
        if not screenless_nonprimary_contract:
            nonprimary_surface_types = "gauges, screens, maps, placards, documents, signs, and consoles"
        background_information_density = (
            "BACKGROUND INFORMATION DENSITY: build a fully dressed explanatory set, not a simple backdrop. "
            f"Make {primary_surface} the single visual-information focal prop. It MUST visibly contain at least two or three short, "
            "clearly readable decorative English labels or sample figures, plus a simple chart silhouette or diagram line, all as "
            "material integrated into that exact prop. "
            f"Every surface OTHER THAN {primary_surface} must remain visually rich only through needles, color blocks, signal lights, "
            "abstract geometry, maps without writing, and non-writing material texture. Do not distribute labels across multiple props. "
            "All AI-drawn writing and values are atmospheric decoration only, never factual information. "
            f"{screenless_nonprimary_contract}{third_attempt_layout_ban}"
            "Never leave an empty screen or a blank placeholder."
        )
        exclusions = (
            "DO NOT INCLUDE Korean text, Korean subtitles, a channel logo, watermark, or a generic floating dashboard card. "
            "Do not create a detached rectangular UI widget, free-floating data card, isolated LCD panel, presentation slide, "
            "or a separate POS-style number screen placed on top of the scene. "
            f"{substitute_ban}{screenless_nonprimary_contract}{third_attempt_layout_ban}"
            f"{primary_surface} MUST contain two or three short, clearly readable decorative English labels or sample figures. "
            f"All {nonprimary_surface_types} OTHER THAN {primary_surface} must show only needles, "
            "color blocks, abstract shapes, or non-writing material texture: "
            "no readable text, letters, numbers, formula fragments, labels, axis ticks, or chart annotations on them. "
            "Do not make empty monitors, empty boards, empty signboards, blank title cards, or layout-guide frames. "
            "Do not make a split screen, comic panels, inset images, picture-in-picture windows, framing gutters, or a collage. "
            "The gold coin mascot is the only anthropomorphic character: all calculators, robots, screens, products, "
            "animals, and background props must be inanimate and must not have eyes, faces, limbs, or expressions. "
            "The scene must be complete, busy, and meaningful."
        )
    elif visual_text_policy == "diegetic_decorative":
        background_information_density = (
            "BACKGROUND INFORMATION DENSITY: build a fully dressed explanatory set, not a simple backdrop. "
            "Include populated analog gauges, labeled control dials, signal lights, dense diagram lines, maps, charts, "
            "stacked documents, warning placards, and integrated prop details. Use short English labels, sample figures, "
            "simple equations, chart ticks, and diagram annotations as hand-drawn decorative scene material. "
            f"DIEGETIC TEXT PLACEMENT: {DIEGETIC_TEXT_GUIDANCE[spec.archetype]} "
            "All writing must be painted, chalked, engraved, printed, projected, or physically mounted onto an existing prop. "
            "It must share that prop's material, outline, illumination, occlusion, and perspective; it must not look pasted on. "
            "All AI-drawn writing and values are atmospheric decoration only, never factual information. "
            "Every board, gauge, map, checkout prop, and signboard must already contain dense meaningful visual detail; "
            "never leave an empty screen or a blank placeholder."
        )
        exclusions = (
            "DO NOT INCLUDE Korean text, Korean subtitles, a channel logo, watermark, or a generic floating dashboard card. "
            "Do not create a detached rectangular UI widget, free-floating data card, isolated LCD panel, presentation slide, "
            "or a separate POS-style number screen placed on top of the scene. Typography may exist only as a naturally integrated "
            "part of a map, plaque, gauge, product package, sign, container, chalk wall, or other physical stage prop. "
            "Do not make empty monitors, empty boards, empty signboards, blank title cards, or layout-guide frames. "
            "Do not make a split screen, comic panels, inset images, picture-in-picture windows, framing gutters, or a collage. "
            "The gold coin mascot is the only anthropomorphic character: all calculators, robots, screens, products, "
            "animals, and background props must be inanimate and must not have eyes, faces, limbs, or expressions. "
            "The scene must be complete, busy, and meaningful."
        )
    else:
        background_information_density = (
            "BACKGROUND INFORMATION DENSITY: build a fully dressed explanatory set, not a simple backdrop. "
            "Include color-only control dials, clusters of signal lights, dense non-linguistic connection lines, "
            "abstract bar and curve silhouettes without axes, map markers, layered physical props, and colored light shapes. "
            "Every visual surface must contain meaningful non-linguistic detail rather than an empty placeholder."
        )
        exclusions = (
            "DO NOT INCLUDE any visible typographic mark. The image must contain no writing-like strokes anywhere: "
            "no readable or pseudo-readable words, glyphs, numerals, captions, branding marks, or watermarks. "
            "Do not draw Roman letters such as X or x, variable symbols, equation fragments, equals signs, plus or minus signs, "
            "colons, axis labels, or any chart annotation that can be read as writing. "
            "Do not make a split screen, comic panels, inset images, picture-in-picture windows, framing gutters, or a collage. "
            "The scene must be complete, busy, and meaningful."
        )
    reserve = (
        "Keep a slim lower band and a small upper-right corner free of foreground subjects and high-contrast details. "
        "Show only continuous background texture in those areas. Do not place the mascot's face or hands there."
    )
    return " ".join((
        f"<character> {character} </character>", f"<composition> {composition} </composition>",
        f"<scene> {scene} </scene>", f"<art_direction> {art_direction} </art_direction>",
        f"<background_information_density> {background_information_density} </background_information_density>",
        f"<fact_surface_contract> {fact_surface_contract} </fact_surface_contract>" if fact_surface_contract else "",
        f"<reserve> {reserve} </reserve>",
        f"<layout_contract> {layout_instruction} </layout_contract>" if layout_instruction else "",
        f"<exclusions> {exclusions} </exclusions>",
    ))


BENCHMARK_SCENES = [
    SceneSpec("bench_01_port", "port_emergency", "alarm", "safety_vest", "alarmed_run", character_position="right"),
    SceneSpec("bench_02_retail", "retail_shock", "surprise", "analyst", "calculator_hold", character_position="left"),
    SceneSpec("bench_03_classroom", "classroom", "happy", "professor", "point_left", character_position="right"),
    SceneSpec("bench_04_classroom2", "classroom", "confidence", "professor", "point_left", character_position="left"),
    SceneSpec("bench_05_weather", "weather_map", "explain", "reporter", "present", character_position="right"),
    SceneSpec("bench_06_risk", "risk_control_room", "confidence", "formal", "present", character_position="center"),
    SceneSpec("bench_07_trade", "trade_calculator", "confidence", "vest", "think", character_position="left"),
    SceneSpec("bench_08_datalab", "data_lab", "explain", "reporter", "present", character_position="center"),
]

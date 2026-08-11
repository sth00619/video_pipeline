"""V5 정보 장면의 무문자 이미지 프롬프트를 구성한다."""
from __future__ import annotations

from app.utils.art_direction import SHARED_STYLE_LOCK_PROMPT, SHARED_MASCOT_STYLE_LOCK_PROMPT, ARCHETYPE_TO_COSTUME

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.v5.scene.scene_type_archetypes import ArchetypeSelection


MASCOT_STYLE_BIBLE = (
    "a friendly anthropomorphic GOLD COIN mascot character with a perfectly round golden face and embossed rim, "
    "big expressive cartoon eyes with white highlights, rosy pink cheeks, and a warm smile or matching expression. "
    "Keep the exact same round coin silhouette, rim thickness, face proportions, eye shape, iris style, eyebrows, "
    "and thick black ink-line weight as the fixed channel mascot in every scene. Never restyle the mascot as a flat token, "
    "a different cartoon character, a document, a card, a sheet of paper, a tablet, a phone, a monitor, a rectangle, "
    "or a different illustration medium"
)

# 첫 번째 참조 이미지는 화풍 참고가 아니라 캐릭터의 고정 모델시트다.
MASCOT_IDENTITY_LOCK = (
    "CHARACTER IDENTITY LOCK: the first supplied character reference image is the authoritative model sheet. "
    "Reproduce its exact round coin silhouette, embossed rim, warm gold material, thick dark outer contour, "
    "large brown oval eyes with two white highlights each, thick curved eyebrows, small rounded nose, rosy circular cheeks, "
    "and compact navy-suit body proportions. Keep these facial traits identical in every scene. "
    "Do not add eyelashes, change the eye shape or iris style, make the face flatter or more 3D-rendered, "
      "or reinterpret the mascot as a different character. Only the mouth, eyebrows, and arm pose may change to express scene emotion. "
    "Both visible hands must wear the same white cartoon gloves from the character reference; never show bare golden hands. "
    "Rosy circular cheeks remain visible even for worried or alarmed expressions. "
    "The character perimeter uses only one dark brown or black ink outline: absolutely no white sticker-cutout border, white halo, or white stroke around the hat, coin, suit, limbs, or shoes."
)


# 기존 8종 승인본의 미감을 현재 실전 경로에서도 명시적으로 고정한다. 이 계약은
# 사실값·수치의 생성 지시가 아니라 선·명암·무대 밀도에 관한 그림체 계약이다.
V5_STYLE_CONTRACT_VERSION = "2026-08-03-r4-korean-nonnumeric-three-mode-v1"
BASE_STYLE_LOCK_PROMPT = SHARED_STYLE_LOCK_PROMPT

# 2026-08-04: 헤드웨어 락을 "항상 갈색 페도라"에서 "의상별 헤드웨어 1개만,
# 절대 두 개를 겹치지 않음"으로 바꿨다. 경제사냥꾼 채널은 씬의 역할(교수=학사모,
# 사회자=민머리+턱시도 등)에 맞춰 모자를 바꾸므로, 페도라를 모든 씬에 강제하면
# 그 채널 문법을 재현할 수 없다. 대신 실제 헤드웨어 지정은 COSTUME_MAP 각 항목이
# 전담하고, 여기서는 "정확히 하나만" 규칙만 고정한다. 얼굴·손·발 정체성 락
# (MASCOT_IDENTITY_LOCK)은 이 변경과 무관하게 그대로 유지된다.
MASCOT_STYLE_LOCK_PROMPT = SHARED_MASCOT_STYLE_LOCK_PROMPT

STYLE_LOCK_PROMPT = f"{BASE_STYLE_LOCK_PROMPT} {MASCOT_STYLE_LOCK_PROMPT}"

# 기존 상수 이름을 사용하는 호출부의 호환성을 유지한다.
STYLE_LOCK_PROMPT += (
    " Exactly one headwear item per scene, exactly as the costume describes it. Never stack two headwear "
    "pieces, and never substitute a different headwear than the one the costume names."
)
V5_CINEMATIC_CARTOON_STYLE_CONTRACT = STYLE_LOCK_PROMPT

CHARACTER_FRAME_CONTRACT = (
    "Place the gold coin mascot in the right-side foreground, while the broad background prop "
    "(chalkboard / screen / map / board) fills the left side of the frame. "
    "Character is full-body visible from head to shoes and occupies no more than 35% of the total frame width; "
    "the primary explanatory prop occupies at least 60% of the frame. Do not use a close portrait crop or an oversized mascot head. "
    "The character wears exactly the single headwear item named in its costume description below — never a second hat, "
    "never a mix of two headwear pieces, and never a different headwear than the one the costume names. "
    "Character expression must match scene tone: down market = worried/sweating expression, "
    "up market = confident/happy expression, neutral = calm/explaining expression."
)

# 정보형 data_lab은 7/30 벤치마크의 짙고 촘촘한 무대 미감을 기준으로 삼는다.
# 검증 수치의 위치·내용을 AI에게 맡기는 지시가 아니라, 배경의 재질과 밀도를 고정하는 계약이다.
CHARACTER_FRAME_CONTRACT += (
    " Exactly one headwear item total, matching the costume description exactly; no stacked or duplicate headwear."
)

DATA_LAB_BENCHMARK_VISUAL_TREATMENT = (
    " DATA-LAB BENCHMARK VISUAL TREATMENT: render a tactile hand-drawn broadcast analysis studio with ceiling spotlights, "
    "visible cameras, cables, analog console details, and one broad curved presentation wall physically built into the set. "
    "Use warm amber key light balanced with restrained cool-blue fill, thick bold black ink outlines, hard shadow edges, and flat high-contrast cel shading. "
    "The presentation wall remains the only clear information surface, while the surrounding set stays busy through physical studio "
    "equipment and non-writing material detail. Do not turn this into a neon sci-fi control room, a glossy 3D fintech dashboard, "
    "a minimal vector infographic, or broad empty wall space."
)

EMOTION_MAP = {
    "surprise": "shocked wide-eyed expression, open mouth, sweat drop",
    "happy": "bright cheerful smile, sparkling eyes, one hand waving",
    "explain": "calm friendly explaining expression, gentle smile",
    "confidence": "smug confident half-lidded eyes, subtle smirk",
    "concern": "worried frightened face, spiral or wide eyes, sweat drops",
    "alarm": "panicked alarmed face, mouth open shouting",
}
# 07 문서(경제사냥꾼 심층분석) §1의 8종 의상 관찰을 반영한다. 기존 6종은
# 페도라를 유지하고(브랜드 일관성 우선), 신규 2종(professor의 학사모 교체 포함
# 총 3곳)은 채널 관찰 그대로 헤드웨어를 역할에 맞게 바꾼다. "no fedora" 절은
# 위 CHARACTER_FRAME_CONTRACT/STYLE_LOCK_PROMPT의 "정확히 하나만" 규칙과
# 결합해, 모델이 페도라와 새 헤드웨어를 동시에 그리는 것을 막는다.
COSTUME_MAP = {
    "analyst": "wearing exactly one brown fedora hat as its only headwear, and a navy blue suit with white shirt and tie, with an optional call-center headset",
    "professor": "wearing exactly one black graduation mortarboard cap as its only headwear (no fedora), a brown tweed blazer, and round glasses, holding a wooden pointer stick",
    "reporter": "wearing exactly one brown fedora hat as its only headwear, and a navy TV-anchor suit",
    "formal": "wearing exactly one brown fedora hat as its only headwear, and a navy blue suit with white shirt and tie, holding a cane",
    "safety_vest": "wearing exactly one yellow hard hat as its only headwear (no fedora), and a navy blue suit under a reflective yellow safety vest",
    "vest": "wearing exactly one brown fedora hat as its only headwear, and a navy blue suit with white shirt and tie",
    "tuxedo_host": "bare-headed with no hat of any kind (no fedora), wearing a black tuxedo jacket with a red bow tie, holding a golden cane",
    "architect_planner": "wearing exactly one yellow hard hat as its only headwear (no fedora), a brown tool belt over the navy suit, and holding a drafting compass",
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
        "a stately trade calculation chamber centered on one large brass balance scale mounted on an engraved stone plinth",
        "one large brass balance scale, its broad engraved front plinth, and a small stack of closed ledger books",
        "dark navy chamber light with focused amber spotlight and restrained red-alert rim light",
        "engraved metal texture, balance-chain detail, and non-writing etched directional marks only on the scale setting",
    ),
    "data_lab": Archetype(
        "a tactile broadcast analysis studio with one broad curved presentation wall, cameras, and an analog control console",
        "a physical illuminated presentation mural with non-writing line and bar silhouettes, studio cameras on tripods, cable bundles, analog gauges, and a desk microphone",
        "warm amber studio spotlights with restrained cool-blue fill light",
        "painted chart strokes, practical studio equipment, cable lines, analog dials, and color-only explanatory marks",
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
    # earnings_stage: 기업실적·분기발표·EPS·배당 서사 전용 무대
    # briefing_podium과 달리 금융 실적 발표에 특화된 기업용 연단 + 무대 조명을 사용한다.
    "earnings_stage": Archetype(
        "a formal corporate quarterly earnings announcement stage with one broad results-presentation mural embedded flush into the center back wall behind an executive podium and desk",
        "an executive desk, a central branded podium without real logos, broadcast cameras on tripods, overhead stage spotlights, investor-seating rows, floor microphone stands, and cable bundles",
        "bright professional stage lighting with focused warm key spotlights, cool-blue fill on the results-mural surface, and subtle directional financial-indicator glow from floor-mounted strips",
        "non-writing financial chart silhouettes, color-coded bar-outline shapes, rising-or-falling directional arrows without numbers, podium trim details, and floor cable lines",
    ),
}


@dataclass
class SceneSpec:
    scene_id: str
    archetype: str
    emotion: str
    costume: str
    pose: str
    frame_occupancy: float = 0.35
    character_position: Literal["left", "center", "right"] = "right"
    character_required: bool = True

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
    "right": "The mascot occupies only the far-right 35 percent of the frame in the foreground, full body visible from hat to shoes",
    "center": "The mascot stands centered in the foreground",
    "left": "The mascot occupies the left third of the frame in the foreground",
}


VisualTextPolicy = Literal["diegetic_decorative", "strict_textless", "script_captioned"]


PROP_SURFACE_MAP: dict[str, str] = {
    "weather_map": "large illuminated weather-map wall behind the mascot",
    "classroom": "broad central green chalkboard behind the mascot",
    "port_emergency": "broad painted front face of the single largest foreground shipping container nearest the center dock",
    "briefing_podium": "broad curved presentation wall behind the podium",
    "trade_calculator": "broad engraved front plinth directly beneath the brass balance scale's central pillar",
    "data_lab": "broad curved broadcast-analysis wall on the left side of the studio",
    "risk_control_room": "single large central analog gauge dial face embedded at eye level in the curved operations wall",
    "retail_shock": "large checkout price board built into the supermarket counter",
    "real_estate_office": "large market guidance board behind the consultation desk",
    "job_market_hall": "large employment-trend board behind the consultation counter",
}

MANDATORY_TEXT_EMBED_SUFFIX = (
    "The text '{caption}' is PHYSICALLY PART OF THE {surface} — it looks like it was printed, painted, or written ON the physical surface, "
    "not floating in mid-air, not a separate text layer, not a sticker placed on top. "
    "It is physically part of that prop and has the same material texture and lighting as the {surface} around it."
)


def _build_prop_prompt(archetype: str, caption_en: str, direction: str, script_visuals: str = "") -> str:
    """대본 키워드가 소품 표면에 직접 생성되도록 프롬프트를 만든다."""
    if not caption_en or any(character.isdigit() for character in caption_en):
        raise ValueError("소품 문구는 숫자 없는 영어 대본 키워드여야 합니다.")
    surface = PROP_SURFACE_MAP[archetype]
    direction_detail = {
        "down": "a bold BLUE downward trend arrow and descending non-numeric bar-and-line chart",
        "up": "a bold RED upward trend arrow and rising non-numeric bar-and-line chart",
        "neutral": "a balanced amber sideways trend line with connecting concept arrows",
    }[direction]
    mandatory_suffix = MANDATORY_TEXT_EMBED_SUFFIX.format(caption=caption_en, surface=surface)
    return (
        f"PROP SURFACE — {surface}. The exact English words '{caption_en}' are written DIRECTLY ON THE {surface.upper()} surface. "
        f"{mandatory_suffix} Put {direction_detail} directly below the words on that same surface. "
        f"SCRIPT MEANING VISUALS: {script_visuals or 'use non-textual scene-native explanatory objects'}. "
        "Render these as physical illustrations, object silhouettes, arrows, and non-numeric chart shapes integrated into this same archetype; "
        "they explain the script without adding labels, values, or a second text-bearing prop. "
        "Show the exact caption exactly ONCE, only on the named primary surface. All secondary consoles, screens, gauges, signs, containers, "
        "and background props must contain no readable words and no partial repetition of any caption word. "
        "The prop itself is the message. No Korean characters, no numerals, no other English words, no brand marks, and no floating text anywhere else in the image."
    )


# 신규 archetype의 1차 병렬 검증에서 비문자 보조 모니터가 primary 대체물로
# 산개했다. 기존 7개 규칙은 동결하고, 신규 4개에만 화면형 소품 자체를 금지한다.
SCREENLESS_PRIMARY_SURFACE_ARCHETYPES = frozenset({
    "briefing_podium", "real_estate_office", "job_market_hall",
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
            "unlabelled physical material surface with dense non-numeric analytical detail: abstract grid lines, unlabeled rising or falling "
            "traces, pie-slice color shapes, arrows, world-map silhouettes, and decorative equation-like marks that are not readable characters. "
            "Keep enough calm contrast for later deterministic compositing. "
            "Never create a blank monitor, detached UI card, floating panel, or separate number display."
        )
    if visual_text_policy == "script_captioned":
        return base + (
            "Only the exact script-derived English caption named in the PROP SURFACE section may appear on this primary prop. "
            "Do not add any other readable words, figures, labels, or values."
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
    semantic_direction: str = "neutral",
    semantic_caption: str = "",
    semantic_visual_brief: str = "",
    locale_visual_brief: str = "",
) -> str:
    """검증 수치는 후처리로 유지하고, 장식 표기는 선택된 물리 표면에만 요청한다."""
    spec.validate()
    if visual_text_policy not in {"diegetic_decorative", "strict_textless", "script_captioned"}:
        raise ValueError(f"Unsupported visual_text_policy: {visual_text_policy}")
    if semantic_direction not in {"down", "up", "neutral"}:
        raise ValueError(f"Unsupported semantic_direction: {semantic_direction}")
    fact_surface_contract = _fact_surface_contract(spec, scene_type_selection, visual_text_policy)
    is_general_scene = bool(scene_type_selection and scene_type_selection.scene_type == "general")
    is_selected_information_scene = bool(scene_type_selection and not is_general_scene)
    priority_prop_instruction = ""
    if visual_text_policy == "script_captioned":
        if is_selected_information_scene:
            priority_prop_instruction = _build_prop_prompt(
                spec.archetype, semantic_caption, semantic_direction, semantic_visual_brief,
            )
        else:
            visual_text_policy = "strict_textless"
            priority_prop_instruction = ""
    archetype = ARCHETYPES[spec.archetype]
    if spec.character_required:
        character = f"{MASCOT_STYLE_BIBLE}, {MASCOT_IDENTITY_LOCK}, {EMOTION_MAP[spec.emotion]}, {COSTUME_MAP[spec.costume]}, {POSE_MAP[spec.pose]}"
        composition = (
            "Premium economic-explainer cartoon illustration. "
            f"{CHARACTER_FRAME_CONTRACT} "
            "Keep clear foreground, midground, and background depth around the one designated physical explanatory prop."
        )
        art_direction = V5_CINEMATIC_CARTOON_STYLE_CONTRACT
    else:
        character = (
            "NO mascot and NO anthropomorphic character in this scene. Tell the script meaning through the environment, "
            "physical objects, lighting, scale, and action only."
        )
        composition = (
            "Premium wide situational economic-explainer cartoon illustration with clear foreground, midground, and background depth. "
            "Give the environment and script-specific physical metaphor the full frame; do not reserve a character-shaped empty area."
        )
        art_direction = (
            f"{BASE_STYLE_LOCK_PROMPT} NO mascot, no gold coin person, no face on any object, and no anthropomorphic props."
        )
    if spec.archetype == "data_lab" and spec.character_required:
        composition += (
            " For this wide broadcast-analysis-studio view, show the mascot from hat to shoes at the same full-body scale as the other "
            "economic-explainer scenes; keep the character within the right-side foreground and leave the curved presentation wall, "
            "cameras, and console visibly spacious around it. Do not use a close portrait crop."
        )
    scene = (
        "Use a distinct camera angle, prop arrangement, and lighting balance for this scene. "
        f"STAGE: {archetype.stage}. KEY PROPS: {archetype.props}. "
        f"LIGHTING: {archetype.lighting}. DECORATIVE DETAIL: {archetype.visual_detail}. "
        f"LOCAL CONTEXT: {locale_visual_brief or 'use a contextually specific real-world setting rather than a generic Western storefront or office'}."
    )
    if spec.archetype == "weather_map":
        scene += (
            " The one large curved map wall is the only map or information surface in this studio. "
            "Do not add any small map screen, chart card, dashboard, control-panel display, inset forecast window, or mini infographic anywhere else."
        )
    if spec.archetype == "data_lab" and is_selected_information_scene:
        art_direction += DATA_LAB_BENCHMARK_VISUAL_TREATMENT
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
        "If a mascot is present it is the only anthropomorphic character; all props must be inanimate."
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
            f"Make {primary_surface} the single visual-information focal prop. "
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
            f"All {nonprimary_surface_types} OTHER THAN {primary_surface} must show only needles, "
            "color blocks, abstract shapes, or non-writing material texture: "
            "no readable text, letters, numbers, formula fragments, labels, axis ticks, or chart annotations on them. "
            "Do not make empty monitors, empty boards, empty signboards, blank title cards, or layout-guide frames. "
            "Do not make a split screen, comic panels, inset images, picture-in-picture windows, framing gutters, or a collage. "
        "If a mascot is present it is the only anthropomorphic character: all calculators, robots, screens, products, "
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
    elif visual_text_policy == "script_captioned":
        background_information_density = (
            "BACKGROUND INFORMATION DENSITY: build a fully dressed explanatory set, not a simple backdrop. "
            f"Use this script-meaning visual brief: {semantic_visual_brief or 'physical charts, maps, analog gauges, arrows, and color blocks'}. "
            "Use physical charts, maps, analog gauges, arrows, color blocks, light signals, and layered scene-native props. "
            "Do not add a second information-bearing prop or borrow objects from another archetype setting."
        )
        exclusions = (
            "DO NOT INCLUDE Korean text, Korean subtitles, any numeral, factual value, channel logo, watermark, generic floating dashboard card, "
            "detached UI widget, isolated LCD card, presentation slide, split screen, comic panel, inset image, picture-in-picture window, or collage. "
            "If a mascot is present it is the only anthropomorphic character; every other prop must be inanimate."
        )
    else:
        primary_surface = scene_type_selection.primary_physical_surface if is_selected_information_scene else "the main stage prop"
        direction_visual = {
            "down": "a clear descending non-numeric trend line and downward arrow",
            "up": "a clear rising non-numeric trend line and upward arrow",
            "neutral": "a balanced non-numeric trend line and connecting arrows",
        }[semantic_direction]
        background_information_density = (
            "BACKGROUND INFORMATION DENSITY: build a fully dressed explanatory set, not a simple backdrop. "
            "Include color-only control dials, clusters of signal lights, dense non-linguistic connection lines, "
            "abstract bar and curve silhouettes without axes, map markers, layered physical props, and colored light shapes. "
            f"Make {primary_surface} visibly broad, flat, and unobstructed in the left-side set. On that same physical surface, compose {direction_visual} "
            "and leave its upper-middle area visually calm for the deterministic caption compositor. "
            "Every visual surface must contain meaningful non-linguistic detail rather than an empty placeholder."
        )
        exclusions = (
            "DO NOT INCLUDE any visible typographic mark. The image must contain no writing-like strokes anywhere: "
            "no readable or pseudo-readable words, glyphs, numerals, captions, branding marks, or watermarks. "
            "Do not draw Roman letters such as X or x, variable symbols, equation fragments, equals signs, plus or minus signs, "
            "colons, axis labels, or any chart annotation that can be read as writing. "
            "The primary surface must remain a physical wall, board, map, gauge, container face, or console surface—never a floating UI card. "
            "Do not make a split screen, comic panels, inset images, picture-in-picture windows, framing gutters, or a collage. "
            "The scene must be complete, busy, and meaningful."
        )
    reserve = (
        "Keep a slim lower band and a small upper-right corner free of foreground subjects and high-contrast details. "
        "Show only continuous background texture in those areas. Do not place a mascot's face or hands there when a mascot is required."
    )
    return " ".join((
        f"<prop_surface_priority> {priority_prop_instruction} </prop_surface_priority>" if priority_prop_instruction else "",
        f"<character> {character} </character>", f"<composition> {composition} </composition>",
        f"<scene> {scene} </scene>", f"<art_direction> {art_direction} </art_direction>",
        f"<background_information_density> {background_information_density} </background_information_density>",
        f"<semantic_surface> {semantic_caption or 'non-textual'} physical prop surface with {semantic_direction} direction </semantic_surface>",
        f"<script_meaning_visuals> {semantic_visual_brief or 'non-textual scene-native objects'} </script_meaning_visuals>",
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

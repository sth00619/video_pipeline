"""V5 정보 장면의 무문자 이미지 프롬프트를 구성한다."""
from __future__ import annotations

from dataclasses import dataclass


MASCOT_STYLE_BIBLE = (
    "a friendly anthropomorphic GOLD COIN mascot character, round gold coin body with an embossed rim, "
    "expressive cartoon face, large round eyes with visible white sclera, small confident smile, "
    "white four-finger cartoon gloves, short stubby legs with brown shoes, thick clean black ink outline, "
    "flat cel-shading, warm rim light"
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
        "a large chunky checkout device with color buttons, a conveyor belt, a friendly robot cashier",
        "bright clean fluorescent store lighting, a red alert glow around the checkout device",
        "product silhouettes, alert-color light rings, and color-coded price blocks without glyphs",
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
    "split_stage": Archetype(
        "a dramatic theater stage split into a dark-red left half and a bright-golden right half by a center line",
        "a cracked wooden crate on the left, a golden protective umbrella on the right, red lightning bolts, sparkles",
        "harsh red spotlight on the left, warm golden spotlight on the right, theatrical stage haze",
        "contrasting red and gold color fields, lightning-shaped accents, and spark particles",
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
}


@dataclass
class SceneSpec:
    scene_id: str
    archetype: str
    emotion: str
    costume: str
    pose: str
    frame_occupancy: float = 0.42

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


OCCUPANCY_PHRASE = {
    "right": "The mascot occupies the right third of the frame in the foreground",
    "center": "The mascot stands centered in the foreground",
    "left": "The mascot occupies the left third of the frame in the foreground",
}


def build_prompt(spec: SceneSpec, *, character_position: str = "right") -> str:
    """검증 수치는 후처리만 사용하고 AI에는 무문자 배경만 요청한다."""
    spec.validate()
    archetype = ARCHETYPES[spec.archetype]
    character = f"{MASCOT_STYLE_BIBLE}, {EMOTION_MAP[spec.emotion]}, {COSTUME_MAP[spec.costume]}, {POSE_MAP[spec.pose]}"
    composition = (
        "Premium economic-explainer cartoon illustration. "
        f"{OCCUPANCY_PHRASE.get(character_position, OCCUPANCY_PHRASE['right'])}, "
        "taking up a large but not dominant part of the frame. Clear foreground, midground, and background depth."
    )
    scene = (
        f"STAGE: {archetype.stage}. KEY PROPS: {archetype.props}. "
        f"LIGHTING: {archetype.lighting}. DECORATIVE DETAIL: {archetype.visual_detail}."
    )
    art_direction = (
        "ART STYLE: bold thick black ink outlines, flat cel-shading, high contrast, rich prop density, "
        "theatrical composition, editorial cartoon quality, limited vivid palette."
    )
    background_information_density = (
        "BACKGROUND INFORMATION DENSITY: build a fully dressed explanatory set, not a simple backdrop. "
        "Include color-only control dials, clusters of signal lights, dense non-linguistic connection lines, "
        "abstract bar and curve silhouettes without axes, map markers, layered physical props, and colored light shapes. "
        "Every visual surface must contain meaningful non-linguistic detail rather than an empty placeholder."
    )
    reserve = (
        "Keep a slim lower band and a small upper-right corner free of foreground subjects and high-contrast details. "
        "Show only continuous background texture in those areas. Do not place the mascot's face or hands there."
    )
    exclusions = (
        "DO NOT INCLUDE any visible typographic mark. The image must contain no writing-like strokes anywhere: "
        "no readable or pseudo-readable words, glyphs, numerals, captions, branding marks, or watermarks. "
        "The scene must be complete, busy, and meaningful."
    )
    return " ".join((
        f"<character> {character} </character>", f"<composition> {composition} </composition>",
        f"<scene> {scene} </scene>", f"<art_direction> {art_direction} </art_direction>",
        f"<background_information_density> {background_information_density} </background_information_density>",
        f"<reserve> {reserve} </reserve>", f"<exclusions> {exclusions} </exclusions>",
    ))


BENCHMARK_SCENES = [
    SceneSpec("bench_01_port", "port_emergency", "alarm", "safety_vest", "alarmed_run"),
    SceneSpec("bench_02_retail", "retail_shock", "surprise", "analyst", "calculator_hold"),
    SceneSpec("bench_03_classroom", "classroom", "happy", "professor", "point_left"),
    SceneSpec("bench_04_classroom2", "classroom", "confidence", "professor", "point_left"),
    SceneSpec("bench_05_weather", "weather_map", "explain", "reporter", "present"),
    SceneSpec("bench_06_split", "split_stage", "confidence", "formal", "present"),
    SceneSpec("bench_07_trade", "trade_calculator", "confidence", "vest", "think"),
    SceneSpec("bench_08_datalab", "data_lab", "explain", "reporter", "present"),
]

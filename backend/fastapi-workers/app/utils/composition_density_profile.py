"""레퍼런스 배경 관찰을 archetype별 구성 밀도 계약으로 변환한다.

이 모듈은 문구나 금융 수치를 만들지 않는다. 이미지 모델이 장면을 비워 두지
않도록 근경·중경·원경과 비문자 소품의 최소 구성을 지시하며, 기존 텍스트 계약은
독립된 승인 목록과 결정론 렌더 경로에 그대로 남긴다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CompositionDensityProfile:
    """하나의 무대를 채우는 최소 구성과 텍스트 표면 경계를 설명한다."""

    id: str
    reference_background_type: str
    min_background_elements: int
    required_depth_layers: tuple[str, ...]
    foreground_elements: tuple[str, ...]
    midground_elements: tuple[str, ...]
    background_elements: tuple[str, ...]
    min_information_surfaces: int
    color_contrast_rule: str
    text_surface_anchors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "required_depth_layers",
            "foreground_elements",
            "midground_elements",
            "background_elements",
            "text_surface_anchors",
        ):
            value[key] = list(value[key])
        return value


_DEPTH = ("foreground", "midground", "background")


def _profile(
    identifier: str,
    reference_type: str,
    minimum: int,
    foreground: tuple[str, ...],
    midground: tuple[str, ...],
    background: tuple[str, ...],
    surfaces: int,
    color: str,
    anchors: tuple[str, ...],
) -> CompositionDensityProfile:
    return CompositionDensityProfile(
        id=identifier,
        reference_background_type=reference_type,
        min_background_elements=minimum,
        required_depth_layers=_DEPTH,
        foreground_elements=foreground,
        midground_elements=midground,
        background_elements=background,
        min_information_surfaces=surfaces,
        color_contrast_rule=color,
        text_surface_anchors=anchors,
    )


# 69개 레퍼런스 표본의 배경 유형 분포를 현재 11개 운영 archetype에 연결했다.
# 숫자는 화면 속 글자 수가 아니라 서로 구분 가능한 장면 고유 소품·장치 묶음의
# 보수적 하한이다. 임의 모니터나 표지판을 늘려 수를 채우지 못하도록 프롬프트에서
# 비문자·장면 고유 요소로 제한한다.
COMPOSITION_DENSITY_PROFILES: dict[str, CompositionDensityProfile] = {
    "port_emergency": _profile(
        "port_emergency", "market_news_crisis+factory_construction", 7,
        ("wet dock hardware", "one narration-essential cargo or warning prop"),
        ("stacked containers", "warning beacons", "working crane structure"),
        ("cargo ship silhouette", "storm sky or distant port lights"),
        1, "cool storm blues with localized red warning light and one warm focal accent",
        ("container face", "dock warning plate", "customs sign"),
    ),
    "retail_shock": _profile(
        "retail_shock", "physical_economic_metaphor", 6,
        ("checkout device", "conveyor or basket prop"),
        ("dense product shelf clusters", "price-change mechanism without writing"),
        ("store aisle depth", "overhead retail lighting"),
        1, "clean retail neutrals with a strong red or green causal accent",
        ("receipt window", "shelf price tag", "product package face"),
    ),
    "classroom": _profile(
        "classroom", "classroom_briefing", 6,
        ("desk edge or lectern", "pointer, book, or teaching prop"),
        ("large teaching wall", "banker lamp or pinned-note cluster"),
        ("desk rows", "bookshelf or architectural classroom detail"),
        1, "warm wood and amber light against a saturated green or navy teaching surface",
        ("chalk wall", "pinned note", "lectern face"),
    ),
    "weather_map": _profile(
        "weather_map", "classroom_briefing+market_news_crisis", 6,
        ("presenter pointer or weather prop", "floor light or camera edge"),
        ("curved map wall", "storm-cloud and directional weather forms"),
        ("broadcast camera silhouettes", "ceiling spotlights or studio depth"),
        1, "clear cool-versus-warm weather contrast with directional color bands",
        ("map region", "cloud callout", "broadcast map arrow zone"),
    ),
    "risk_control_room": _profile(
        "risk_control_room", "control_room_data_lab+market_news_crisis", 7,
        ("physical console", "one narration-essential risk prop"),
        ("central gauge or monitor", "two supporting instrument clusters"),
        ("operations wall depth", "warning lamps and cable or circuit structure"),
        3, "deep blue control-room base with decisive red risk and restrained gold protection accents",
        ("central gauge face", "metal warning plaque", "console screen"),
    ),
    "trade_calculator": _profile(
        "trade_calculator", "physical_economic_metaphor+classroom_briefing", 5,
        ("large brass balance scale", "engraved plinth"),
        ("closed ledger stack", "comparison objects on separate scale pans"),
        ("chamber architecture", "focused spotlight and shadow depth"),
        2, "dark navy and brass gold with one red caution accent when required",
        ("scale pan prop face", "engraved plinth", "wall diagram"),
    ),
    "data_lab": _profile(
        "data_lab", "control_room_data_lab+factory_construction", 7,
        ("laboratory workbench or console", "one narration-essential sample or mechanism"),
        ("at least three distinct analytical equipment or information-surface clusters", "production or comparison props"),
        ("server racks, factory depth, or research-room architecture", "overhead technical lighting"),
        3, "cool cyan-blue analytical base with scene-direction green, red, or gold causal accents",
        ("scene-planned laboratory surface", "equipment face", "solid monitor"),
    ),
    "briefing_podium": _profile(
        "briefing_podium", "classroom_briefing", 6,
        ("podium and microphones", "foreground cable or press equipment"),
        ("embedded briefing wall", "press seating or camera cluster"),
        ("ceiling light bank", "room architecture and audience depth"),
        1, "neutral press-room blues with a warm speaker key light and one directional accent",
        ("embedded briefing wall", "podium face"),
    ),
    "real_estate_office": _profile(
        "real_estate_office", "dialogue_office_library+physical_economic_metaphor", 6,
        ("consultation desk", "calculator, folder, or house-model prop"),
        ("wall guidance board", "banker lamp and file cluster"),
        ("window architecture", "exterior home silhouettes or shelving"),
        1, "warm office amber with cool window and board reflections",
        ("wall guidance board", "calculator face", "window listing surface"),
    ),
    "job_market_hall": _profile(
        "job_market_hall", "classroom_briefing+dialogue_office_library", 7,
        ("consultation counter", "mechanical ticket dispenser or closed folder"),
        ("booth dividers", "job-seeker and guide-light clusters"),
        ("public-hall architecture", "queue depth and distant counters"),
        1, "bright civic neutrals with welcoming blue-green accents and restrained warning color",
        ("wall employment board", "closed folder face", "counter-integrated surface"),
    ),
    "earnings_stage": _profile(
        "earnings_stage", "classroom_briefing+control_room_data_lab", 7,
        ("executive podium or desk", "microphone and cable cluster"),
        ("embedded results mural", "camera and investor-seat clusters"),
        ("stage architecture", "overhead spotlights and audience depth"),
        1, "cool corporate stage base with warm key lights and direction-specific green or red accents",
        ("embedded results mural", "podium face"),
    ),
    # Job52 보존 입력에 있던 분할형은 현재 운영 archetype을 추가하거나 바꾸지
    # 않고 별도 밀도 프로필로만 해석한다.
    "split_comparison": _profile(
        "split_comparison", "physical_economic_metaphor+market_news_crisis", 6,
        ("central comparison subject", "one foreground causal prop per side"),
        ("distinct left and right physical mechanisms", "one anchored surface per side"),
        ("continuous architectural context or matched distant depth",),
        2, "clearly separated green or gold positive side and red negative side without flattening the room into two blank cards",
        ("left scene-native surface", "right scene-native surface"),
    ),
    "evidence_insert": _profile(
        "evidence_insert", "evidence_insert", 5,
        ("verified capture or document asset", "one physical framing prop"),
        ("source-context object cluster", "supporting non-textual explanation prop"),
        ("room, newsroom, or desk depth",),
        1, "neutral evidence treatment with one scene-direction accent; never regenerate source text",
        ("verified capture asset",),
    ),
    "generic_editorial": _profile(
        "generic_editorial", "physical_economic_metaphor", 5,
        ("one narration-essential foreground prop",),
        ("two distinct causal object clusters", "one scene-integrated information surface when planned"),
        ("location-specific architecture or environment depth",),
        1, "scene-direction contrast with a restrained neutral base",
        ("scene-planned physical surface",),
    ),
}


_ARCHETYPE_ALIASES = {
    "split_stage": "split_comparison",
    "split_outcomes": "split_comparison",
    "comparison_board": "classroom",
    "factory_dashboard": "risk_control_room",
    "data_lab": "data_lab",
    "article_evidence": "evidence_insert",
    "evidence_insert": "evidence_insert",
}


def _candidate_archetypes(scene: dict[str, Any]) -> list[str]:
    render = scene.get("v5_render_contract") or {}
    selection = render.get("selection") or scene.get("v5_scene_type_selection") or {}
    direction = scene.get("art_direction") or {}
    return [
        str(selection.get("archetype") or "").strip(),
        str(scene.get("archetype") or scene.get("visual_archetype") or "").strip(),
        str(direction.get("family") or "").strip(),
        str(scene.get("visual_mode") or "").strip(),
    ]


def composition_density_profile_for_scene(scene: dict[str, Any] | None) -> CompositionDensityProfile:
    """장면 번호와 무관하게 archetype·연출 계보로 밀도 프로필을 고른다."""
    for candidate in _candidate_archetypes(scene or {}):
        if not candidate:
            continue
        key = _ARCHETYPE_ALIASES.get(candidate, candidate)
        if key in COMPOSITION_DENSITY_PROFILES:
            return COMPOSITION_DENSITY_PROFILES[key]
    return COMPOSITION_DENSITY_PROFILES["generic_editorial"]


def composition_density_prompt(profile: CompositionDensityProfile) -> str:
    """기존 텍스트 정확성 계약과 충돌하지 않는 영어 생성 지시를 만든다."""
    foreground = "; ".join(profile.foreground_elements)
    midground = "; ".join(profile.midground_elements)
    background = "; ".join(profile.background_elements)
    anchors = ", ".join(profile.text_surface_anchors)
    surface_requirement = (
        f"Keep at least {profile.min_information_surfaces} distinct scene-integrated information-surface or instrument clusters"
        if profile.min_information_surfaces > 1
        else "Keep any planned information surface subordinate and integrated into the set"
    )
    return (
        f"COMPOSITION DENSITY PROFILE [{profile.id}]: render at least {profile.min_background_elements} distinct scene-native non-textual background elements or coherent prop clusters outside any calm text surface. "
        f"Use all three depth layers: foreground ({foreground}); midground ({midground}); background ({background}). "
        f"{surface_requirement}. Color contrast rule: {profile.color_contrast_rule}. "
        f"Approved text, when present, may anchor only to a scene-planned physical surface such as {anchors}, and remains governed by the independent approved scene-local text contract. "
        "The density requirement is visual, not typographic: do not use words, pseudo-text, digits, tick labels, equations, microprint, logos, extra blank screens, detached cards, or invented dashboards to satisfy the element count. "
        "Every counted element must explain the narration's location, causal mechanism, or economic relationship rather than act as random decoration."
    )


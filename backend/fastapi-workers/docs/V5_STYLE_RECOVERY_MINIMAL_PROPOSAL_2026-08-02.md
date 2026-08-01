# V5 스타일 회복 최소 수정안

## 결론

현재 결과의 문제는 두 층으로 나뉜다.

1. **AI 배경 미감 이탈**: 일반형 `port_emergency`도 기존 7월 30일 승인본보다 매끈한 벡터·프리미엄 일러스트처럼 생성됐다. 따라서 정보형 전용 `fact_surface_contract`만이 원인은 아니다.
2. **사실값 오버레이의 재질 이탈**: `data_lab`의 `코스피 종가 5663.24`는 지정 primary 영역 안에는 들어갔지만, Pillow의 짙은 남색 불투명 사각형이 홀로그램 지도 표면의 재질·광원·원근을 상속하지 못했다. 이 문제는 Gemini 프롬프트를 수정해도 해결되지 않으며, 별도 렌더러 작업이 필요하다.

따라서 이 문서는 **배경 스타일을 회복하는 최소 프롬프트 수정안**과 **정확한 수치의 재질 통합을 위한 별도 후속 작업**을 구분한다.

## 확인된 근거

| 항목 | 7월 30일 승인 benchmark | 8월 1일 실전 경로 | 현재 비교 생성 |
|---|---|---|---|
| 모델·해상도·티어 | `gemini-3-pro-image`, 2K, standard | 동일 | 동일 |
| 참조 자산 | v2 textless 2장 | v2 textless 2장 | v4 clean 2장 |
| 텍스트 정책 | `strict_textless` | 정보형은 `diegetic_decorative` | 정보형은 `diegetic_decorative` |
| 레이아웃 계약 | `LayoutSketcher`를 프롬프트에 포함 | runtime 경로에서 미전달 | runtime 경로에서 미전달 |
| seed | runner가 값만 기록 | runner가 값만 기록 | 동일 |

### Git 이력 확인

`prompt_builder.py`에 관한 Git 이력은 초기 커밋 `34bfb8e` 하나뿐이다. 7월 30일과 8월 1일 사이의 세부 변경은 모두 아직 커밋되지 않은 작업 트리에 있어 Git 날짜만으로 정확한 변경 시점을 복원할 수 없다. 다만 초기 버전과 현재 버전의 diff는 다음 변경이 실제로 존재함을 증명한다.

- `build_prompt()`가 단순 무문자 benchmark 계약에서 `scene_type`, primary 표면, 대체물 금지, 화면형 소품 금지 등 대형 계약으로 확장됐다.
- benchmark는 `LayoutSketcher.prompt_instruction()`을 전달하지만, `runtime_contract.py`는 현재 `build_prompt()`를 layout instruction 없이 호출한다.
- 현재 Gemini HTTP payload에는 `seed`, `temperature`, `topP`, `topK`가 없다. 모델명·이미지 크기·서비스 티어가 바뀐 증거는 없지만, 기록된 seed도 실제 결과를 고정하지 못한다.

## 가설 판정

| 가설 | 판정 | 근거 |
|---|---|---|
| 7/30~8/1 프롬프트/경로가 달라졌다 | 확인됨 | `strict_textless`→`diegetic_decorative`, primary 계약 추가, runtime의 layout 미전달 |
| `fact_surface_contract`가 정보형의 UI 성향을 키운다 | 일부 확인됨 | 정보형만 동일 계약을 3개 구역에 반복해 primary·라벨·금지 조건을 과도하게 강조한다 |
| 이것이 전체 화풍 이탈의 유일 원인이다 | 기각 | 일반형도 사실 표면 계약 없이 미감 이탈을 보였다 |
| 모델 파라미터가 변경됐다 | 증거 없음 | 모델·2K·standard는 동일이고, payload에 조절 파라미터 자체가 없다 |
| v4 참조가 8월 1일 이탈의 원인이다 | 기각 | 8월 1일 생성은 v2 참조를 사용했다. 다만 현재 비교 생성은 v4이므로, v4가 회복에 충분하지 않다는 별도 사실은 확인됐다 |

## R1 — 배경 스타일 회복용 최소 수정안

다음 세 항목만 변경한다. archetype 정의, primary 좌표, 검증 수치 계약, Pillow 오버레이 좌표 가드는 변경하지 않는다.

1. `runtime_contract.py`에서 benchmark와 같이 `LayoutSketcher`의 layout instruction을 `build_prompt()`에 전달한다. 이는 캐릭터 점유율·위치·안전 공간을 실전 경로에도 복원하는 변경이다.
2. 현재의 긴 `V5_CINEMATIC_CARTOON_STYLE_CONTRACT`를 아래의 회복 계약으로 교체한다. 새 계약은 benchmark의 핵심 art direction을 그대로 유지하고, 현재 결과에서 확인된 매끈한 벡터 UI 경향만 한 줄로 금지한다.
3. 정보형에서는 primary 표면의 장식 문자 의무를 `_fact_surface_contract()` 한 곳에만 남긴다. `background_information_density`와 `exclusions`의 같은 의무 문구 두 번은 제거한다. primary 선택과 non-primary 금지는 유지한다.

### R1 공통 art-direction 문자열

```text
ART STYLE: bold thick black ink outlines, flat cel-shading, high contrast,
rich prop density, theatrical composition, editorial cartoon quality, limited
vivid palette. Build one continuous full-bleed illustrated stage with clear
foreground, midground, and background depth. Preserve hard, readable cel-shadow
boundaries and strong localized red, gold, cyan, or storm-light accents chosen
by the stage. Do not render a smooth vector-dashboard illustration, a glossy
3D toy, a corporate UI illustration, or an airbrushed premium concept-art finish.
```

### R1 일반형 예시 프롬프트 핵심부

```text
<composition>
Premium economic-explainer cartoon illustration. The mascot occupies the right
third of the frame, taking up about 42% of the frame. Keep the subject fully
visible in a staged foreground; preserve the generated layout contract.
</composition>
<scene>
STAGE: a stormy shipping port at night, container cranes and a cargo ship in
the background, wet reflective dock. KEY PROPS: stacked shipping containers,
a large cargo ship, harbor cranes, red warning beacons, crashing waves.
LIGHTING: dark stormy sky, lightning strike, heavy rain, red emergency glow.
</scene>
<art_direction>[R1 공통 문자열]</art_direction>
<background_information_density>
Build a fully dressed narrative set using scene-native cranes, containers,
waves, rain, beacon light, dock hardware, and non-quantitative texture. No
numbers, chart labels, metric displays, or factual readouts.
</background_information_density>
```

### R1 정보형 예시 프롬프트 핵심부

```text
<composition>
Premium economic-explainer cartoon illustration. The mascot occupies the right
third of the frame, taking up about 42% of the frame. Keep the central map
panel unobstructed; preserve the generated layout contract.
</composition>
<scene>
STAGE: a futuristic control-room with one central holographic world-map panel,
physical control consoles, cyan data streams, and map nodes. KEY PROPS: map
panel, console, luminous routes, color-only gauge forms. LIGHTING: cool cyan
holographic glow with controlled dark-navy shadows.
</scene>
<art_direction>[R1 공통 문자열]</art_direction>
<background_information_density>
Build a dense explanatory cartoon set. Make the central holographic map panel
the only information focal prop. All non-primary props remain rich through
color blocks, needles, routes, light, and non-writing texture; do not distribute
labels across multiple props.
</background_information_density>
<fact_surface_contract>
The only permitted information-bearing prop is one central holographic map
panel. Compose one substantial perspective-correct information area inside that
exact prop. The primary prop alone MUST include two or three short decorative
English labels or sample figures integrated with cyan glow, reflection,
occlusion, and map perspective. Other props have no readable marks. AI text is
decorative only; verified facts are composited later.
</fact_surface_contract>
```

R1은 AI가 만든 장식 텍스트의 위치·무대 밀도·캐릭터 구도를 회복하기 위한 것이다. 정확한 수치의 후처리 방식은 변경하지 않는다.

## R2 — 사실값의 재질 통합(별도 승인 필요)

현재 `diegetic_fact_overlay.py`의 공용 `monitor`/`placard`/`gauge_caption`/`embedded_monitor` 템플릿은 사각형 카드만 그린다. 이 사실은 이번의 짙은 남색 스티커 문제를 직접 설명한다. R1 프롬프트 변경으로는 Pillow가 그린 카드의 재질을 바꿀 수 없다.

R2는 archetype별로 공용 카드를 바꾸는 작업이다. 예를 들면 `data_lab`에서는 불투명 사각 패널을 제거하고, 지도 좌표계 위의 반투명 cyan callout·연결선·광원 글자만 그린다. `trade_calculator`는 저울 받침 각인, `risk_control_room`은 곡면 게이지 문자반 방식으로 별도 템플릿을 사용한다. 이 작업은 R1과 독립된 새 구현 범위이므로 이번 문서에서 구현하거나 승인된 것으로 간주하지 않는다.

## 실행 순서

1. 이 문서의 R1 문자열과 세 변경 범위를 사람 검토로 승인한다.
2. 승인 후 R1 코드만 반영하고, API 호출 없이 일반형·정보형 최종 프롬프트 전체를 다시 제출한다.
3. 그 프롬프트가 승인된 뒤에만 일반형 1장·정보형 1장을 다시 생성한다.
4. 배경 미감 통과 후 R2를 별도 설계·승인한다. R2 전에는 카드의 재질 통합을 해결됐다고 주장하지 않는다.


## R1 완전 프롬프트 검토본

아래 문자열은 코드 적용 전 사람 검토용이다. `R1 공통 art-direction`, LayoutSketcher 복원, 정보형의 중복 의무 문구 제거를 모두 반영했으며, 아직 API에 전송되지 않았다.

### 일반형: `port_emergency`

```text
<character>
a friendly anthropomorphic GOLD COIN mascot character, round gold coin body with an embossed rim, expressive cartoon face, large round eyes with visible white sclera, small confident smile, white four-finger cartoon gloves, short stubby legs with brown shoes, thick clean black ink outline, flat cel-shading, warm rim light. Keep the exact same round coin silhouette, rim thickness, face proportions, eye shape, iris style, eyebrows, and ink-line weight as the fixed channel mascot in every scene; only wardrobe, pose, and facial expression may change. Never restyle the mascot as a flat token, a different cartoon character, or a different illustration medium, panicked alarmed face, mouth open shouting, wearing an orange hard hat and a reflective yellow safety vest, running forward in panic, holding a red megaphone
</character>
<composition>
Premium economic-explainer cartoon illustration. The mascot occupies the right third of the frame in the foreground, taking up about 42% of the frame. Clear foreground, midground, and background depth. LAYOUT CONTRACT: keep the mascot in the right-side foreground and keep its face and hands away from a calm lower band and a quiet upper-right corner. Keep the designated mid-frame readable for a later fact overlay while preserving ordinary scene depth and fully dressed diegetic props. Do not draw any layout guide, safe-area outline, placeholder, or empty display.
</composition>
<scene>
STAGE: a stormy shipping port at night, container cranes and a cargo ship in the background, wet reflective dock. KEY PROPS: stacked shipping containers, a large cargo ship, harbor cranes, red warning beacons, crashing waves. LIGHTING: dark stormy sky, lightning strike, heavy rain, red emergency light glow. DECORATIVE DETAIL: rain streaks, beacon glows, container color blocks, and wave silhouettes.
</scene>
<art_direction>
ART STYLE: bold thick black ink outlines, flat cel-shading, high contrast, rich prop density, theatrical composition, editorial cartoon quality, limited vivid palette. Build one continuous full-bleed illustrated stage with clear foreground, midground, and background depth. Preserve hard, readable cel-shadow boundaries and strong localized red, gold, cyan, or storm-light accents chosen by the stage. Do not render a smooth vector-dashboard illustration, a glossy 3D toy, a corporate UI illustration, or an airbrushed premium concept-art finish. FRAME CONTINUITY: make one continuous full-bleed illustrated scene from edge to edge. Do not use a split screen, comic-panel gutter, inset picture, internal frame border, filmstrip, collage, or a large rectangular overlay that visually divides the composition.
</art_direction>
<background_information_density>
Build a fully dressed narrative set using scene-native cranes, containers, waves, rain, beacon light, dock hardware, and non-quantitative texture. No numbers, chart labels, metric displays, or factual readouts.
</background_information_density>
<reserve>
Keep a slim lower band and a small upper-right corner free of foreground subjects and high-contrast details. Show only continuous background texture in those areas. Do not place the mascot's face or hands there.
</reserve>
<exclusions>
DO NOT INCLUDE any visible typographic mark: no readable or pseudo-readable words, glyphs, numerals, captions, branding marks, or watermarks. Do not draw Roman letters, symbols, equations, axis labels, or chart annotations. Do not make a split screen, comic panels, inset images, picture-in-picture windows, framing gutters, or a collage. The scene must be complete, busy, and meaningful.
</exclusions>
```

### 정보형: `data_lab`

```text
<character>
a friendly anthropomorphic GOLD COIN mascot character, round gold coin body with an embossed rim, expressive cartoon face, large round eyes with visible white sclera, small confident smile, white four-finger cartoon gloves, short stubby legs with brown shoes, thick clean black ink outline, flat cel-shading, warm rim light. Keep the exact same round coin silhouette, rim thickness, face proportions, eye shape, iris style, eyebrows, and ink-line weight as the fixed channel mascot in every scene; only wardrobe, pose, and facial expression may change. Never restyle the mascot as a flat token, a different cartoon character, or a different illustration medium, calm friendly explaining expression, gentle smile, wearing a brown fedora and a navy TV-anchor suit, one arm extended presenting, open palm gesture
</character>
<composition>
Premium economic-explainer cartoon illustration. The mascot occupies the right third of the frame in the foreground, taking up about 42% of the frame. Clear foreground, midground, and background depth. For this wide control-room view, show the mascot from hat to shoes at the same full-body scale as the other scenes; keep the character within the right-side foreground and leave the control room, map wall, and console visibly spacious around it. Do not use a close portrait crop. LAYOUT CONTRACT: keep the mascot in the right-side foreground and keep its face and hands away from a calm lower band and a quiet upper-right corner. Keep the designated mid-frame readable for a later fact overlay while preserving ordinary scene depth and fully dressed diegetic props. Do not draw any layout guide, safe-area outline, placeholder, or empty display.
</composition>
<scene>
STAGE: a futuristic control-room with a holographic map wall and abstract data light forms. KEY PROPS: a holographic map with node lights, floating bar and line silhouettes without axes, a control console, glowing data streams. LIGHTING: cool holographic blue-cyan glow, soft ambient room light. DECORATIVE DETAIL: holographic map nodes, luminous lines, color blocks, and color-only data streams.
</scene>
<art_direction>
ART STYLE: bold thick black ink outlines, flat cel-shading, high contrast, rich prop density, theatrical composition, editorial cartoon quality, limited vivid palette. Build one continuous full-bleed illustrated stage with clear foreground, midground, and background depth. Preserve hard, readable cel-shadow boundaries and strong localized red, gold, cyan, or storm-light accents chosen by the stage. Do not render a smooth vector-dashboard illustration, a glossy 3D toy, a corporate UI illustration, or an airbrushed premium concept-art finish. FRAME CONTINUITY: make one continuous full-bleed illustrated scene from edge to edge. Do not use a split screen, comic-panel gutter, inset picture, internal frame border, filmstrip, collage, or a large rectangular overlay that visually divides the composition.
</art_direction>
<background_information_density>
Build a dense explanatory cartoon set. Make one central holographic map panel the only visual-information focal prop. All non-primary props remain rich through color blocks, needles, routes, light, and non-writing texture; do not distribute labels across multiple props. All AI-drawn writing and values are atmospheric decoration only, never factual information. Never leave an empty screen or a blank placeholder.
</background_information_density>
<fact_surface_contract>
IN-SCENE FACT-SURFACE CONTRACT: this is a graph scene. The only permitted information-bearing prop is one central holographic map panel. Compose one substantial, unobstructed, perspective-correct information area inside that exact prop; it is part of the set, not an overlay placed on top of the frame. Every other gauge, screen, map, placard, document, and console must show only needles, color blocks, abstract shapes, or non-writing material texture: no readable text, letters, numbers, formula fragments, labels, axis ticks, or chart annotations. The designated primary prop MUST visibly include at least two or three short, clearly readable decorative English labels or sample figures engraved, painted, chalked, printed, or projected directly inside that same physical prop. Those marks must inherit its material, outline, lighting, occlusion, and perspective. Never place a number or text in a floating card, detached rectangular UI, separate LCD widget, or pasted-on panel. AI-drawn marks are decorative only; exact verified facts are composited later by deterministic rendering.
</fact_surface_contract>
<reserve>
Keep a slim lower band and a small upper-right corner free of foreground subjects and high-contrast details. Show only continuous background texture in those areas. Do not place the mascot's face or hands there.
</reserve>
<exclusions>
DO NOT INCLUDE Korean text, Korean subtitles, a channel logo, watermark, or a generic floating dashboard card. Do not create a detached rectangular UI widget, free-floating data card, isolated LCD panel, presentation slide, or a separate POS-style number screen placed on top of the scene. All gauges, screens, maps, placards, documents, signs, and consoles OTHER THAN one central holographic map panel must show only needles, color blocks, abstract shapes, or non-writing material texture. Do not make empty monitors, empty boards, blank title cards, layout-guide frames, split screens, comic panels, inset images, picture-in-picture windows, framing gutters, or collages. The gold coin mascot is the only anthropomorphic character. The scene must be complete, busy, and meaningful.
</exclusions>
```


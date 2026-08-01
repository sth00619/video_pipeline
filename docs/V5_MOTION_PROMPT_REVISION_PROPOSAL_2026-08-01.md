# V5 모션 프롬프트 개선안 — 검토용

## 상태와 범위

이 문서는 **코드 변경·FAL/Kling 호출을 하지 않은** 검토안이다. 현재 실제 호출 경로는 `app/services/kling_prompt_builder.py`의 `build_kling_motion_prompt()`이며, `longform_worker.py`의 동명에 가까운 `_build_kling_motion_prompt()`는 현재 호출 경로가 아니다.

목표는 고정 카메라를 유지한 채, 장면 안에서만 다음 세 요소를 조합하는 것이다.

1. 마스코트 행동 한 가지
2. 그 행동에 반응하는 기존 소품 한 가지
3. 광원 또는 파티클 한 가지

모든 프롬프트는 새 글자·숫자·차트를 만들거나, 기존 텍스트를 바꾸지 않는다. 실제 금융 수치는 이 프롬프트에 넣지 않으며, 생성 모델이 수치를 발명하게 하지 않는다.

## 공통 프리픽스 및 네거티브 제안

### 프리픽스

```text
2D cel-shaded cartoon animation. Preserve the exact source image composition, character identity, line weight, palette, and all existing scene objects. Camera is locked: no pan, zoom, dolly, roll, shake, reframing, or crop change. Animate only the mascot, one existing reactive prop, and one light/particle effect. Preserve every existing written mark, number, chart shape, and factual overlay exactly; do not create, erase, translate, redraw, morph, or animate any text or number.
```

### 네거티브

```text
no 3D rendering, no photorealism, no face morphing, no outfit change, no color shift, no extra characters, no warped hands, no jitter, no camera movement, no background redesign, no new screen, no new panel, no text distortion, no number distortion, no chart redraw, no changing labels, no changing factual overlay.
```

## motion_type별 교체 제안

아래 본문은 기존 5초 클립 규격을 유지한다. 특정 소품이 원본 장면에 없으면 그 소품을 새로 만들지 않고, 마지막 문장의 광원/파티클만 적용한다.

### `chart_shock`

```text
0–1s: the mascot sharply leans back and raises one open hand in a single surprised reaction. 1–3s: the mascot takes one short backward step and settles. 3–5s: one existing alert light or existing chart glow briefly brightens once, then returns to its original state; three to five small dust or sparkle particles rise and fade. Do not animate, redraw, or change any chart line, text, number, label, or overlay. Camera remains locked.
```

### `pointing_explain`

```text
0–2s: the mascot raises the existing pointer or open hand toward the already-visible information surface. 2–4s: make one gentle tap or one short presenting sweep, then stop; do not draw on the surface. 4–5s: the mascot gives one confident nod while a soft existing room light subtly blooms and a few dust motes drift. Do not animate, redraw, or change any chart, text, number, label, or overlay. Camera remains locked.
```

### `thinking_desk`

```text
0–2s: the mascot rests its chin on one hand and glances once toward an existing desk prop. 2–4s: one blink and a small eyebrow raise; keep the body otherwise still. 4–5s: an existing desk lamp reflection or ambient rim light softly pulses once while a few dust motes fade through the air. Do not animate, redraw, or change any screen contents, chart, text, number, label, or overlay. Camera remains locked.
```

### `walking_intro`

```text
0–3s: the mascot makes exactly two small in-place walking steps within its original footprint; do not approach the camera or change framing. 3–5s: the mascot stops and gives one short wave. If an existing physical prop can naturally react, make only that prop sway slightly; otherwise use only a few background particles. Do not create or change signs, text, numbers, charts, labels, or overlays. Camera remains locked.
```

### `celebration`

```text
0–2s: the mascot raises both arms once. 2–4s: one compact joyful hop in place, then land in the same position. 4–5s: one existing warm light or already-present sparkle effect brightens gently and fades. Do not create trophies, coins, labels, numbers, charts, or text; do not alter any existing overlay. Camera remains locked.
```

## 사실 오버레이와 모션의 안전 규칙

현재 V5 이미지는 `ImagesWorker._apply_image_overlays()`에서 Pillow 합성된 뒤, 해당 PNG가 FAL image-to-video의 입력으로 전달된다. 따라서 현재 상태에서 정보 씬을 FAL로 보내면 모델이 합성된 글자·숫자를 **왜곡하지 않는다는 보장이 없다.** "no text distortion"은 억제 프롬프트일 뿐 결정론적 보장이 아니다.

첫 구현에서는 아래의 보수적 규칙을 적용하는 것이 안전하다.

| 씬 | 초기 모션 처리 | 사실값 보존 |
|---|---|---|
| `general` | 위 프롬프트로 FAL/Kling 사용 가능 | 사실 오버레이 없음 |
| `metric`/`graph`/`diagram` + `v5_verified_overlays` | FAL/Kling 모션 대상에서 제외하고 정지 이미지/기존 전환만 사용 | Pillow로 합성된 최종 PNG가 프레임 전체에서 그대로 유지됨 |

이 방식은 정보 씬의 배경·캐릭터를 움직이지 않는 대신, 실제 수치가 한 픽셀도 변형되지 않게 보장한다. 향후 정보 씬에도 움직임을 넣으려면 별도 구현·검증이 필요하다.

1. 오버레이 없는 깨끗한 배경판만 FAL/Kling에 전달한다.
2. 생성된 동영상의 모든 프레임에 Pillow/FFmpeg로 동일 좌표의 검증 오버레이를 후합성한다.
3. 카메라는 계속 고정하고, primary surface가 캐릭터나 소품에 가려지지 않는 장면만 허용한다.

이 후합성 방식은 다음 코드 변경 단계에서 별도 테스트 영상으로 검증해야 하며, 이번 문서가 그 구현을 승인하거나 수행하지는 않는다.

## 다음 승인 이후의 작은 변경 단위

1. 위 다섯 템플릿과 공통 프리픽스/네거티브만 `kling_prompt_builder.py`에 반영한다.
2. `longform_worker.py`의 FAL 선택 전, `v5_verified_overlays`가 있는 씬을 FAL 후보에서 제외한다.
3. 단위 테스트로 일반 씬은 프롬프트를 받고, 정보 씬은 정지 경로로 분기되는지만 확인한다.
4. 사람 승인 뒤 5초짜리 일반 씬 한 장만 영상 생성해 행동·소품·광원 조합을 평가한다.

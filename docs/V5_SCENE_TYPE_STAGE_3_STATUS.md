# V5 씬 타입 → 프롬프트 물리 표면 계약 — 3단계 결과

작성일: 2026-07-31

## 완료 범위

`build_prompt()`에 선택 인자 `scene_type_selection`을 추가했다. 이 인자는 2단계 `recommend_v5_archetype()`의 결과를 그대로 받으며, 정보형 씬만 물리 표면 계약을 프롬프트에 추가한다.

```python
selection = recommend_v5_archetype(scene)
prompt = build_prompt(spec, scene_type_selection=selection)
```

기존 호출은 이 인자를 넘기지 않으므로 기존 벤치마크 프롬프트 동작을 바꾸지 않는다.

## 정보형 씬 계약

`graph`, `metric`, `diagram`, `text` 씬에는 `<fact_surface_contract>`가 들어간다.

- 정확히 하나의 기존 물리 소품을 사실 정보 표면으로 선택한다.
- 숫자·글자·축 눈금이 생긴다면 그 소품 안에 새겨지거나, 칠해지거나, 분필/인쇄/투사되어야 한다.
- 소품의 재질·외곽선·조명·가림·원근을 따라야 한다.
- 떠 있는 카드, 분리 UI, 별도 LCD 위젯, 붙여 놓은 패널은 명시적으로 금지한다.
- AI가 그린 글자·숫자는 장식이며, 정확한 검증 사실은 이후 결정론적 합성으로만 넣는다고 명시한다.

예: `risk_control_room`의 `metric` 씬은 `analog gauge faces`, `metal warning plaques`, `control console` 중 하나를 정보 표면으로 지정한다. 따라서 “숫자가 있다”는 요구와 “떠 있는 UI 카드는 금지”가 같은 문단에서 결합된다.

## 무문자 정책과의 충돌 방지

| 정책 | 정보형 씬의 표면 지시 | AI 문자/숫자 |
|---|---|---|
| `diegetic_decorative` | 장면 속 물리 소품에만 표시 | 장식만 허용, 정확 사실은 후처리 |
| `strict_textless` | 같은 물리 소품을 후처리용 재질 표면으로 확보 | 전부 금지 |

`strict_textless`에는 “문자·숫자·기호를 그리지 말라”는 지시만 들어가며, `diegetic_decorative`의 “숫자를 소품에 새겨라” 문장은 들어가지 않는다. 두 요구가 한 프롬프트 안에서 충돌하지 않도록 테스트로 확인했다.

`general` 씬은 `<fact_surface_contract>` 자체를 받지 않으며, 수치·차트 눈금·지표 표시도 요청하지 않는다. 따라서 `port_emergency` 같은 일반 서사 무대에 숫자 UI가 실수로 추가되지 않는다.

## 파일럿 3씬의 전체 프롬프트 검토본

이미지 API를 호출하지 않고 생성한 전체 프롬프트 원문은 아래 파일에 있다.

`backend/fastapi-workers/out/v5_pilot/kospi_july_2026/scene_type_prompt_review.md`

| 씬 | 타입 | 무대 | 지정 물리 표면 |
|---|---|---|---|
| `kospi_july_01` | `graph` | `data_lab` | holographic map paths / translucent gauge faces / console etchings |
| `kospi_july_02` | `graph` | `trade_calculator` | balance-scale base / printed documents / wall diagrams |
| `kospi_july_03` | `metric` | `risk_control_room` | analog gauge faces / metal warning plaques / control console |

검토 출력 생성 명령:

```text
python scripts/review_v5_scene_type_prompts.py
```

이 스크립트는 JSON을 읽고 Markdown 프롬프트 검토본만 저장하며, API 키·외부 API·이미지 생성기를 사용하지 않는다.

## 검증

`backend/fastapi-workers`에서 다음을 실행했다.

```text
python -m pytest tests/test_v5_scene_type_prompt_contract.py tests/test_v5_scene_type_archetypes.py tests/test_v5_textless_prompt.py tests/test_scene_type_classification.py tests/test_script_worker_safety.py -q
```

결과: `23 passed`

## 이번 단계에서 하지 않은 일

- Gemini/BFL 등 이미지 API 호출
- 실제 생성 이미지의 UI 카드·텍스트 오염 판정
- QualityGate 연결
- Pillow/FFmpeg 합성 규칙 변경
- 영상 조립 모션·노출 규칙 변경

다음 비용 발생 단계는 이 프롬프트 검토 결과에 대한 사람 승인 이후에만 진행한다.

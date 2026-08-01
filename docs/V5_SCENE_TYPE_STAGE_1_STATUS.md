# V5 씬 타입 분류 — 1단계 결과

작성일: 2026-07-30

## 완료 범위

`ScriptWorker`의 씬 계획 단계에서 `direct_scenes()` 직후, `_attach_verified_market_charts()` 직전에 모든 씬에 다음 두 필드를 기록한다.

```json
{
  "scene_type": "general|metric|graph|diagram|text",
  "selection_reason": "대본에 검증 대상 수치·등락·규모 표현이 있어 지표형으로 분류"
}
```

분류는 제목·대사·기존 시각 의도(`prompt_ko`, `prompt_en`, `visual_intent`)의 명시적 신호만 사용한다. LLM 호출이나 수치 생성은 하지 않는다. 실제 수치의 사실성은 이 분류 단계가 아닌 기존 검증·오버레이 계약의 책임이다.

## 분류 우선순위

1. `graph`: 차트, 그래프, 추이, 타임라인, 막대·선 그래프가 명시된 씬
2. `diagram`: 공급망, 흐름도, 구조, 단계, 과정, 인과 관계가 명시된 씬
3. `metric`: 수치, 지수, 종가, 고점·저점, 시가총액, 등락·변동률·낙폭이 있는 씬 또는 기존 `section=data` 씬
4. `text`: 정의·용어·핵심 문구 중심의 씬
5. `general`: 위 조건에 해당하지 않는 일반 설명 씬

`흐름` 단독 단어는 다이어그램 신호로 쓰지 않는다. 예를 들어 “향후 시장 흐름”은 수치 변화 씬을 다이어그램으로 잘못 분류할 수 있기 때문이다. 구조를 뜻하는 `흐름도` 또는 공급망·단계·인과처럼 명시적인 표현만 다이어그램으로 취급한다.

## V5 코스피 7월 파일럿 3씬 검증

입력: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/v5_pilot_input.json`

| 씬 | 기존 시각 의도 | 결과 | 판정 근거 |
|---|---|---|---|
| `kospi_july_01` | 사상 최고치와 종가 대비 차트 | `graph` | 차트·변화 비교가 명시됨 |
| `kospi_july_02` | 월간 낙폭 비교 막대그래프와 일별 타임라인 | `graph` | 막대그래프·타임라인이 명시됨 |
| `kospi_july_03` | 시가총액 감소 인포그래픽 | `metric` | 규모 변화와 수치가 핵심이며, 일반 “향후 흐름”은 다이어그램 신호에서 제외 |

## 검증

`backend/fastapi-workers`에서 다음을 실행했다.

```text
python -m pytest tests/test_scene_type_classification.py tests/test_script_worker_safety.py -q
```

결과: `10 passed`

## 이번 단계에서 하지 않은 일

- `scene_type`에 따른 V5 archetype/프롬프트 선택 연결
- 숫자가 장면 속 물리 소품에만 배치되도록 하는 프롬프트·합성 변경
- UI 카드 감지 QualityGate
- 씬 타입별 모션·노출 시간 조립 규칙
- 이미지 API 호출

위 항목은 다음 단계의 별도 승인 대상이다.

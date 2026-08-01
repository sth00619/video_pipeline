# V5 씬 타입 → archetype 매핑 — 2단계 결과

작성일: 2026-07-31

## 완료 범위

씬 타입에 맞는 V5 무대 후보를 고르는 순수 매핑 규칙을 추가했다. 이 규칙은 입력 씬을 수정하지 않고, 프롬프트 빌더·이미지 API·QualityGate·영상 조립을 호출하거나 연결하지 않는다.

- 규칙: `backend/fastapi-workers/app/v5/scene/scene_type_archetypes.py`
- 실제 V5 정의 대조 기준: `backend/fastapi-workers/app/v5/scene/prompt_builder.py`의 `ARCHETYPES`, `DIEGETIC_TEXT_GUIDANCE`

반환 형태는 다음과 같다.

```json
{
  "scene_type": "graph",
  "archetype": "data_lab",
  "alternatives": ["weather_map", "trade_calculator"],
  "selection_reason": "일반 시계열·시장 그래프이므로 지도 경로·계기면·콘솔이 있는 data_lab을 추천",
  "physical_surfaces": ["홀로그램 지도 경로", "반투명 계기면", "콘솔 각인"]
}
```

## 실제 archetype 대조

V5에는 `split_stage`가 없다. 실제 무대는 아래 7개다. 8개 벤치마크 씬은 `classroom`을 두 번 사용한 결과다.

| archetype | 실제 정의에 있는 장면 속 정보 표면 | 주 용도 |
|---|---|---|
| `port_emergency` | 컨테이너 측면, 부두 경고판, 세관 표지 | 일반 서사·현장 경고 |
| `retail_shock` | 계산대 내장 영수증 창, 가격표, 상품 포장 | 가격·판매·합계 지표 |
| `classroom` | 초록 강의 벽, 고정된 종이 노트 | 다이어그램·짧은 정의/문구 |
| `weather_map` | 곡면 지도 벽, 구름 아이콘, 지도 화살표 | 지도/지역 기반 그래프 |
| `risk_control_room` | 아날로그 계기판, 금속 경고 명판, 제어 콘솔 | 하락·위험·변동 지표 |
| `trade_calculator` | 저울 받침, 인쇄 문서, 벽면 다이어그램 | 막대·비율·공식·비교 그래프 |
| `data_lab` | 홀로그램 지도 경로, 반투명 계기면, 콘솔 각인 | 일반 시계열·시장 지표·연결망 |

## 매핑 규칙

| scene_type | 기본 추천 | 문맥에 따른 전환 | 후보 |
|---|---|---|---|
| `graph` | `data_lab` | 지도·지역·날씨 → `weather_map`; 막대·비율·공식 → `trade_calculator` | `data_lab`, `weather_map`, `trade_calculator` |
| `metric` | `data_lab` | 가격·판매·합계 → `retail_shock`; 하락·위험·변동 → `risk_control_room` | `risk_control_room`, `retail_shock`, `data_lab`, `trade_calculator`, `weather_map` |
| `diagram` | `classroom` | 노드·연결망 → `data_lab` | `classroom`, `trade_calculator`, `data_lab` |
| `text` | `classroom` | 없음 | `classroom`, `risk_control_room`, `port_emergency` |
| `general` | `port_emergency` | 설명·원리·배경 → `classroom` | `port_emergency`, `classroom`, `risk_control_room` |

후보에는 모두 실제 물리 정보 표면이 등록돼 있어야 하며, 빈 보드·분리 UI 카드·떠 있는 숫자 패널은 후보로 취급하지 않는다.

## V5 코스피 7월 파일럿 3씬 검증

입력: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/v5_pilot_input.json`

| 씬 | 1단계 타입 | 기존 시각 의도 | 추천 archetype | 사람이 확인할 이유 |
|---|---|---|---|---|
| `kospi_july_01` | `graph` | 사상 최고치·종가 대비 차트 | `data_lab` | 일반 시장 시계열을 홀로그램 계기면·콘솔에 녹이기 적합 |
| `kospi_july_02` | `graph` | 월간 낙폭 막대그래프·일별 타임라인 | `trade_calculator` | 막대·비율 비교를 저울·문서·벽면 다이어그램에 배치하기 적합 |
| `kospi_july_03` | `metric` | 시가총액 감소·투자자 우려 | `risk_control_room` | 급락·위험 지표를 계기판·경고 명판·콘솔에 배치하기 적합 |

첫 씬의 “고점 대비”는 단순 비교 문장일 뿐, `trade_calculator` 전환 신호로 쓰지 않는다. 막대·비율·공식처럼 비교 무대를 요구하는 명시 신호가 있을 때만 전환한다.

## 검증

`backend/fastapi-workers`에서 다음을 실행했다.

```text
python -m pytest tests/test_v5_scene_type_archetypes.py tests/test_scene_type_classification.py tests/test_script_worker_safety.py -q
```

결과: `14 passed`

## 이번 단계에서 하지 않은 일

- `ScriptWorker` 결과에 archetype 추천값을 저장하거나 프롬프트 빌더에 전달하는 연결
- V5 `build_prompt()` 수정
- 이미지 API 호출 및 이미지 생성
- 결정론적 수치 오버레이·QualityGate·FFmpeg 조립 변경

다음 단계에서는 이 매핑 계약을 어떤 필드로 이미지 경로에 전달할지와, 각 무대의 물리 표면을 프롬프트·합성에서 동일하게 보장할지 별도 승인 후 다룬다.

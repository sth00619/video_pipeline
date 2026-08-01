# V5 씬 타입 물리 표면 — 4단계 실제 이미지 검토

작성일: 2026-07-31

## 실행 범위와 회계

- 실행: `kospi_july_01`, `kospi_july_02`, `kospi_july_03`만 생성
- 모델: `gemini-3-pro-image` (표준 티어)
- 요청: 씬당 1회, 자동 재시도 없음
- 요청 원장: 세 건 모두 `http_200`
- 추정: 이미지당 `$0.14`, 합계 `$0.42`, 보수 환율 기준 `₩762`
- 실비 상태: `unverified_until_console_reconciliation`

원장과 manifest:

- `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/generated_backgrounds/kospi_july_2026_scene_type_stage4/_request_ledger.json`
- `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/generated_backgrounds/kospi_july_2026_scene_type_stage4/_manifest.json`

다음 유료 호출 전에는 Gemini 콘솔 실비와 이 3건을 대조해야 한다.

## 사람 육안 검토

| 씬 | 타입 / 무대 | 한글·로고 오염 | 떠 있는 카드/프레임 밖 UI | 정보가 물리 소품 안에 보이는가 | 정보 표면 하나 집중 | 판정 |
|---|---|---|---|---|---|---|
| `kospi_july_01` | `graph` / `data_lab` | 보이지 않음 | 보이지 않음 | 지도 벽·콘솔·계기면과 결합됨 | 지도, 양쪽 패널, 콘솔에 장식 문자가 분산됨 | 부분 통과 |
| `kospi_july_02` | `graph` / `trade_calculator` | 보이지 않음 | 보이지 않음 | 저울·문서·벽면·콘솔과 결합됨 | 벽면 패널, 문서, 콘솔에 다수 정보가 분산됨 | 부분 통과 |
| `kospi_july_03` | `metric` / `risk_control_room` | 보이지 않음 | 보이지 않음 | 계기판·경고 명판·콘솔에 결합됨 | 여러 계기판·모니터·명판이 동시에 정보를 가짐 | 부분 통과 |

## 통과한 점

- 세 장 모두 2D 카툰 무대와 금화 마스코트의 일관성이 유지됐다.
- 가짜 영어·숫자는 화면 위에 뜬 카드가 아니라 제어실/저울실/연구실의 물리 소품 안에 그려졌다.
- 이번 3씬에서 한글 자막, 채널 로고, 워터마크는 육안으로 보이지 않았다.

## 통과하지 못한 점

“검증 사실을 넣을 정보 표면 하나를 고른다”는 조건은 세 장 모두 충족되지 않았다. 장식 정보가 여러 소품으로 흩어져 있어, 나중에 정확한 Pillow 오버레이를 하나의 자연스러운 위치에 넣기 어려운 상태다.

원인은 프롬프트의 두 지시가 아직 경쟁하기 때문이다.

1. 새 `<fact_surface_contract>`는 `exactly one` 사실 표면을 요구한다.
2. 기존 `BACKGROUND INFORMATION DENSITY`와 archetype별 `DIEGETIC_TEXT_GUIDANCE`는 여러 계기판·화면·명패·문서에 라벨/수치/눈금을 넣도록 요구한다.

즉 “사실 표면은 하나”와 “장식 정보 표면은 여러 개”가 동시에 모델에 전달됐다. 이번 결과는 모델이 후자도 충실히 따른 것으로 해석해야 한다.

## 다음 권고 — 아직 구현하지 않음

나머지 5씬을 생성하기 전에 프롬프트 계약을 한 단계 더 좁혀야 한다.

- 후보 목록이 아니라 씬별 `primary_physical_surface` 하나를 결정한다.
- 그 표면에만 장식 텍스트/수치/그래프를 허용한다.
- 나머지 소품은 게이지 바늘·색상·도형·비문자 질감만 허용한다.
- `BACKGROUND INFORMATION DENSITY`와 `DIEGETIC_TEXT_GUIDANCE`를 이 선택에 종속시켜, 다수의 라벨을 요구하는 문장을 제거한다.

이 수정의 실제 이미지 재검증 승인 전에는 추가 생성하지 않는다.

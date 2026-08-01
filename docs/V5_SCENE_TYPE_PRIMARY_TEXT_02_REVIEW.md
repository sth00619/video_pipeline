# V5 primary surface 장식 문자 재검증 — 02·03번

작성일: 2026-07-31

## 실행 범위

- run ID: `kospi_july_2026_scene_type_primary_text_v4`
- 요청: `kospi_july_02`와 `kospi_july_03`, 각 1회
- 자동 재시도: 없음
- 사전 승인 예상 상한: `$0.28` / `₩508`

## 요청 결과

| 씬 | archetype | HTTP 상태 | 결과 |
| --- | --- | --- | --- |
| `kospi_july_02` | `trade_calculator` | 200 | 이미지 생성됨, 시각 판정 실패 |
| `kospi_july_03` | `risk_control_room` | 503 | 이미지 미생성, 자동 재시도 없음 |

이번 두 요청의 실제 청구액은 콘솔 대조 전까지 `unverified_until_console_reconciliation` 상태다.

## 02번 시각 판정: 실패

### 통과한 부분

- 한글 자막·채널 로고·워터마크는 보이지 않는다.
- 전체 일러스트 매체와 저울이라는 무대 소품은 유지된다.

### 실패한 부분

1. 지정 primary는 `front face of the balance-scale base`였지만, 읽을 수 있는 표기는 저울 받침이 아니라 전경의 별도 정보 명패에 집중됐다. 따라서 표면 위치 계약을 지키지 못했다.
2. 오른쪽 보조 소품에도 `MARKET TRENDS` 같은 읽을 수 있는 표기가 남아 primary 외 비문자 규칙을 위반했다.
3. 전경 명패는 장면 속 물체이긴 하지만, 이번 archetype에서 목표로 한 “저울 받침에 새겨진 정보”가 아니라 별도 데이터 패널처럼 보여 기존 UI-패널 실패 형태에 가깝다.

## 03번 상태

`risk_control_room` 요청은 `http_503`으로 종료됐다. 이미지가 없으므로 primary 집중·오염 여부를 판정할 수 없다. 별도 승인 없이 재요청하지 않는다.

## 다음 조정 후보 — 아직 미구현

`trade_calculator`에 한해 primary 명칭을 더 구체적으로 `the broad engraved front plinth directly beneath the scale's central pillar`로 바꾸고, `freestanding information plaque`, `desk display`, `framed dashboard`, `separate board`를 명시적으로 금지한다. 이 변경은 `data_lab` 규칙을 건드리지 않고 `trade_calculator`만 대상으로 한다.

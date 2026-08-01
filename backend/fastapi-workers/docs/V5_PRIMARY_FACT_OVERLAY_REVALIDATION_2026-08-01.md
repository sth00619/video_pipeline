# V5 primary-surface 사실 오버레이 재검증

## 목적

Gemini가 만든 V5 archetype 배경의 primary 표면 계약과 Pillow의 검증 수치
합성이 분리되어, 과거 입력 좌표가 primary 표면 밖이어도 그대로 렌더되던
문제를 재발 방지한다.

## 공통 차단 규칙

- `v5_render_contract.selection.archetype`가 있는 씬은
  `PRIMARY_SURFACE_REGIONS[archetype]` 안에 사실 오버레이가 완전히 들어가야 한다.
- 벗어나면 이미지 렌더 전에 `ValueError`로 차단한다.
- 이 규칙은 모든 12개 정의에 공통 적용된다. `earnings_stage`는 별도 렌더
  차단 상태지만 좌표 계약 테스트에는 포함한다.
- 이전 입력을 좌상단 기본값으로 바꾸는 동작은 없었다. 문제는 과거 입력이
  제공한 좌표를 검증 없이 수용했던 것이며, 이제는 이를 허용하지 않는다.

## 실제 배경 재합성 완료

| archetype | 사실값 | primary 물리 표면 | 결과 |
| --- | --- | --- | --- |
| `data_lab` | 코스피 종가 `5663.24` | 중앙 홀로그램 지도 패널 | 통과 |
| `trade_calculator` | 7월 월간 낙폭 `33.18%` | 저울 중앙 기둥 아래의 넓은 받침 전면 | 통과 |
| `risk_control_room` | 증시 시총 고점 `7810조 원` | 중앙 아날로그 게이지 문자반 | 통과 |

`trade_calculator`의 공통 좌표는 기존에 기둥 쪽으로 너무 높게 잡혀 있어,
실제 받침 전면을 가리키도록 `(0.36, 0.68, 0.38, 0.25)`로 정정했다.

## 아직 실제 합성 전인 승인 archetype

`port_emergency`, `retail_shock`, `classroom`, `weather_map`,
`briefing_podium`, `real_estate_office`, `job_market_hall`, 그리고
일반 서사에서만 쓰이는 `general` 경로는 새 가드가 적용되지만, 실제 검증
수치 합성의 첫 사용 시에는 원장·가드 통과 여부와 화면 배치를 사람이 함께
확인한다.

## 자동 검증

`tests/test_v5_diegetic_fact_overlay.py`는 모든 12개 archetype에 대해
primary 밖 사실 오버레이 차단과 primary 안 사실 오버레이 허용을 각각
검증한다. 2026-08-01 컨테이너 실행 결과는 관련 테스트 41건 통과다.

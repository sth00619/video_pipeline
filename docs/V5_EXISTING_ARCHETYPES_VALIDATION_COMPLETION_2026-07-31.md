# V5 기존 Archetype 검증 완료 기록

작성일: 2026-07-31  
범위: 기존 미검증 3개 archetype의 실제 Gemini Pro Image 단건 생성과 육안 판정  
제외: 신규 4개 archetype 구현·생성, 실제 금융 수치 삽입, 최종 영상 렌더링

## 공통 계약

각 장면은 하나의 `primary_physical_surface`에만 읽을 수 있는 장식 영문·표본 수치·도표를 허용한다.
나머지 소품에는 글자·숫자를 넣지 않는다. AI가 만든 표본 텍스트는 연출용이며, 실제 검증 수치는 이후 같은 좌표에 Pillow/FFmpeg로 결정론적으로 합성한다.

판정 기준은 아래와 같다.

| 기준 | 의미 |
|---|---|
| P1 | 지정 primary 표면 안에 2~3개 이상의 읽을 수 있는 장식 텍스트/도식이 장면 재질·조명·원근과 함께 존재 |
| P2-T | primary 외 모든 명시 소품에는 읽을 수 있는 글자·숫자가 없음 |
| P2-F | primary 외에 새로 생긴 비문자 소품도 무대 상식·크기/위치·primary 대체 가능성의 세 질문을 모두 통과해야 함 |
| P3 | 로고·한글·워터마크·분리된 UI 카드가 없음 |

## 실행 및 판정

| archetype | 최종 run | primary physical surface | P1 | P2 | P3 | 판정 |
|---|---|---|---|---|---|---|
| `classroom` | `classroom_primary_v1` | 큰 초록 교육 벽의 중앙 칠판 영역 | `GLOBAL MARKETS`, `TRADE FLOW`와 흐름도가 칠판 분필 질감으로 결합 | 책·책상·연단·보조 칠판은 비문자 | 통과 | 통과 |
| `port_emergency` | `port_emergency_primary_v2` | 중앙 부두의 가장 큰 전경 컨테이너의 넓고 평평한 정면 | 경고 문구와 하락 도식이 비·경광등·원근을 공유한 정면 도장으로 결합 | 선박·크레인·다른 컨테이너·지정 컨테이너의 측면은 비문자 | 통과 | 통과 |
| `retail_shock` | `retail_shock_primary_v2` | 단일 대형 계산대 상단에 매립된 영수증 창 | `TOTAL DUE`, 표본 금액, 화살표가 영수증 창의 테두리·반사광과 결합 | 계산기 액정·상품 포장·가격표·보조 화면은 비문자이며, 별도 모니터도 없음 | 통과 | 통과 |

## 보정 이력

`port_emergency_primary_v1`은 글자가 컨테이너 정면뿐 아니라 오른쪽 측면에도 생성되어 P2에 미달했다. 1회 보정에서는 primary를 “가장 큰 전경 컨테이너의 넓고 평평한 **정면**”으로 한정하고, 측면·끝문·지붕·코너 기둥·잠금 막대를 명시적으로 비문자로 금지했다. `v2`가 이 계약을 충족하여 채택했다.

`classroom`은 1차 생성으로 통과했다. `retail_shock`은 P2-F 보정 1회를 거쳐 통과했다. 자동 재시도는 어떤 run에도 사용하지 않았다.

### P2-F 판정 보완: retail_shock의 비문자 모니터

`retail_shock_primary_v1` 우측에는 모델이 추가한 비문자 색 블록 화면 2대가 있었다. 이는 `ARCHETYPES["retail_shock"]`의 명시 소품은 아니며, `color-coded price blocks without glyphs`라는 장식 지시를 배경 장비로 해석한 결과다. 다음 세 질문으로 재판정했다.

1. **무대 상식**: 현대 매장에 상품 안내·홍보용 디지털 화면은 자연스럽다. **예**
2. **크기·위치**: 두 화면은 배경 선반 뒤/프레임 가장자리에 있고, 캐릭터와 매립 영수증 창보다 시선을 강하게 차지하지 않는다. **예**
3. **primary 대체 가능성**: 화면 형태라서, 텍스트가 생기면 매립 영수증 창의 가격·합계 표면과 경쟁하는 정보 표면이 될 수 있다. **아니오**

따라서 `v1`은 P2-T는 통과했지만 P2-F는 실패였다. `extra wall display`, `overhead promotional screen`, `digital signage`, `secondary monitor`를 명시적으로 금지한 `v2`에서 추가 모니터가 사라졌고, P2-T와 P2-F 모두 통과했다. P2-F는 "텍스트가 없으니 자동 통과"가 아니라, 위 세 질문이 모두 예일 때만 통과다.

## 산출물과 회계 상태

| run | 이미지 | 요청 원장 | 예약 추정 |
|---|---|---|---|
| classroom v1 | `backend/fastapi-workers/out/v5_archetype_validation/classroom_primary_v1/classroom_primary_validation.png` | `.../classroom_primary_v1/_request_ledger.json` | $0.14 / ₩254 |
| port v1 (교체됨) | `backend/fastapi-workers/out/v5_archetype_validation/port_emergency_primary_v1/port_emergency_primary_validation.png` | `.../port_emergency_primary_v1/_request_ledger.json` | $0.14 / ₩254 |
| port v2 (채택) | `backend/fastapi-workers/out/v5_archetype_validation/port_emergency_primary_v2/port_emergency_primary_validation.png` | `.../port_emergency_primary_v2/_request_ledger.json` | $0.14 / ₩254 |
| retail v1 | `backend/fastapi-workers/out/v5_archetype_validation/retail_shock_primary_v1/retail_shock_primary_validation.png` | `.../retail_shock_primary_v1/_request_ledger.json` | $0.14 / ₩254 |
| retail v2 (채택) | `backend/fastapi-workers/out/v5_archetype_validation/retail_shock_primary_v2/retail_shock_primary_validation.png` | `.../retail_shock_primary_v2/_request_ledger.json` | $0.14 / ₩254 |

이번 배치의 실제 HTTP 요청은 5건(최종 채택 3건 + port 1차 교체본 + retail 1차 교체본)이다. 예약 추정 합계는 **$0.70 / ₩1,270**이며, 모든 항목의 `cost_status`는 `unverified_until_console_reconciliation`이다. 콘솔 실비 대조 전에는 이를 실제 청구액으로 표현하지 않는다.

## 현재 V5 상태

기존 7개 archetype(`data_lab`, `trade_calculator`, `risk_control_room`, `weather_map`, `classroom`, `port_emergency`, `retail_shock`)은 모두 primary-surface 규칙을 실제 이미지로 검증했다. 다음 범위는 별도 작업으로 남긴다.

1. `earnings_stage`, `briefing_podium`, `real_estate_office`, `job_market_hall`의 코드 설계와 검증
2. 대본의 `scene_type`과 archetype 매핑을 실제 운영 프롬프트/렌더링에 연결
3. 검증된 사실값을 동일 물리 표면 좌표에 Pillow/FFmpeg로 합성
4. 실제 영상 1~3씬 파일럿 및 콘솔 실비 대조

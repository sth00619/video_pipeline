# V5 Primary Surface Archetype 검증 플레이북

작성일: 2026-07-31  
적용 상태: `data_lab`, `trade_calculator`, `risk_control_room` 검증 완료  
다음 대상: `weather_map`, `classroom`, `port_emergency`, `retail_shock`

## 1. 이 문서의 목적

이 문서는 V5의 정보형 이미지에서 발생했던 실패를 같은 방식으로 다시 겪지 않도록 하는 **archetype별 검증 절차서**다. 다음 4개 archetype을 검증할 때에는 이 문서의 준비 → 단일 호출 → 육안 판정 → 보정 순서를 그대로 따른다.

이 문서는 다음을 자동 승인하지 않는다.

- 새 이미지 API 호출
- 자동 재시도
- 실제 금융 수치를 AI 프롬프트에 주입
- Pillow/FFmpeg 실수치 오버레이 구현

실제 호출은 각 archetype별로 별도 비용 승인을 받은 뒤에만 한다.

## 2. V5의 고정 원칙

1. **AI의 영문·숫자는 장식이다.** 그림의 재질·원근·조명에 녹아드는지 검증하는 용도일 뿐, 사실값으로 사용하지 않는다.
2. **검증된 수치·등락률·출처 표기는 결정론적 합성으로만 넣는다.** 같은 물리 표면의 좌표에 Pillow/FFmpeg로 나중에 합성한다.
3. **정보를 담는 물리 표면은 한 장면에 정확히 하나다.** 다른 모든 소품은 바늘, 색 블록, 도형, 그래프 실루엣, 비문자 재질만 허용한다.
4. **"표면 하나"를 추상적으로 쓰지 않는다.** 물체의 위치·형상·연결 관계까지 적는다.
5. **모델이 대체할 만한 물체를 먼저 금지한다.** 독립 명패, 별도 LCD, POS 화면, 안내판, 카드 같은 일반 대체물뿐 아니라 무대 테마에 맞는 상자·가격표·지도 콜아웃도 포함한다.
6. **한 번의 호출은 한 번의 비용이다.** `max_attempts=1`을 유지하고 503/실패를 자동 재시도하지 않는다.

## 3. 통과 기준

한 archetype은 아래 세 항목이 모두 충족될 때만 통과다.

| ID | 육안 통과 기준 | 실패로 판정할 예 |
|---|---|---|
| P1 | 지정 primary 표면 안에 짧은 장식 영문/표본 수치 2~3개와 단순 그래프·다이어그램이 자연스럽게 있다. | 텍스트가 없거나, primary 밖의 별도 명패·카드·LCD에 있다. |
| P2 | primary 외 모든 소품은 읽을 수 있는 문자·숫자가 없는 비문자 상태다. | 계기판, 상자, 제품 포장, 지도 콜아웃, 카메라, 문서 등에 글자가 흩어진다. |
| P3 | 로고·한글 자막·워터마크가 없으며, 내부 프레임/만화 칸 분할/떠 있는 UI 카드가 없다. | 채널 로고, 깨진 한글, 워터마크, 별도 대시보드 패널, 포스트잇형 숫자 카드가 보인다. |

`P1`만 맞아도 통과가 아니다. `P1 + P2 + P3` 전체를 충족해야 한다.

## 4. 호출 전 공통 준비 절차

### 4.1 코드와 계약 확인

확인 위치:

- `backend/fastapi-workers/app/v5/scene/prompt_builder.py`
  - `ARCHETYPES`: 실제 무대·소품 정의
  - `build_prompt()`: primary 계약과 전체 exclusions 조립
  - `_fact_surface_contract()`: 하나의 primary 표면과 비-primary 비문자 계약
  - `_primary_substitute_ban()`: archetype별 대체물 금지
- `backend/fastapi-workers/app/v5/scene/scene_type_archetypes.py`
  - `ARCHETYPE_SURFACES`: 물리 표면 목록
  - `recommend_v5_archetype()`: scene_type에서 무대 추천

호출 전 반드시 아래를 텍스트로 확인한다.

1. `primary_physical_surface`가 실제 `ARCHETYPES`에 있는 소품인지
2. primary 문장이 물체의 **위치와 형상**을 충분히 특정하는지
3. stage/props/visual_detail에 나온 모든 비-primary 소품이 비문자 지시에 포함됐는지
4. standalone plaque, detached card, independent screen 등 archetype별 대체물이 금지됐는지
5. primary에 `MUST visibly include at least two or three short, clearly readable decorative English labels or sample figures`가 남아 있는지

### 4.2 새 archetype 전수 조사표 작성

코드를 수정하기 전에 아래 표를 채운다.

| 항목 | 반드시 기록할 내용 |
|---|---|
| 무대 | `ARCHETYPES.stage` 원문 요약 |
| 명시 소품 | `props`와 `visual_detail`에서 나온 모든 주요 물체 |
| primary | 단 하나. 위치·재질·주변 물체와의 연결 관계까지 지정 |
| 일반 대체물 | 명패, 별도 보드, LCD, 모니터, 카드, 간판 등 |
| 테마 대체물 | 해당 무대에서 모델이 의미상 텍스트를 넣고 싶어할 소품 |
| 비-primary 목록 | 화면·게이지·문서처럼 일반화하지 말고, 물체 이름을 전부 나열 |

이 사전 조사표는 이미지 호출 전에 사람 검토를 받는다.

### 4.3 비용·감사 사전 점검

| 점검 | 기준 |
|---|---|
| 단가 | `V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD=0.14` 설정을 확인한다. |
| 시도 횟수 | 해당 archetype 1장, `max_attempts=1`, 자동 재시도 없음 |
| 원장 | HTTP 요청 직전 reserved/예산 점유 기록이 생성돼야 한다. |
| 로그 | Gemini API Logs가 활성화되어 request ID·상태 코드를 남길 수 있어야 한다. |
| 사후 | 성공/실패와 무관하게 manifest·request ledger를 확인하고, 성공분은 콘솔 실비와 대조한다. |

## 5. 이미 통과한 3개 archetype: 실제 검증 이력

### 5.1 `data_lab` — primary를 비문자 지시에서 명확히 분리

| 항목 | 내용 |
|---|---|
| primary | `one central holographic map panel` |
| 초반 실패 | 비-primary 억제는 됐지만 primary에도 읽을 수 있는 장식 문자가 거의 생성되지 않았다. |
| 원인 | "장식 문자를 넣어도 된다"는 허용형 표현이 전체 비문자 지시보다 약했다. |
| 보정 | primary에는 읽을 수 있는 장식 영문/표본 수치 2~3개를 **반드시** 넣고, primary 이외의 표면만 비문자라는 예외 관계를 문장으로 분리했다. |
| 통과 관찰 | 지도 안에 `GLOBAL DATAFLOW`, `MARKET NODE`, `SAMPLE 45.2%`가 통합되고, 콘솔·보조 패널은 비문자였다. |
| 최종 이미지 | `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/generated_backgrounds/kospi_july_2026_scene_type_primary_text_v3/kospi_july_01.png` |

**재사용 교훈:** "허용"이 아니라 `MUST`를 사용하고, 비-primary 금지 문장은 반드시 `OTHER THAN the primary`로 작성한다.

### 5.2 `trade_calculator` — 모호한 받침 지정을 실제 저울 받침으로 좁힘

| 항목 | 내용 |
|---|---|
| primary | `the broad engraved front plinth directly beneath the scale's central pillar` |
| 초반 실패 | 텍스트가 저울 받침이 아니라 전경의 독립 명패와 차트 옆으로 이동했다. |
| 원인 | "balance-scale base의 front face"가 넓고 모호해서 모델이 그럴듯한 정보 명패를 대체 표면으로 선택했다. |
| 보정 | 기둥 바로 아래의 넓은 각인 받침이라고 위치를 구체화하고, `freestanding information plaque`, `desk display`, `framed dashboard`, `separate board`, `podium sign`을 명시적으로 금지했다. |
| 통과 관찰 | `TRADE BALANCE`, `+$1.5T`, `EXPORT VALUE`가 저울 받침 전면에 집중되고, 계기판·콘솔·차트 아이콘은 비문자였다. |
| 최종 이미지 | `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/generated_backgrounds/kospi_july_2026_trade_primary_v5/kospi_july_02.png` |

**재사용 교훈:** primary를 "사물 이름"으로만 지정하지 말고, 주변 기준점과 결합한 물리 위치로 적는다. 그럴듯한 독립 정보판은 이름까지 써서 금지한다.

### 5.3 `risk_control_room` — 누락된 테마 소품까지 비문자 목록에 포함

| 항목 | 내용 |
|---|---|
| primary | `the single large central analog gauge dial face embedded at eye level in the curved operations wall` |
| 초반 실패 | 중앙 게이지는 성공했지만, 좌측 하단 shipping crate에 `GLOBAL TRADE`가 새었다. |
| 원인 | 경고판·콘솔·보조 게이지는 금지했지만, 위험 테마와 잘 어울리는 `shipping crate`가 비문자 목록에서 빠졌다. |
| 보정 | primary를 벽의 눈높이 단일 대형 게이지 문자반으로 구체화하고, 경고 명판·독립 화면·알림 패널뿐 아니라 secondary gauge, control dial, signal lamp, floor marking, wall indicator, **shipping crate, closed umbrella**를 모두 비문자로 지정했다. |
| 통과 관찰 | `HIGH RISK`, `VOLATILITY`, `DANGER`가 곡면 게이지 문자반에 통합되고, 상자·우산·기타 계기판은 비문자였다. |
| 최종 이미지 | `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/generated_backgrounds/kospi_july_2026_risk_primary_v7/kospi_july_03.png` |

**재사용 교훈:** 비-primary 목록에는 "텍스트를 담기 쉬운 UI 소품"만이 아니라, 무대 테마와 의미상 맞는 모든 서사 소품을 포함한다.

## 6. 새 archetype 1개를 검증하는 표준 사이클

```text
소품 전수 조사표 작성
  → primary 1개·대체물 금지 목록 사람 승인
  → 프롬프트 문자열만 검토(비용 없음)
  → Gemini 1장 호출(max_attempts=1)
  → P1/P2/P3 육안 판정
  → 통과: 원장·콘솔 대조 후 다음 archetype
  → 실패: 실패 표면만 특정해 해당 archetype 규칙만 보정
```

### 6.1 실패 유형별 대응표

| 관찰된 실패 | 먼저 확인할 원인 | 보정 방식 | 건드리지 않을 범위 |
|---|---|---|---|
| primary에 텍스트가 없다 | `may`/`can`처럼 약한 허용형 지시인지, 비문자 지시가 primary까지 덮는지 | primary에 `MUST include 2–3`를 넣고 `OTHER THAN primary`로 분리 | 이미 통과한 다른 archetype의 문구 |
| 별도 명패·카드에 텍스트가 생김 | primary 위치가 모호한지, 대체물 금지가 없는지 | 실제 물체의 위치를 더 좁히고 독립 명패/카드/화면 이름을 금지 | scene_type 매핑·비용 게이트 |
| 다른 소품에 텍스트가 샘 | 전수 목록에서 빠진 테마 소품이 있는지 | 누락 소품을 개별 이름으로 비문자 목록에 추가 | primary의 성공한 표현 |
| 로고·한글·워터마크가 생김 | 참조 자산/순서, 공통 exclusions, 모델 결과를 확인 | 참조 해시·payload 순서·공통 exclusions부터 점검 | 임의의 새 이미지 대량 생성 |
| 503/타임아웃 | 서버 가용성인지 요청 오류인지 로그 확인 | 실패를 ledger에 남기고 **사용자 승인 후** 단 한 번 수동 재시도 | 자동 재시도·무단 다중 호출 |

## 7. 결과 보고 템플릿

각 호출 뒤에는 아래 정보를 한 번에 보고한다.

```md
### [archetype] 1회 검증 결과

- 호출: 1회 / 자동 재시도 없음
- 상태: 200 성공 | 503 실패 | 기타
- primary: [정확한 표면 문장]
- P1 primary 집중: 통과 | 실패 — [실제 위치]
- P2 비-primary 비문자: 통과 | 실패 — [소품 이름과 보이는 텍스트]
- P3 오염/분리 UI 없음: 통과 | 실패 — [증거]
- 비용: 원장 추정 [금액], 콘솔 대조 [완료/대기]
- 다음 조치: 통과 확정 | 해당 archetype만 보정 | 사용자 승인 대기
```

"대체로 좋아 보인다" 또는 "다른 archetype도 아마 통과"는 판정으로 사용하지 않는다. 세 기준과 실제 텍스트 위치를 함께 적어야 한다.

## 8. 남은 4개 적용 전 체크리스트

- [ ] `weather_map` 전수 조사표와 primary/대체물 금지안을 먼저 검토
- [ ] `classroom` 전수 조사표와 primary/대체물 금지안을 먼저 검토
- [ ] `port_emergency` 전수 조사표와 primary/대체물 금지안을 먼저 검토
- [ ] `retail_shock` 전수 조사표와 primary/대체물 금지안을 먼저 검토
- [ ] 각 archetype은 선행 archetype이 통과·콘솔 대조될 때까지 유료 호출하지 않음
- [ ] 정확한 금융 수치·등락률·출처는 이미지 모델이 아니라 검증 자료와 결정론적 오버레이로만 처리

## 9. 현재 완료 상태

| archetype | primary 표면 검증 | 다음 행동 |
|---|---|---|
| `data_lab` | 통과 | 규칙 동결, 재생성하지 않음 |
| `trade_calculator` | 통과 | 규칙 동결, 재생성하지 않음 |
| `risk_control_room` | 통과 | 규칙 동결, 재생성하지 않음 |
| `weather_map` | 미검증 | 사전 조사표 검토 후 1회 호출 승인 필요 |
| `classroom` | 미검증 | 사전 조사표 검토 후 1회 호출 승인 필요 |
| `port_emergency` | 미검증 | 사전 조사표 검토 후 1회 호출 승인 필요 |
| `retail_shock` | 미검증 | 사전 조사표 검토 후 1회 호출 승인 필요 |

이 플레이북은 앞선 세 번의 성공을 "모델이 알아서 잘했다"가 아니라, **구체적 primary 지정 + 대체물 금지 + 소품 전수 비문자화 + 단일 호출 검증**이 만든 재현 가능한 결과로 다룬다.

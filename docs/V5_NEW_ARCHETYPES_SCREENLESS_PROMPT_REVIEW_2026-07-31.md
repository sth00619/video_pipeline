# V5 신규 Archetype 4개: 화면형 보조 소품 금지 프롬프트 검토

작성일: 2026-07-31  
상태: **실제 이미지 호출 전 검토용 — 승인 대기**  
범위: `earnings_stage`, `briefing_podium`, `real_estate_office`, `job_market_hall`만. 기존 7개 archetype 규칙은 변경하지 않는다.

## 1. 배치 1 공통 결함과 보정

배치 1에서 `briefing_podium`과 `job_market_hall`은 primary 벽면의 텍스트 집중(P1)은 성공했지만, primary 밖에 **글자 없는 모니터/키오스크/색 블록 화면**을 새로 만들었다. 이는 텍스트 누출(P2-T)은 아니어도, 이후 텍스트가 생기면 primary를 대체할 수 있는 정보 표면이므로 P2-F 실패다.

따라서 신규 4개에는 다음 상위 계약을 추가했다. primary 자체는 예외이며, primary 밖에서만 적용된다.

```text
Outside the designated primary surface, do not create any monitor, screen,
display, dashboard, kiosk, digital signage, teleprompter, or screen-shaped
rectangular information device at all, even when blank or filled only with
color blocks. Use only scene-native physical objects, lighting, material
texture, abstract geometry, and non-screen silhouettes for background density.
```

이 문장은 각 프롬프트의 다음 세 구역에 반복 삽입되었다.

1. `fact_surface_contract` — primary 외 정보 표면을 원천 금지
2. `background_information_density` — 배경 밀도를 화면형 장치 없이 채우도록 지정
3. `exclusions` — 모델이 빈 모니터/색 블록 모니터로 우회하는 경로 차단

또한 이 네 archetype에서만 기존의 일반 문장 `Every other gauge, screen, ...`도 `Every other gauge, map, ...`으로 좁혔다. 즉 “보조 화면은 색 블록으로 채운다”는 해석 여지를 제거했고, 배경 밀도는 화면이 아닌 현장 물체·조명·재질·추상 기하·비화면 실루엣으로 채우게 했다.

드라이런 결과 네 프롬프트 모두 위 문장이 **3회** 포함됐고, primary의 장식 영문/표본 수치 의무 문장은 **1회** 포함됐다. 실제 API 호출은 수행하지 않았다.

## 2. archetype별 검토 대상

| Archetype | primary 정보 표면 | 추가 개별 방지 규칙 | 전체 프롬프트 |
|---|---|---|---|
| `earnings_stage` | 발표대 바로 뒤 중앙 벽에 매립된 단일 실적 브리핑 표면 | 독립 LED 보드, 발표대 명패, 프리스탠딩 슬라이드, 측면 화면, 티커 스트립, 별도 보고 카드 금지 | [prompt.txt](../backend/fastapi-workers/out/v5_archetype_validation/earnings_stage_screenless_review_v2/prompt.txt) |
| `briefing_podium` | 중앙 발표대 바로 뒤 중앙 벽에 매립된 단일 정책 브리핑 표면 | 발표대 명패, 텔레프롬프터, 프레스 배지, 측면 화면, 로워서드, 부유 경보 패널 금지 | [prompt.txt](../backend/fastapi-workers/out/v5_archetype_validation/briefing_podium_screenless_review_v2/prompt.txt) |
| `real_estate_office` | 상담 데스크 바로 뒤 벽에 고정된 단일 시장·대출 안내 보드 | 창문 매물표, 매물 표지, 가격표, 모니터, 독립 금리 패널 금지. 계산기 액정은 숫자·기호·막대·의사문자 없이 완전히 빈 물리 계산기로 고정 | [prompt.txt](../backend/fastapi-workers/out/v5_archetype_validation/real_estate_office_screenless_review_v2/prompt.txt) |
| `job_market_hall` | 중앙 상담 카운터 바로 뒤 벽에 고정된 단일 고용 동향 안내 보드 | 채용 공고지, 번호표 화면, 키오스크 화면, 카운터 명패, 독립 채용 보드 금지. 번호표 기계는 화면 없는 기계식 종이 배출기, 이력서 폴더는 종이가 보이지 않게 닫힘 상태로 고정 | [prompt.txt](../backend/fastapi-workers/out/v5_archetype_validation/job_market_hall_screenless_review_v2/prompt.txt) |

## 3. 사람이 확인할 핵심 문구

### 모든 신규 4개에 공통

```text
The only permitted information-bearing prop is [지정된 primary 표면].

The designated primary prop MUST visibly include at least two or three short,
clearly readable decorative English labels or sample figures ... directly inside
that same physical prop.

Outside the designated primary surface, do not create any monitor, screen,
display, dashboard, kiosk, digital signage, teleprompter, or screen-shaped
rectangular information device at all, even when blank or filled only with
color blocks.
```

### 부동산 상담실 계산기 예외 처리

```text
The desk calculator display must remain completely blank and empty, showing no
digits, symbols, labels, bars, chart marks, or pseudo-writing; it is a physical
calculator, not a second information surface.
```

### 고용 상담장 번호표·이력서 예외 처리

```text
The queue-ticket machine must be a mechanical paper dispenser with no screen or
display, and all resume folders must stay closed with no visible paper face.
```

## 4. 다음 실행의 판정 기준

재생성 후 각 이미지에서 독립적으로 다음을 판정한다.

- **P1**: primary 하나에 장식 영문/표본 수치 2~3개와 간단한 그래프·도식이 무대 재질·조명·원근에 맞춰 통합됐는가.
- **P2-T**: primary 외 소품에 읽을 수 있는 문자·숫자·라벨이 없는가.
- **P2-F**: primary 외에 새 모니터·화면·대시보드·키오스크·사각 정보장치가 생기지 않았는가. 새 비문자 소품이 생기면 무대 상식, 배경 크기·위치, primary 대체 가능성의 3문항을 모두 통과해야 한다.
- **P3**: 한글, 로고, 워터마크, 프레임 위에 분리된 UI 카드가 없는가.

## 5. 회계 및 실행 경계

- 이번 검토용 드라이런: API 호출 0건, 비용 0원.
- 다음 유료 실행: 네 archetype을 각각 1회씩 병렬 호출, `max_attempts=1`, 자동 재시도 없음.
- 호출 직전 각 요청을 원장에 별도로 reserve하고, 결과는 네 archetype별로 독립 판정한다.
- 실행 후 콘솔 대조 전까지 원장은 `unverified_until_console_reconciliation` 상태를 유지한다.

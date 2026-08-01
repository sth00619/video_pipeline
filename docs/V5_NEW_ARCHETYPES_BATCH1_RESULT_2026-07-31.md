# V5 신규 4개 Archetype 병렬 1차 결과

작성일: 2026-07-31  
실행: 4개 동시 단건 호출, `max_attempts=1`, 자동 재시도 없음  
예약 추정: 요청당 `$0.14 / ₩254`, 실제 청구는 콘솔 대조 전까지 미확정

## 요청 결과

| archetype | run | HTTP 결과 | 이미지 판정 | 다음 조치 |
|---|---|---|---|---|
| `earnings_stage` | `earnings_stage_primary_v1` | 503 `UNAVAILABLE` | 이미지 없음 | 가용성 회복 뒤 수동 1회 재시도 여부 별도 승인 |
| `briefing_podium` | `briefing_podium_primary_v1` | 200 | P1·P2-T·P3 통과, **P2-F 실패** | 이 archetype만 프롬프트 보정 후 재생성 여부 승인 필요 |
| `real_estate_office` | `real_estate_office_primary_v1` | 503 `UNAVAILABLE` | 이미지 없음 | 가용성 회복 뒤 수동 1회 재시도 여부 별도 승인 |
| `job_market_hall` | `job_market_hall_primary_v1` | 200 | P1·P2-T·P3 통과, **P2-F 실패** | 이 archetype만 프롬프트 보정 후 재생성 여부 승인 필요 |

## 성공 이미지의 독립 판정

### briefing_podium

- **P1 통과**: 벽 매립 브리핑 표면에 `POLICY UPDATE`, `Q4 FORECAST`, `+15%` 및 막대그래프가 자연스럽게 결합됐다.
- **P2-T 통과**: 발표대·마이크·카메라·객석·조명에는 읽을 수 있는 문자·숫자가 없다.
- **P2-F 실패**: 좌측 배경과 우측 상단에 별도 모니터가 추가됐다. 글자는 없지만 모두 차후 텍스트가 생기면 primary를 대체할 수 있는 화면형 정보 표면이다. `secondary screen must remain non-textual`은 형태를 허용하는 지시라 충분하지 않았다.
- **P3 통과**: 한글·로고·워터마크·프레임 밖 UI 오염은 없다.

보정 후보: `side monitor`, `wall display`, `broadcast display`, `digital signage`, `secondary screen`을 비문자 허용이 아니라 **소품 자체를 생성 금지**로 전환하고, 비-primary의 색·조명 밀도는 벽 리본·마이크·카메라·객석·케이블·조명으로만 구성한다.

### job_market_hall

- **P1 통과**: 중앙 벽 고정 고용 동향 보드에 `EMPLOYMENT TRENDS`, `JOB MARKET STABLE`, 상승 막대·추이선이 자연스럽게 집중됐다.
- **P2-T 통과**: 나머지 화면·키오스크·서류에는 명확히 읽을 수 있는 텍스트가 없다.
- **P2-F 실패**: 천장/벽의 보조 모니터, 전경 키오스크, 문서형 큐가 모두 텍스트가 생기면 primary와 경쟁할 수 있는 정보 표면이다. 특히 키오스크와 이력서 묶음은 구직 공간의 테마와도 강하게 맞아 모델이 다음 생성에서 문자·숫자를 넣을 위험이 높다.
- **P3 통과**: 한글·로고·워터마크·분리 UI 오염은 없다.

보정 후보: `queue-ticket machine`을 화면 없는 기계식 번호표 배출구로 좁히고, 키오스크·보조 모니터·독립 안내판·문서 더미·벽 공고 묶음을 소품 자체부터 금지한다. 비-primary 정보 밀도는 칸막이·가방·조명·사람 실루엣·비문자 직업 아이콘으로만 유지한다.

## 503 상태

`earnings_stage`와 `real_estate_office`는 같은 Gemini 응답을 받았다.

```text
HTTP 503 / UNAVAILABLE
This model is currently experiencing high demand.
```

이 응답은 프롬프트·참조 자산·모델 ID 오류가 아니라 서버의 일시적 고수요를 의미한다. 두 run은 영속 원장에 실패 상태로 기록됐고 자동 재시도는 실행되지 않았다. 실제 과금 여부는 Gemini 콘솔 로그/지출과 대조해야 한다.

## 회계 범위

이번 배치는 HTTP 요청 4건이며 예약 추정은 **$0.56 / ₩1,016**이다. 성공 2건과 503 2건 모두 `unverified_until_console_reconciliation`으로 남긴다. 503이 과금되지 않았다고 가정하지 않는다.

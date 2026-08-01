# V5 신규 Archetype 화면형 보조 소품 금지 v2 결과

작성일: 2026-07-31  
실행: Gemini Pro Image 4개 병렬 단건 호출  
실행 조건: `max_attempts=1`, 자동 재시도 없음, 요청별 사전 reserve

## 1. 회계 상태

| Archetype | HTTP 결과 | 추정 비용 | 원장 상태 |
|---|---:|---:|---|
| `earnings_stage` | 200 | ₩254 | `unverified_until_console_reconciliation` |
| `briefing_podium` | 200 | ₩254 | `unverified_until_console_reconciliation` |
| `real_estate_office` | 200 | ₩254 | `unverified_until_console_reconciliation` |
| `job_market_hall` | 200 | ₩254 | `unverified_until_console_reconciliation` |
| 합계 | 4건 | **₩1,016** | 콘솔 대조 필요 |

자동 재시도와 수동 재시도는 수행하지 않았다.

## 2. 독립 시각 판정

| Archetype | P1: primary 집중 | P2-T: primary 외 문자 없음 | P2-F: 화면형 보조 표면 없음 | P3: 한글·로고·워터마크 없음 | 판정 |
|---|---|---|---|---|---|
| `earnings_stage` | 통과 — 중앙 벽 매립 실적 보드에 집중 | 통과 | **실패** — 양옆 벽에 별도 차트형 사각 프레임 2개가 생성됨 | 통과 | **부분 통과** |
| `briefing_podium` | 통과 — 벽 매립 브리핑 표면에 집중 | 통과 | 통과 — 카메라·좌석만 존재, 별도 화면 없음 | 통과 | **통과 후보** |
| `real_estate_office` | 통과 — 벽 고정 안내 보드에 집중 | 통과 | 통과 — 계산기 액정 비어 있음, 경쟁 화면 없음 | 통과 | **통과 후보** |
| `job_market_hall` | 통과 — 벽 고정 고용 안내 보드에 집중 | 통과 | **실패** — 우측 상단 모니터와 카운터 앞 키오스크 화면이 생성됨 | 통과 | **부분 통과** |

## 3. 판정 근거

### `earnings_stage`: P2-F 실패

중앙 보드는 primary로 자연스럽게 작동한다. 다만 양옆 벽의 막대·파이·추이선 프레임은 텍스트가 없더라도, 이후 문자가 생기면 독립 정보 표면으로 기능할 수 있는 사각형 화면/대시보드 형태다. 따라서 P2-F의 세 번째 질문(“primary의 대체물이 될 수 없는가”)에 아니오다.

### `briefing_podium`: 통과 후보

중앙 벽 보드, 연단, 카메라, 관객, 조명이라는 무대 상식에 맞는 요소만 있다. 카메라는 촬영 장비이고, 독립 정보 표면이나 텍스트 없는 모니터가 없다.

### `real_estate_office`: 통과 후보

정보는 벽 고정 보드 하나에 집중됐다. 상담 데스크의 계산기는 물리 계산기이며 액정이 비어 있고, 창문·서류·파일·집 모형은 primary를 대체할 수 있는 정보 표면으로 보이지 않는다.

### `job_market_hall`: P2-F 실패

중앙 보드는 primary로 작동하지만, 우측 상단의 검은 벽걸이 모니터와 카운터 앞 키오스크의 화면이 별도로 생성됐다. 전자는 화면형 물체 금지, 후자는 “번호표 기계는 화면 없는 기계식 배출기” 지시를 각각 위반한다.

## 4. 다음 단계 제안 — 실행하지 않음

이번 v2에서 동일 유형의 P2-F가 두 번 재발했다. 따라서 기존 프롬프트 문구를 더 세분화해 반복하기보다, 다음 단계는 승인 후 **QualityGate의 화면형 보조 표면 검출 규칙**을 설계·검증하는 방향을 우선 검토한다.

- `briefing_podium`, `real_estate_office`: 사람 확인 후 통과 확정 가능
- `earnings_stage`, `job_market_hall`: 이미지 재생성은 아직 하지 않음
- 두 실패 archetype은 P3 QualityGate 설계 승인 후, 검출·차단 또는 재생성 정책을 별도로 결정


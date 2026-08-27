# Google AI Studio 제보 초안 — Gemini 3 Pro Image 반복 503

이 문서는 사용자가 Google AI Studio의 Send feedback 또는 Google 지원 채널에 직접 붙여 넣을 수 있는 비민감 요약이다. API 키, 프롬프트 원문, 이미지 base64는 포함하지 않는다.

## 문제 요약

- 모델: `gemini-3-pro-image`
- 호출: `generateContent`, Standard service tier, 2K image output
- 반복 응답: HTTP 503, `UNAVAILABLE`
- 사용자 화면의 원문: `This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.`
- quota 초과/429가 아니라, 같은 모델·동일 payload에서도 503이 반복됨
- 성공과 실패가 같은 시간대에도 공존해 단순한 KST 시간대 규칙으로 설명되지 않음

## 재현 표본

아래 scene42·얼굴 v2·scene07 표본은 현재의 단일 재시도 소유자와 감사 원장 통제 아래에서 수집한 최근 재현 사례다. 뒤의 Job54 scene21 47건은 현재 정책 적용 전의 배경 참고 이력이며, 최근 재현 사례와 같은 집합으로 해석하지 않는다.

### 동일 scene42 payload 두 번

| 시작 KST | 내부 attempt ID | 결과 | 소요 | usageMetadata |
|---|---|---|---:|---|
| 2026-08-27 01:09:09 | `8729ad2c69e949f8b30887ff9bc202f8` | 503 UNAVAILABLE | 12.661초 | 없음 |
| 2026-08-27 01:33:14 | `2dac0c8918db43c08633f7c977a29c81` | 503 UNAVAILABLE | 8.159초 | 없음 |

두 요청의 payload SHA-256은 같고, 공급자 request ID는 응답 헤더에서 확인되지 않았다. 위 ID는 공급자 ID가 아니라 로컬 감사 원장 ID다.

### 얼굴 v2 3장 표본

| scene key | 내부 attempt ID | 결과 | 소요 |
|---|---|---|---:|
| `face-v2:2` | `56f0fabebbe24f4ebaa1681212bb5680` | 503 UNAVAILABLE | 10.252초 |
| `face-v2:7` | `246a77ba4da44508a39ec8c25b4e1b50` | 503 UNAVAILABLE | 7.144초 |
| `face-v2:35` | `f84afef34a064bfeba502f6a9e0f596a` | 503 UNAVAILABLE | 4.657초 |

### scene07 동일 payload canary

| 내부 attempt ID | 결과 | 소요 | payload SHA-256 |
|---|---|---:|---|
| `246a77ba4da44508a39ec8c25b4e1b50` | 503 UNAVAILABLE | 7.144초 | `b58ed621dd9d1bffb159109f3a5f8c03e05a4b1a86a2d4a139045f23df00a454` |
| `e7eb8f76e28241cfae233e29905ef6eb` | 503 UNAVAILABLE | 5.328초 | `b58ed621dd9d1bffb159109f3a5f8c03e05a4b1a86a2d4a139045f23df00a454` |

### 과거 Job54 scene21

**현재 정책 재현 표본이 아니라 배경 참고용 이력이다.**

- 총 원장 항목 47
- HTTP 503: 35
- HTTP 504: 9
- HTTP 200: 2
- 응답 미확정 reserved: 1

이 표본은 현재 단일 재시도 소유자 구현 전의 중첩 재시도 이력도 포함하므로, 47건 전체를 현재 코드의 한 요청 정책 결과로 해석하면 안 된다. 다만 빠른 503과 긴 504가 반복됐다는 공급자 응답 증거로 제공한다.

## 클라이언트 측 완화

- 공급자 POST는 한 계층만 소유
- 일시 오류에만 exponential backoff + equal jitter
- `Retry-After` 존중
- 장면별 현재 냉각 구간 3회 상한
- 3회 뒤 `needs_review`, 자동 재시도 없음
- 24시간 냉각 뒤에도 사용자 승인 및 동일 payload/계약 검증 필요
- 프로젝트 공유 냉각 및 전체 예약 예산 상한
- Flash 자동 폴백 없음

## 확인 요청

다음 세 항목은 모델 가용성과 API 운영에 관한 문의다.

1. 위 시간대에 `gemini-3-pro-image` Standard tier의 알려진 용량 제약 또는 지역별 장애가 있었는지
2. 응답 헤더에서 지원되는 공급자 request ID 또는 추적 ID가 별도로 있는지
3. 장시간 반복되는 503에 권장되는 최소 냉각 시간 또는 상태 엔드포인트가 있는지

## Cloud 결제 지원에 별도로 문의할 항목

다음 항목은 모델 가용성 제보와 섞지 않고 Cloud 결제 지원 채널에 별도로 문의한다.

- `usageMetadata`가 없는 503의 quota 집계 및 billing 처리 범위를 확인할 수 있는 공식 문서나 계정별 청구 근거가 있는지

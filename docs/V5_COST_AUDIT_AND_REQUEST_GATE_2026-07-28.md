# V5 비용 감사와 요청 단위 게이트

## 결론

- 2026-07-26 UTC의 17건은 V4 작업 `94302`, `94303`, `94304`의 원장 항목 수와 일치한다.
- 2026-07-27 UTC의 11건은 V5 P1-b의 7개 성공 결과, 중단된 8번째 요청, 503 재시도로 설명된다.
- 기존 V4/V5 원장은 **성공 장면 단위**로만 비용을 기록했다. 공급자 내부 재시도와 응답 대기 중 중단된 요청은 원장에 남지 않을 수 있었다.
- 과거 V4 실비는 콘솔 요청별 내역과 대조 전까지 `unverified_until_console_reconciliation`로 취급한다. 과거 원장을 추정값으로 덮어쓰지 않는다.

## V4 재시도 노출 범위

V4 작업은 `ImagesWorker`의 병렬 경로를 사용했다. 당시 기본 구성은 다음과 같다.

- `GEMINI_PARALLEL_ENABLED=true`
- `GEMINI_RETRY_MAX=3`: 장면 실패 시 최대 3회
- 병렬 경로의 공급자 호출은 `gemini_max_attempts=1`
- 단일 장면 경로는 `GEMINI_PRO_MAX_ATTEMPTS=5`를 공급자에 전달할 수 있음

따라서 기존 `cost_ledger.json`의 항목 수는 실제 HTTP 요청 수가 아니라 완료된 장면/템플릿 재생성 수다. V4 사전계획의 10% 재시도 완충은 최대 재시도 횟수를 예약하거나 실제 시도별로 차감하지 않았다.

## 수정된 계약

1. Gemini의 매 HTTP POST 직전에 비용을 `reserved` 상태로 원장에 기록하고 예산을 즉시 점유한다.
2. 503 등의 재시도도 독립된 원장 항목으로 기록한다.
3. 응답 상태 코드와 Google 요청 ID가 제공되면 요청 ID를 저장한다. 키, 프롬프트, 응답 본문은 저장하지 않는다.
4. 응답 대기 중 프로세스가 종료되면 `reserved` 항목이 남는다. 이는 콘솔 대조 전 비용을 0으로 처리하지 않기 위한 보수적 처리다.
5. V4의 기존 `record_cost()`는 같은 장면에 Gemini 요청 예약이 존재하면 사후 성공 비용을 중복 기록하지 않는다.
6. V5 P1 비교용 `GeminiProvider`는 `gemini_max_attempts=1`을 강제한다.

## 대조 절차

콘솔에서 `timestamp`, `model`, `method/resource`, `error message`, `request ID`를 가져온다. 원장의 `reserved_at`, `status_code`, `request_id`, `scene_key`, `attempt`와 대조한 뒤에만 실제 비용을 확정한다.

## 검증

네트워크 모사 테스트로 다음을 확인한다.

- 503 뒤 재시도는 두 개의 예약 항목으로 남는다.
- 예산을 넘는 예약은 POST 이전에 차단된다.
- V4 성공 후 `record_cost()`가 예약된 Gemini 시도를 이중 기록하지 않는다.
- V5 P1 비교는 공급자 내부 시도를 한 번으로 고정한다.

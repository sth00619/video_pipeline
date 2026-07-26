# Spring Boot 작업 규칙

- 7-gate 승인 흐름은 `VideoPipelineWorkflow`의 `approveGate()`/`rejectGate()` Temporal 시그널을 사용한다.
- `GateService`가 시그널을 발송할 때는 반드시 트랜잭션 커밋 이후에 실행한다. `TransactionSynchronizationManager` 패턴을 사용한다.
- 서킷브레이커는 기존 패턴을 재사용하고, YouTube `quotaExceeded`, Fal.ai 403, Gemini 503·429·billing 오류를 구분한다.
- 파일 다운로드는 JWT 인증 `fetch` 후 Blob URL 패턴만 사용한다. 직접적인 `<a href>` 링크는 사용하지 않는다.

# Gemini scene42 추가 1회 재시도 결과

## 1. 결론

승인된 추가 POST **1회**를 실행했다. **다시 HTTP 503 / UNAVAILABLE**로 실패했고,
이미지와 `usageMetadata`는 반환되지 않았다. **이번에도 사용량 실측을 얻지 못했다.**
세 번째 요청, 다른 scene 키/원장/모델로의 우회, 8장 파일럿, Claude·TTS·Fal·MP4는 실행하지 않았다.

| 구분 | 첫 시도 | 승인된 두 번째 시도 |
|---|---|---|
| 시작 KST | 2026-08-27 01:09:09.273345 | 2026-08-27 01:33:14.568948 |
| 완료 KST | 01:09:21.939534 | 01:33:22.733913 |
| HTTP / 오류 | 503 / UNAVAILABLE | 503 / UNAVAILABLE |
| 기록된 소요 초 | 12.660527422034647 | 8.15873704495607 |
| 누적 장면 시도 | 1 | 2 |
| 완료 후 failure_n | 1 | 2 |
| usageMetadata | 미반환 | 미반환 |

두 번째 attempt ID: `2dac0c8918db43c08633f7c977a29c81`.
검사한 응답 헤더에 공급자 request ID가 없었다. 내부 attempt ID를 공급자 식별자로 대신 주장하지 않는다.
`duration_seconds`는 monotonic 계측이다. 원장 예약/완료 시각 차이에는 기록 처리 시간도 포함되므로 정확히 같지 않다.

현재 SQLite 상태는 `count=2, n=2, active=NULL, status=needs_review`다.
프로젝트 실패 번호도 2이며 초기화하지 않았다. 냉각 종료 epoch는 `1787762034.2775416`,
완료 시각 기준 약 **31.543629초** 뒤다. 이는 두 번째 실패의 equal-jitter 범위 20~40초 안이다.
냉각이 끝나도 추가 승인이나 자동 실행을 의미하지 않는다.

원장의 `attempt=1`은 각 공급자 함수 호출의 내부 시도 번호다. 누적 시도는
`request_control.scene_attempt=2`로 확인한다. `attempt=1`을 누적 카운터 초기화로 해석하면 안 된다.

## 2. 증거와 원문 제공 여부

- [두 요청을 함께 보존한 원장](evidence/gemini_usage_retry2_20260827/request_ledger.json)
- [두 번째 실행 manifest](evidence/gemini_usage_retry2_20260827/manifest_retry2.json)
- [호출 전 입력 대조](evidence/gemini_usage_retry2_20260827/preflight_retry2.json)
- [추가 1회 승인 소비 기록](evidence/gemini_usage_retry2_20260827/retry_2.claim)
- [사후 재계산/상태 검증](evidence/gemini_usage_retry2_20260827/verification.json)

**제공할 공급자 usageMetadata 원문이 없다.** 아래는 원문이 아니라 원장이 기록한 부재 상태다.

```json
{
  "usage_metadata_status": "absent",
  "usage_metadata": null
}
```

토큰 수를 0으로 채우거나 가짜 응답 테스트 숫자를 실측으로 옮기지 않았다.
`usageMetadata_retry2.json` 및 `scene_042_raw_retry2.png`는 생성되지 않았다.

| 증거 파일 | SHA-256 |
|---|---|
| request_ledger.json | f9f016644e9f4288bd3f754d2d9caeea3a5a6e00c26f1cec6b5f6af9aea9daa3 |
| manifest_retry2.json | a45303a68c4bca24bd578d1bf437944cfc45ef5b3f028a4103dcc21f6525890a |
| 기존 manifest.json — 불변 | af2d625a6c2c0dd2054d932bc41459b43bceda37ee12f7e3cc54619d89f0ec88 |

## 3. 동일 요청과 실패 이력 보존

`gemini-3-pro-image`, Standard, 2K, 16:9, `image:42` → `scene:42`를 유지했다.
동일 영속 원장 `/app/data/pilots/usage_metering_20260827_scene42/request_ledger.json`을 사용했다.
원장 첫 행은 이전 manifest에 보관된 첫 요청 객체와 완전히 동일하다.
두 요청의 `request_evidence` 전체 객체도 동일하다.

- payload SHA-256: `f8ea5d570c82016d2feb0bb571b289f4e7c7367d56f7d4c8e10a76b9631ed013`
- 실제 프롬프트 SHA-256: `2fa239aed28238683d41bc1ea29505f4ad34e14e346add8573a02f0f4fb6567e`
- 계약 fingerprint: `4fc255095b4cd0bedfd5c1f0a8ce442c26d660e1fb475f7c4d9402152396fa6c`

내레이션·원래 입력 파일·참조 이미지 3장·중앙 가격 파일 해시를 전송 전에 대조했다.
이것은 **직전 실측 요청과 동일함**의 증거이지 Job52 당시 payload 복원 확정이나 시각 품질 승인 증거가 아니다.
기존 scene42의 생성 텍스트 계약과 V5 참조 선택도 바꾸지 않았다. 해당 원본 단계는 정보성 문구 합성이 완료된 이미지가 아니다.

## 4. 이번 최소 변경과 오프라인 검증

운영 코드 디렉터리나 컨테이너를 재시작하지 않고, 이전과 같은 격리 사본
`/tmp/wo_request_verify.vm7YND/backend/fastapi-workers`에서 검증/실행했다.
운영 영속 원장과 요청 상태 DB는 그대로 이어 썼다.

1. `run_gemini_usage_pilot.py`에 `--retry-of`, `--reservation-krw`를 추가했다.
   첫 503 실패의 다음 한 번만 대상이며 `retry_2.claim`을 배타적으로 생성한다.
   첫 claim/manifest/preflight를 덮어쓰지 않고 `_retry2` 결과를 별도로 기록한다.
2. `ProviderRequestAudit.before_attempt`는 원장 잠금 안에서 이전 attempt ID·누적 건수·503 상태·모델·
   실제 payload 증거·계약 fingerprint·failure_n을 검사한다. 소진된 승인이나 변경된 요청은 POST 전에 거부한다.
3. `ImageRequestControl.reserve`는 같은 SQLite 트랜잭션에서 직전 완료 요청과 실패 번호를 대조하고
   다음 슬롯을 예약한다. `needs_review`를 지우는 수동 SQL, 카운터/냉각 초기화는 사용하지 않는다.
   기존 전역 누적 최대 3회는 그대로이며, 이번 프로세스는 **누적 2회**까지만 허용했다.
4. 첫 요청은 한 번의 호출로 종료하고 두 번째 요청도 한 번으로 종료한다. 공급자 내부 중첩 재시도를 추가하지 않았다.

- 집중 검증: **95 passed, 1.39초** — [JUnit](evidence/gemini_usage_retry2_20260827/focused-pytest.xml)
- 전체 회귀: **949 passed, 19 warnings, 92.83초** — [JUnit](evidence/gemini_usage_retry2_20260827/full-pytest.xml)
- 이번 변경 5개 코드/테스트 파일: 작업 트리와 격리 사본 SHA-256 일치 — [hash 대조](evidence/gemini_usage_retry2_20260827/source-comparison.json)

신규 17개 테스트는 가짜 200/503, 원문 사용량 보존, 첫 행 불변, 승인 재사용 차단,
프롬프트/계약/이전 ID/실패 번호/건수 변경 차단, 예산·냉각·미확정 예약 차단,
claim 중복 차단, 입력/참조 변동 차단을 검증한다. 테스트 사용량 5/7 등은 실측이 아니다.

## 5. 예산 정정

**최초 ₩1,600 승인은 8장 파일럿의 전체 예산이었다. 요청당 단가나 확정 지출이 아니었다.**
이전 실행기가 그 전액을 첫 요청 예약에 배정한 것은 보수적인 구현 선택이지 사용자의 승인 취지가 아니다.
“추가 요청에는 반드시 또 ₩1,600이 필요하다”는 일반 규칙도 아니다.

이번에는 사용자가 반대하지 않는다고 명시한 보수적 대안인 **합산 예약 상한 ₩3,200**을 택했다.
원장에 `original_pilot_budget_krw=1600`, `authorized_combined_reservation_cap_krw=3200`,
`additional_reservation_krw=1600`, `cost_interpretation`을 남겼다.
이 추가 상한은 이번 단일 재시도의 불확실성 대비이며, 8장 전체 실행이나 향후 요청의 자동 승인이 아니다.

두 요청의 합산 `reserved_exposure_krw=3200`, 성공 추정 합계 `total_krw=0`이다.
**어느 값도 실제 청구액으로 확정하지 않았다.** `estimated_usd=1.142857…` 역시 각 예약액 ÷ 중앙 환산율 1400이며
관측 사용량에 기반한 비용 견적이 아니다. 기존 첫 요청 예약/청구 미확정 상태를 소급 삭제하지 않았다.

약 $0.134는 1K/2K 이미지 **출력분** 가격이다. 입력 및 텍스트/thinking은 별도이므로 이를 전체 요청의 비용 상한으로
사용하지 않는다. [Google 공식 가격표](https://ai.google.dev/gemini-api/docs/pricing#gemini-3-pro-image)
사용량을 받더라도 공급자 보고 사용량과 실제 청구서는 별개이며, 한 장 실측을 8장 전체의 확정 상한으로 일반화할 수 없다.
[Google 사용량 필드 정의](https://ai.google.dev/api/generate-content#UsageMetadata)

## 6. 판정과 다음 체크포인트

시작 간격 약 24분 5.296초를 둔 동일 요청 두 번에서 503이 반복됐다.
**이 시간대·이 요청 구성에서 503이 재현되었다**고는 말할 수 있다.
모델 전체의 상시 장애, 프롬프트가 원인, 특정 시간대가 인과적 원인이라는 결론은 두 관측만으로 확정하지 않는다.

사용자 조건에 따라 여기서 유료 호출을 멈췄다. 세 번째 시도나 다른 scene 키로 상한을 우회하지 않는다.
추가 승인 시 시간대를 바꾼 동일 키 검증을 검토할 수 있으며, 그 전에는 WO-IMG-01 텍스트 계약/
참조 자산 보존 같은 오프라인 준비를 진행할 수 있다. 이번 턴에는 그 별도 작업이나 Git 이력 재작성을 실행하지 않았다.

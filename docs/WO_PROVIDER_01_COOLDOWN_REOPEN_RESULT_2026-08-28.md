# WO-PROVIDER-01 — Gemini 503 냉각 재도전 정책 구현 결과

작성일: 2026-08-28 KST

범위: `gemini-3-pro-image` 503 운영 정책, 냉각 후 사용자 승인 재도전, 공식 상태 확인 기록

실행하지 않은 단계: Gemini/Claude/TTS/Fal/Kling/FFmpeg/영상 조립/썸네일

## 1. 결론

반복된 `503 UNAVAILABLE`은 저장소의 얼굴 v2·문자·물리 표면 계약 실패와 분리되는 공급자 가용성 실패다. 사용자가 보존한 응답 본문 `This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.`는 원장의 HTTP 503 및 `UNAVAILABLE`과 일치한다.

기존 단일 재시도 소유자, 지수 백오프, equal jitter, `Retry-After`, 오류 종류 한정, 장면별 3회 상한, 전체 예약 예산 상한은 그대로 유지했다. 추가 자동 재시도 계층은 만들지 않았다.

이번 변경은 `needs_review`를 영구 폐기 상태가 아니라 **현재 냉각 구간의 3회가 끝난 상태**로 표현한다. 다만 24시간이 지나도 자동으로 재개되지 않는다. 다음 조건이 모두 있어야 새 3회 구간의 첫 요청을 예약할 수 있다.

1. 사용자가 승인한 직전 503 attempt ID
2. 평생 원장 항목 수와 직전 `failure_n`의 정확 일치
3. 동일 모델·payload·prompt·참조 이미지·계약 fingerprint
4. 최초 `needs_review` 시각의 정확 일치
5. Google Cloud 공식 상태 대시보드 수동 확인 기록
6. 24시간 미만이면 별도의 명시적 냉각 override
7. 기존 전체 예약 예산 상한 안의 새 요청 예약 여유

유료 호출은 0회다. scene07·02·35와 scene42의 원장·이미지 상태를 변경하지 않았다.

## 2. 외부 근거 확인

공식 자료에서 확인한 범위는 다음과 같다.

- [Gemini API 오류 문제 해결](https://ai.google.dev/gemini-api/docs/troubleshooting): 503은 서비스 과부하 또는 일시적 가용성 문제이며 잠시 기다린 뒤 재시도하도록 안내한다.
- [Gemini API 오류 코드](https://ai.google.dev/gemini-api/docs/api-errors): `UNAVAILABLE`은 서비스가 일시적으로 과부하되었거나 내려간 경우로 설명하고 exponential backoff 재시도를 권장한다.
- [GenerateContent 오류 가이드](https://ai.google.dev/gemini-api/docs/generate-content/api-errors): 503은 용량이 일시적으로 소진된 상태로 설명하며, 지속될 경우 상태 확인과 피드백을 안내한다.
- [Google Cloud Service Health](https://status.cloud.google.com/): 2026-08-28 확인 시 대시보드는 `No broad severe incidents`를 표시했다. 이 대시보드에 광역 장애가 없다는 사실은 Gemini Developer API의 특정 이미지 모델 용량이 충분하다는 증거가 아니므로, 재시도 성공을 보장하는 신호로 사용하지 않는다.

사용자가 조사한 포럼 사례는 공급 제약이 프로젝트 외부에서도 발생한다는 보조 근거다. 구현 결정은 위 공식 문서와 우리 원장의 재현 데이터에 기반했다. 결제 등급 상향, Flash 폴백, Provisioned Throughput은 채택하지 않았다.

## 3. 구현

### 3.1 영속 상태 확장과 기존 DB 마이그레이션

`scenes` 테이블에 다음 필드를 추가했다.

- `first_needs_review_at`: 현재 냉각 구간이 처음 `needs_review`가 된 epoch
- `review_cycle`: 사용자 승인으로 다시 열린 냉각 구간 번호

기존 SQLite 파일을 지우거나 경로를 바꾸지 않는다. `PRAGMA table_info` 확인 후 빠진 열만 `ALTER TABLE`로 추가한다. 기존 `count`, `n`, `next`, `active`, `status`는 보존된다.

### 3.2 24시간 냉각과 명시 승인

정책 상수는 `24 * 60 * 60`초다.

- 승인 없음: 24시간 또는 48시간이 지나도 `count >= 3`이면 차단
- 24시간 미만 + 승인 + override 없음: 경고와 정확한 `next_allowed_at`을 반환하고 POST 차단
- 24시간 미만 + 승인 + 명시 override: 새 냉각 구간 1회차 예약 허용, `cooldown_override_used=true` 기록
- 24시간 이상 + 승인: 새 냉각 구간 1회차 예약 허용

새 구간을 열어도 `failure_n`과 프로젝트 백오프 번호를 초기화하지 않는다. 원장 항목도 삭제하지 않는다. `scene_attempt`만 현재 구간 기준 1부터 다시 세고, 평생 요청 수는 JSON 원장에 계속 누적된다.

과거 파일럿처럼 2회 상한에서 이미 `needs_review`가 된 장면도 현재 기본 상한 3으로 바뀌었다는 이유로 세 번째 요청을 바로 보낼 수 없다. scene07과 같은 과거 상태는 먼저 냉각 재도전 계약을 통과해 새 구간을 열어야 한다.

### 3.3 원장 유실 방어

상태 DB가 다시 만들어져도 평생 JSON 원장의 마지막 `approved_reopen_after_cooldown=true` 항목을 찾아 현재 구간 시도 수를 재구성한다. 승인된 재도전 마커가 한 번도 없다면 과거 원장 전체를 기존처럼 상한 계산에 넣으므로, Job54 scene21의 47회 이력이 새 객체·별칭으로 초기화되지 않는다.

### 3.4 공식 상태 확인 attestation

냉각 후 재도전 metadata에는 다음 객체가 필수다.

```json
{
  "source": "https://status.cloud.google.com/",
  "checked_at": "2026-08-28T09:00:00+09:00",
  "result": "no_official_incident",
  "incident_url": null
}
```

`source`는 Google Cloud 공식 상태 도메인이어야 하고 `checked_at`은 시간대가 있는 ISO-8601이어야 한다. `result`는 `no_official_incident` 또는 `official_incident_posted`만 허용한다. 장애가 게시됐다고 기록하면 같은 공식 도메인의 `incident_url`이 필수다. 이 객체는 요청 metadata와 함께 원장에 남는다.

이 기록은 상태 페이지를 봤다는 운영 attestation이지 모델 가용성 보증이 아니다. 자동 웹 조회나 유료 API 호출은 추가하지 않았다.

## 4. 선행 실패와 독립 재검증

| 단계 | 커밋 | 격리 결과 |
|---|---|---:|
| 냉각 재도전 선행 테스트 | `86fc714` | 9 failed, 54 passed |
| 냉각 재도전 최소 구현 | `09abd3e` | 64 passed |
| 상태 확인 선행 테스트 | `a0e7723` | 4 failed, 15 passed |
| 상태 확인 최소 구현 | `4eba123` | 68 passed |
| 과거 2회 검수 상태 선행 테스트 | `d61d29e` | 1 failed, 49 deselected |
| 과거 검수 상태도 냉각 계약으로 통일 | `2df08ef` | 69 passed |

각 커밋은 `git archive`로 `/tmp/wo_provider_verify.4h9v2x/`에 분리해 실행했다. 최종 archive의 핵심 파일 SHA-256은 작업 사본과 일치했다.

- `image_request_control.py`: `0fa7f75e900a7b8ae3374ee7c2d401fd92c7d4e0c0ca5261db42526067dab62c`
- `budget.py`: `9c6676d6885850d4815d7a4560f3932909e10be3d2b3854bd2c196effa314d62`

운영 Docker 이미지에 현재 저장소를 마운트한 최종 결과:

- 공급자 및 이미지 계약 집중 검사: 154 passed
- 공급자 계약 집중 검사: 69 passed
- 외부 Google RSS 통합 테스트를 제외한 전체 오프라인 검사: **1079 passed**, 20 warnings
- 외부 유료 호출: 0

증거:

- [냉각 정책 선행 실패](evidence/wo_provider_01_20260828/cooldown-red.xml)
- [상태 확인 선행 실패](evidence/wo_provider_01_20260828/status-check-red.xml)
- [과거 2회 검수 상태 선행 실패](evidence/wo_provider_01_20260828/legacy-two-attempt-red.xml)
- [공급자 집중 성공](evidence/wo_provider_01_20260828/provider-focused-green.xml)
- [전체 오프라인 성공](evidence/wo_provider_01_20260828/full-offline-green.xml)

## 5. 이미지 오프라인 항목과 경계

WO가 요구한 순서에 따라 유료 호출 전 현재 상태를 다시 확인했다.

| 항목 | 현재 판정 | 이번 WO에서 한 일 |
|---|---|---|
| 빈 물리 표면 | 8장 실측 뒤 프롬프트·로컬 픽셀 attestation 보완 완료, 새 실 API 미검증 | 관련 계약을 포함한 Docker 집중 회귀 통과. 게이트 완화 없음 |
| 의사문자 | 8장 중 비승인 문자·수치가 남아 전역 활성화 보류 | fail-closed 유지. 보이는 문자를 허용 목록 밖에서도 통과시키는 변경 없음 |
| `전망치` OCR | 육안상 정확하지만 전체 프레임 Tesseract가 안정 판독하지 못함 | 성공으로 재분류하지 않음. OCR 정확 대조 기준 완화 없음 |

따라서 이번 WO는 이 세 문제를 “해결 완료”라고 주장하지 않는다. 공급자가 200 이미지를 반환한 다음에도 얼굴 → 승인 문자열 → 비승인 문자 → 물리 표면 → OCR을 각각 독립 판정한다.

## 6. 예산·게이트 불변식

- 장면별 현재 구간 상한은 3회다.
- 새 구간은 자동으로 열리지 않는다.
- 24시간 미만 override도 사용자 승인 없이는 만들 수 없다.
- 전체 예약 상한을 넘으면 재도전 승인과 무관하게 차단한다.
- 503의 `amount_krw=0`은 성공 추정에서 제외했다는 뜻이며 무과금 확정이 아니다.
- `gemini-3-pro-image` 고정, Flash 폴백 금지를 유지한다.
- 얼굴 v2, 문자/수치, 물리 표면, OCR, Fal fail-closed 계약을 변경하지 않았다.
- scene42 동결을 유지했다.

## 7. 세 가지 큰 목표에서의 위치

아래 비율은 테스트 커버리지 수치가 아니라 남은 완료 조건을 반영한 보수적 작업 진척 추정이다.

| 큰 목표 | 보수적 진척 | 이번 작업의 의미 | Job52 예시 |
|---|---:|---|---|
| 1. 승인 대본·TTS·자막 시간 보정 | 약 60% | 변경 없음. 이번 공급자 작업은 승인 대본/TTS/자막 해시를 건드리지 않았다 | 짧은 자막 청크와 장면 의미 동기화는 기존 계약을 유지하지만 신규 5분 E2E 재검증이 남음 |
| 2. Fal/Kling의 국소 모션 | 약 30% | 문자·수치 표면을 계속 정지 대상으로 막았다 | scene35라면 구름·빗줄기·한 손만 후보이고 `전망치`·`경고` 표면은 정지. 아직 Fal 실파일럿 전 |
| 3. 이미지 의미·문자·수치·캐릭터 정확성 | 약 70% | 503 때문에 품질 검증이 중단돼도 요청 폭주·계보 우회 없이 나중에 같은 계약으로 재개 가능 | scene07이 503이어도 얼굴 v2가 실패했다고 오판하지 않고, 성공 이미지가 생긴 뒤에만 홍채/흰자/눈썹과 텍스트를 판정 |

이번 작업은 3번 목표의 품질 알고리즘을 직접 높인 것이 아니라, 이미 만든 얼굴·문자·수치 검증을 **공급자 불안정 때문에 잃거나 무단 반복하지 않게 하는 운영 기반**이다.

## 8. 다음 순서

1. scene07·02·35·scene42는 지금 상태로 유지한다.
2. 다음 유료 재도전 직전에 공식 상태 대시보드를 사람이 확인한다.
3. 상태 확인 객체, 동일 payload/계약 증거, 새 예약 예산, 사용자 승인을 포함한 명세를 만든다.
4. scene07 canary 한 장만 실행한다.
5. HTTP 503이면 즉시 중단한다. HTTP 200이면 공급자 성공과 얼굴/문자/표면/OCR 품질을 별도로 판정한다.
6. 이미지 승인 전 Fal/TTS/조립으로 진행하지 않는다.

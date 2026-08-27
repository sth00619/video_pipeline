# WO-REQUEST-01 구현 체크포인트 — 유료 8장면 파일럿 전

기준: 2026-08-26, Git `75ac1f5` 이후 작업 트리. 승인된 요청 제어 WO를 구현하고 오프라인 검증했다.
**운영 워커에는 미배포이며, 이 작업에서 Gemini/Anthropic/ElevenLabs/Fal 실생성·영상 조립을 실행하지 않았다.**
Job 52/54는 재개·재생성·수정하지 않았다. Git 커밋/푸시/필터/태그 삭제도 수행하지 않았다.

후속: [zero-padding 추가 검증·참조 25개 분류·파일럿 비용 보류](WO_REQUEST_01_PILOT_PREFLIGHT_2026-08-26.md).
아래 비용 예약 설명은 주입 단가 범위이며 입력/thinking을 포함한 실제 청구 상한 보장으로 해석하지 않는다.

## 1. 변경한 계약과 보존한 계약

- 공급자 한 번 호출 = 최대 한 번의 Gemini GenerateContent POST. 기존 `max_attempts` 인수로 중첩 재전송하지 않는다.
- SQLite 영속 제어기가 누적 한도, 실패 번호, 프로젝트 냉각을 소유한다. 워커는 보류 상태를 기록하고 반환한다.
- 원본·배경·표면 재생성·variation은 동일 장면 키로 합쳐 최초 포함 최대 3회다. 계약 hash/모델/감사 객체를 바꾸어도 초기화하지 않는다.
- HTTP 실패·네트워크 오류·HTTP 200의 이미지 해석 실패·QA 거절·표면 합성 거절을 구분한다.
- QA 실패 시 기존의 장면별 표적 수정 동작은 유지한다. 단, 추가 POST는 반드시 동일 영속 한도를 통과해야 한다.
- 이미지 프롬프트 본문, 참조 선택, 캐릭터/화풍/구도, 텍스트 정책, 승인 대본, TTS 목소리/속도/처리 설정은 변경하지 않았다.
- 새 감사 메타데이터가 기존 장면 계보 fingerprint를 바꾸지 않는 회귀 테스트를 추가했다.
- Fal의 대상/길이/동작 프롬프트는 변경하지 않았다. 추가한 것은 **미완료 이미지가 있는 작업의 Fal/조립 진입 차단**뿐이다.

## 2. 파일별 구현

| 파일 (`backend/fastapi-workers/` 기준) | 역할 |
|---|---|
| `app/utils/image_request_control.py` | SQLite 원자적 예약, 누적 장면 상한, 프로젝트 공유 냉각, Retry-After, 보류/조립 차단 계약 |
| `app/utils/budget.py` | 프로세스 간 원장 잠금, 요청 메타데이터/해시, QA 연결, 보수적 비용 노출액 |
| `app/providers/real/image.py` | POST 1회, 응답/이미지 해시 기록, 제어 예외 전달, 내부 sleep/retry 제거 |
| `app/workers/images_worker.py` | HTTP 재시도/자동 복구 라운드 제거, 장면별 보류, V4 OCR/비전 QA 연결 |
| `app/v5/providers/gemini_provider.py` | 보류 예외 보존, 반환 이미지에 실제 요청 계보 전달 |
| `app/v5/providers/router.py` | V5 QualityGate 결과를 동일 이미지 hash/attempt ID에 연결 |
| `app/workers/longform_worker.py` | 조립 직접 호출도 보류 상태를 먼저 확인 |
| `app/config.py`, `app/runtime_config.py`, `app/main.py` | 영속 저장 경로/프로젝트 설정과 런타임 장면 한도 |

## 3. 영속화와 재개 의미

기본 저장소는 `/app/data/provider_requests/gemini.sqlite3`다. 현재 Docker 워커는 `/app/data` 영속 볼륨을 사용한다.
SQLite `BEGIN IMMEDIATE` 예약과 비용 원장의 `flock` 읽기-수정-쓰기 잠금을 함께 사용한다.
원장 교체는 파일 및 디렉터리 fsync를 수행한다. 두 저장소 사이의 장애는 요청을 과소 집계해 재발송하는 대신
응답 미확정 예약을 남겨 차단하는 방향으로 처리한다. 원장/DB 손상을 빈 상태로 초기화하지 않는다.

- 범위 키: 영속 비용 원장 절대 경로 + 정규화된 scene ID. 모델/계약 hash는 범위 키가 아니다.
- `image:21`, `template_regen:21`, `background:21`, `scene-021`, `pilot:image:21`, `image:21:variation:1`은 같은 장면이다.
- 기존 원장의 시도 수도 한도에 포함한다. 기존 47회 원장을 새 감사 객체로 열어도 추가 요청할 수 없다.
- 진행 중 예약은 자동 만료시키지 않는다. 프로세스가 죽었을 때 실제 공급자 처리 여부를 모르면 수동 대조가 필요하다.
- 예약 직후 중지/공유 냉각 경합으로 미전송된 예약도 시도 한도를 자동 환급하지 않는 보수적 정책이다.
  따라서 상한에 도달했더라도 실제 POST 수는 3회보다 적을 수 있다. `not_dispatched`를 실요청/청구로 집계하지 않는다.
- `gemini_scene_request_limit`는 `/pipeline/config`로 1~3회만 설정할 수 있다. 4회 이상은 거절한다.
- 저장 경로/프로젝트 식별자 런타임 변경으로 상태를 초기화하지 못하게 했다.
- 예약 직전과 POST 직전에 Redis 중지 상태를 확인한다. 조회 불가 시 이미지 POST는 fail-closed다.

**재개는 현재 명시적 재호출 방식이다.** `next_allowed_at`을 저장한 뒤 즉시 반환하며, 같은 job/원장으로 다시 실행하면
그 시각 전에는 새 POST를 거절한다. 이번 변경은 Temporal/백그라운드 자동 예약 디스패처를 추가하지 않았다.
따라서 “정해진 시각에 자동 재발송까지 구현됐다”고 보고하지 않는다. 자동 실행이 필요하면 별도 디스패처 연결을 검토해야 한다.
대기 중 살아 있는 워커/수면 루프가 없으며, 중지 상태는 다음 재개 요청이 들어왔을 때도 확인한다.

### 백오프

`B = min(300, base × 2^n)`, `delay = U(B/2, B)`.
`base`는 기존 런타임 `gemini_pro_retry_base_seconds`를 따른다. 새 가격 상수나 모델은 추가하지 않았다.
장면 실패 번호와 프로젝트 실패 번호 중 큰 값을 사용하며, 프로젝트 연쇄 실패 번호도 재실행마다 초기화하지 않는다.
유효한 Retry-After(초/HTTP-date)가 있으면 그 최소 시각을 지킨다. 900초를 300초로 줄이지 않는다.
예약 후 다른 워커가 503을 받았을 때도 POST 직전 프로젝트 냉각을 다시 검사한다.
이미 발송된 요청까지 취소할 수 있다는 의미는 아니다.

## 4. 감사 증거의 정확한 의미

POST 전: attempt ID, run ID, scene 키, endpoint, model, tier, contract fingerprint, payload/prompt hash,
순서대로 전달한 참조 이미지 hash·byte 수·MIME.
POST 후: HTTP 상태, 공급자 오류 코드, 응답 헤더의 request ID(없으면 미상), 소요 시간, 저장한 이미지 SHA-256.

- `payload_sha256`은 **정렬된 키의 UTF-8 canonical JSON** 해시다. `payload_hash_basis`에 이를 명시한다.
  wire-level HTTP 바이트/헤더 전체의 해시 또는 과거 Job 52/54의 실제 송신 본문이라고 주장하지 않는다.
- V4 병렬 렌더는 기존 장면 fingerprint와 실행 run ID를 넘긴다. 별도 호출자가 넘기지 않으면
  `contract_fingerprint_source=payload_sha256`, `run_id_source=audit_session`이라고 구분해 기록한다.
- API 키/인증 헤더/base64/공급자 오류 본문 전체는 감사 원장에 쓰지 않는다.
- QA는 이미지 hash로 연결한다. hash가 없거나 후보가 모호하면 `link_status=unresolved`, attempt ID=null로 남긴다.
  마지막 요청을 무조건 QA 결과의 원인으로 붙이지 않는다.
- 이미지 합성 후 파일은 final hash를 별도로 기록한다. 기본 이미지와 합성 후 이미지가 같다고 가정하지 않는다.
- 과거 Job 54의 request ID 미연결·QA 미확정·청구 미확정은 이 신규 코드로 소급 해결되지 않는다.

### 비용 표기 정정

기존 실패 항목의 `cancelled_due_to_failure`는 실제 청구가 없다는 근거가 아니었다.
이제 `excluded_from_success_estimate_billing_unverified`로 기록한다.
`total_krw`는 성공/진행 중 비용 추정 합계이고, `reserved_exposure_krw`는 실패 응답을 포함한 보수적 예약 노출액이다.
새 Gemini 요청은 후자의 상한도 통과해야 한다. 실제 단가는 기존 중앙 설정을 사용한다.
청구 확정에는 공급자 콘솔과의 별도 대조가 필요하다. 기존 역사 원장을 재작성하거나 과거 청구를 확정하지 않았다.

## 5. 검증 결과

최종 전체 테스트 **899 passed, 19 warnings, 88.66초**. 집중 테스트 **68 passed, 2.29초**.
경고는 기존 matplotlib/Pillow 사용 중단 예정 API 경고다.
실행한 격리 사본과 현재 작업 트리의 변경 소스/테스트 **15개 파일 SHA-256이 모두 일치**함을 확인했다.

- [전체 JUnit 원장](evidence/wo_request_01_20260826/full-pytest.xml)
- [집중 JUnit 원장](evidence/wo_request_01_20260826/focused-pytest.xml)
- [검증 소스 SHA-256](evidence/wo_request_01_20260826/source-files.sha256)

최종 전체 명령:

```sh
docker exec -w /tmp/wo_request_verify.vm7YND/backend/fastapi-workers pipeline_fastapi \
  python -m pytest -q --junitxml=/tmp/wo_request_verify.vm7YND/wo-request-01-full.xml
```

집중 테스트는 유료 네트워크 대신 가짜 응답/시계/RNG를 사용한다. 검증 범위:

1. 누적 3회 상한, 변경된 계약/별칭/재개로 한도 우회 불가, 기존 원장 47회 차단.
2. 응답 종료 후 대기 계산, 재생성한 제어 객체에서도 실패 번호/예약 시각 유지.
3. 같은 프로젝트 다른 job 냉각 공유, 상한 300초에서도 `[150,300]` jitter 유지.
4. Retry-After 900초와 HTTP-date, 잘못된 값/NaN/음수 처리.
5. 별도 프로세스 6개 동시 예약에서 한 개만 점유, 여러 스레드의 원장/한도 원자성.
6. 감사 객체 누락, 원장 손상, Redis 중지/장애 시 POST 차단.
7. 실제 송신에 전달되는 payload 객체/참조/결과 이미지의 hash와 QA attempt ID 연결.
8. HTTP 200 이미지 해석 실패를 QA reject로 오집계하지 않음.
9. 워커 두 번 재실행 중 공유 냉각을 만나도 최초 POST 1회만 허용, 복구 라운드 없음.
10. 미완료 장면은 완료 manifest로 게시하지 않으며 조립 직접 호출도 Fal 이전에 차단.
11. V5 QA 이벤트 연결과 감사 메타데이터 추가 전후 장면 fingerprint 불변.

격리 테스트 사본을 만들 때 최초에는 scripts/참조/기존 입력 fixture 일부가 빠져 수집·파일 누락 실패가 있었다.
운영 코드나 원본 이미지를 바꿔 우회하지 않고, 필요한 기존 fixture를 읽기 전용 원본에서 사본으로 보충했다.
최종 검증은 Docker 서비스의 실행 소스가 아니라 `/tmp/wo_request_verify.vm7YND/` 아래 별도 사본에서 수행한다.

## 6. 파일럿 전 남은 조건과 한계

- 이 코드가 운영 프로세스에 반영됐는지는 **아직 미검증/미배포**다. 현재 서비스 동작이 이미 바뀌었다고 보면 안 된다.
- 단일 호스트/공유 로컬 볼륨 계약이다. 서로 다른 호스트가 각자 SQLite를 가지면 프로젝트 냉각을 공유하지 못한다.
  그 구성으로 확대할 때는 중앙 저장소 또는 동등한 분산 예약 계약이 필요하다.
- 감사 객체가 없는 기존 보조 호출은 자동 임시 원장을 만들어 우회하지 않고 차단한다.
  8장면 파일럿 호출자가 **고정된 job/scene/원장 경로와 예산**을 넘기는지 실행 전 확인한다.
- 실제 provider Retry-After/header 동작, 실측 지연, 비용 청구, 이미지 오탈자/화풍 품질은 이번 모의 테스트로 증명하지 못한다.
- 8장면 표본이 오류 0건이어도 5% 미만 결함률의 통계적 증거가 되지 않는다는 기존 59개 기준을 유지한다.
- 텍스트 정책 WO-IMG-01, 8장면 시각 파일럿, Fal 파일럿은 이번 요청 제어 구현과 구분한다. 아직 실행하지 않았다.

## 7. Git 체크포인트

읽기 전용 원격 재조회 결과 main=`75ac1f5`, apple=`0d8e26e`, assemble=`493a275` 유지.
원격 annotated backup tag 객체는 `b964fd1`, 대상 커밋은 `6fa5e79`다. 태그를 제거하지 않았다.
apple/assemble 활성 여부·담당자·동시 Git 작업 중지 확인은 사용자에게 질문했으며 응답 대기다.

추가 확인: `filter-generated-binary-paths.txt`의 766행부터 `out/references/` 경로 **25개**가 포함돼 있다.
실제 Gemini 참조 로더가 사용하는 자산 디렉터리이므로 이 필터 초안을 그대로 실행하면 안 된다.
이번에는 기존 manifest/백업/필터 목록을 변경하지 않았으며, 사람 확인과 함께 참조 보존 계획도 정정해야 한다.

운영 배포·유료 파일럿·force push는 수행하지 않고 이 증거 체크포인트에서 사용자 검토를 기다린다.

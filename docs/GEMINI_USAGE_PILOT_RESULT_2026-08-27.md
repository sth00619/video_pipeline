# Gemini 사용량 보존 패치 및 단일 호출 실측 결과

> 후속 정정: 최초 ₩1,600은 **8장 파일럿 전체 승인액**이었다. 아래 단일 요청 전액 예약은
> 당시 실행기의 보수적 할당 방식이며 사용자 승인 취지나 요청당 단가가 아니다.
> 승인된 추가 1회 결과와 예산 해석은 [두 번째 시도 보고서](GEMINI_USAGE_RETRY2_RESULT_2026-08-27.md)를 참조한다.
> 이 문서 본문과 연결된 첫 실행 원장/manifest는 첫 시도 시점의 증거다.

## 1. 결론

사용자가 승인한 순서대로 **사용량 저장 패치 → 오프라인 테스트 → 실제 GenerateContent 1회**를 진행했다.
실제 응답은 **HTTP 503 / UNAVAILABLE**, 소요 시간은 **12.6605초**였다.
이미지와 `usageMetadata`가 반환되지 않았으므로 **이번에는 thinking 토큰 실측을 얻지 못했다.**
이를 0토큰/무료 이미지/실측 성공으로 보고하지 않는다. 자동·수동 추가 호출은 하지 않았다.

실행 시각(KST): 2026-08-27 01:09:09.273345 → 01:09:21.939534.
운영 서비스를 재시작하거나 소스를 덮어쓰지 않고 격리된 코드 사본에서 실행했다.
Job 52/54, 승인 대본, TTS, 참조 픽셀, 캐릭터/스타일 선택 로직은 변경하지 않았다.
Claude·ElevenLabs·Fal 호출, 이미지 수정/재생성, MP4 조립, Git 이력 정리는 하지 않았다.

## 2. 사용량 파싱·저장 최소 패치

### `app/providers/real/image.py::_generate_gemini_api`

- HTTP 응답 JSON을 한 번 파싱하고 `usageMetadata` 객체만 원장에 넘긴다.
- `present` / `absent` / `invalid`를 구분한다. `{}`는 도착한 빈 객체로 보존한다.
- `promptTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount`, `totalTokenCount`뿐 아니라
  모달리티별 상세와 추가 필드도 객체 그대로 보존한다. 임의로 마스킹/축약/0 채움/차감 계산하지 않는다.
- HTTP 오류나 HTTP 200의 이미지 디코딩 실패에서도 응답에 포함된 사용량을 같은 attempt에 보존한다.
- 사용량 누락은 이미지 재생성 사유가 아니다. 송신 payload, 모델, 해상도, thinking 설정, 참조 선택을 변경하지 않았다.

### `app/utils/budget.py::ProviderRequestAudit.after_attempt`

원장 항목에 `usage_metadata`, `usage_metadata_status`, `usage_metadata_source`,
canonical JSON SHA-256인 `usage_metadata_sha256`을 추가한다.
기존 attempt ID·요청 hash·이미지 hash와 같은 행에 남긴다.
이는 JSON 객체의 값 보존이지 원본 HTTP wire bytes 보존이라는 뜻은 아니다.
사용량 객체 외 전체 응답·인증 헤더·이미지 base64·키는 원장에 기록하지 않는다.

**사용량 원장과 공급자 청구서는 다르다.** usageMetadata를 받더라도 해당 요청의 공급자 보고 사용량이 확인되는 것이며,
할인·크레딧·세금·모달리티별 청구 적용 및 실제 청구액은 별도 대조가 필요하다.
한 장의 사용량을 향후 8장/56장의 확정 총비용이나 상한으로 일반화하지 않는다.

필드 정의: [Google GenerateContent UsageMetadata](https://ai.google.dev/api/generate-content#UsageMetadata).
`candidatesTokenCount`는 생성 후보 토큰, `thoughtsTokenCount`는 사고 토큰, `totalTokenCount`는 전체 합계다.
어느 필드가 누락돼도 다른 필드로 보충한 값을 원문이라고 저장하지 않는다.

## 3. 오프라인 검증

실제 호출 전 집중 검증 **78 passed, 0.75초**.
전체 회귀 검증 **932 passed, 19 warnings, 100.01초**.
경고는 기존 matplotlib/Pillow 사용 중단 예정 API 경고다.

- [집중 JUnit](evidence/gemini_usage_pilot_20260827/focused-pytest.xml)
- [전체 JUnit](evidence/gemini_usage_pilot_20260827/full-pytest.xml)
- [격리 사본과 작업 트리 20개 파일 hash 일치](evidence/gemini_usage_pilot_20260827/source-comparison.json)

신규 검증 범위:

1. 가짜 200 응답의 usageMetadata가 attempt·request ID·이미지 hash와 함께 원장까지 동일하게 보존됨.
2. 일부 필드만 있는 객체, 빈 객체, 미래 추가 필드를 임의로 보충하거나 삭제하지 않음.
3. 누락/비정상 사용량은 별도 상태로 남기고 정상 이미지를 다시 생성하지 않음.
4. 사용량을 포함한 503 및 이미지 없는 200 응답에서도 사용량이 사라지지 않음.
5. 비JSON 200/503도 공급자 중첩 재시도 없이 한 번만 POST함.
6. 사용량 추가 전후 송신 payload가 동일함. 키/이미지 본문이 원장에 노출되지 않음.
7. 단일 실행 claim과 기존 원장이 재실행을 차단함. 중앙 가격 누락 시 숨은 단가로 폴백하지 않음.

최초 집중 실행에서 기존 테스트의 가짜 Response에 `.json()` 메서드가 없어 한 건 실패했다.
실제 requests.Response 계약과 같은 JSON 응답 메서드를 테스트에 추가한 뒤 다시 통과했다.
테스트 예시의 thinking 321토큰 등은 **가짜 fixture**이며 실측값이 아니다.

```sh
docker exec -w /tmp/wo_request_verify.vm7YND/backend/fastapi-workers pipeline_fastapi \
  python -m pytest -q tests/test_gemini_usage_metadata.py tests/test_gemini_usage_pilot.py \
  tests/test_provider_request_audit.py tests/test_image_request_control.py tests/test_v5_gemini_provider.py \
  --junitxml=/tmp/wo_request_verify.vm7YND/usage-metering-focused.xml
docker exec -w /tmp/wo_request_verify.vm7YND/backend/fastapi-workers pipeline_fastapi \
  python -m pytest -q --junitxml=/tmp/wo_request_verify.vm7YND/usage-metering-full.xml
```

## 4. 실제 호출의 입력과 경로

실행기: `backend/fastapi-workers/scripts/run_gemini_usage_pilot.py`.
별도의 Gemini 구현이나 다른 생성 도구를 만들지 않고 기존 `GeminiProvider.generate` →
`NanaBananaProvider.generate` → `_generate_gemini_api` 경로를 호출한다.

- 모델: `gemini-3-pro-image`, Standard, 2K, 16:9, 기존 IMAGE 모달리티.
- 입력: `artifacts/job52_full_audit_20260824/metadata/scene_generation_contracts.json`의 index 42.
- 입력 파일 hash: `72dd95c1f577acca6793d850567d045c28c7a0e5cd05f3229d9d105c8dc8cdf6`.
- 내레이션 원문: `첫째, 이익 전망치가 더 내려가는지인 겁니다. 애널리스트들의 전망치 흐름을 보세요.`
- 내레이션 hash: `097133103703bb30a10332944b170b272d37a8c9df01678729f33918e3892385`.

내레이션과 기존 영문 장면 프롬프트를 재작성하지 않았다. 기존 `_bounded_text_generation_prompt`와 현재 V5 참조 계약을
거친 송신 대상이므로 “Job 52 당시의 전체 HTTP payload를 그대로 재전송했다”는 뜻은 아니다.
최초 드라이런에 사용한 통합 `scenes.json`에는 장면 프롬프트의 연구복과 상충하는 후속 `scene_spec`의 요리사 의상이
있어, 실제 호출은 연구복 `art_direction`을 가진 원래 생성 계약 추출본을 사용했다. 전역 의상 로직은 수정하지 않았다.
이 두 파일의 내레이션은 위 hash로 동일함을 확인했다.

현재 scene42의 `screen_texts`는 null이다. 기존 텍스트 계약이 생성 문자열을 허용하지 않아 원본 프롬프트의
`ANALYST FORECAST` 표시 지시는 해당 원본 생성 단계에서 제거됐다. **전역 무문자 정책을 새로 도입한 것이 아니며,
이 샘플을 완성 이미지 또는 정보성 텍스트 합성 검증으로 취급하지 않는다.** 이번 범위는 사용량 계측뿐이다.
새 Claude 대본/장면 기획이나 유료 비전 QA도 호출하지 않았다.

전송된 참조 3개는 현재 선택 알고리즘의 결과다:

| 참조 | SHA-256 |
|---|---|
| channel_character_face_range_v1.png | 3d113c43e9395435d1b07b6e5a015c17e606b246e7a4f177bd3de4d074489c45 |
| channel_style_job52_risk_map.png | f9fd75a1622f865d3e81c4618ec3b4d8d35839c2de4c96daaba593beecda4337 |
| channel_style_job52_market_flow.png | c9e821d51a44d7184f84de92962e76b244c8794d49c87ea009f143948a303a74 |

원장/승인 소비 기록은 임시 디렉터리가 아니라 영속 볼륨
`/app/data/pilots/usage_metering_20260827_scene42/`에 저장했다.
실행 claim + 장면 한도 1 + 동일 원장 예산 예약으로 추가 실행을 차단한다.
프로젝트 공유 상태 경로/범위를 바꾸거나 기존 실패 카운터를 초기화하지 않았다.

## 5. 실응답 증거 및 usageMetadata 원문 요청에 대한 답

- [실제 요청 원장](evidence/gemini_usage_pilot_20260827/request_ledger.json)
- [입력·프롬프트·참조·결과 manifest](evidence/gemini_usage_pilot_20260827/manifest.json)

| 항목 | 실제 관측 |
|---|---|
| POST 횟수 | 1 |
| HTTP / 오류 코드 | 503 / UNAVAILABLE |
| 응답 대기 시간 | 12.660527초 |
| attempt ID | 8729ad2c69e949f8b30887ff9bc202f8 |
| payload SHA-256 | f8ea5d570c82016d2feb0bb571b289f4e7c7367d56f7d4c8e10a76b9631ed013 |
| 실제 송신 프롬프트 hash | 2fa239aed28238683d41bc1ea29505f4ad34e14e346add8573a02f0f4fb6567e |
| 공급자 request ID | 검사한 헤더에서 반환되지 않음; 내부 attempt ID로 대체 주장하지 않음 |
| usageMetadata | 미반환 |
| 이미지 / QA 실행 | 0장 / 0회 |
| 실패 후 상태 | needs_review, failure_n=1 |
| 응답 종료 후 기록된 냉각 | 약 16.274초; 냉각 종료가 추가 호출 승인이라는 뜻은 아님 |

아래는 **공급자 usageMetadata 원문이 아니라 원장의 누락 상태**다:

```json
{
  "usage_metadata_status": "absent",
  "usage_metadata": null
}
```

실응답에 해당 객체가 없었으므로 제공할 usageMetadata 원문은 없다.
빈 객체나 테스트 숫자를 원문처럼 작성하지 않았고 `usageMetadata.json`도 만들지 않았다.
이번 결과로 이미지 출력/입력/thinking 토큰 수, 장당 실측 비용, 8장·56장 예상 총액을 산출할 수 없다.

## 6. 비용/실패 과금 조사 보충

중앙 `PricingConfig.java`의 `$0.134`는 USD 이미지 출력 추정값이며 `₩0.134`가 아니다.
공식 1,120토큰 × $120/백만 토큰 산식은 $0.1344다. 입력·thinking은 별도다.
[Google 공식 가격표](https://ai.google.dev/gemini-api/docs/pricing#gemini-3-pro-image)

이번 원장은 승인 예산 전체 ₩1,600을 **단일 호출 예약 한도**로 점유했다.
`estimated_usd=1.142857…`, `reserved_amount_krw=1600`은 원장의 기존 예약 필드를 재사용한 할당량이지
Gemini 단가 또는 관측 청구액이 아니다. `reservation_basis=entire_authorized_budget_not_image_unit_price`로 명시했다.
503 뒤 `amount_krw=0`도 성공 추정액에서 제외됐다는 뜻이며 실제 청구액 0의 증거가 아니다.
새 비용 상수를 워커에 하드코딩하거나 남은 예산으로 두 번째 호출을 만들지 않았다.

Vertex AI 자료를 전용하지 않고 Developer API 공식 Billing FAQ를 별도로 확인했다.
FAQ는 **400 또는 500 오류로 실패하면 토큰 요금을 청구하지 않으며 quota에는 집계한다**고 안내한다.
[Gemini Developer API 실패 요청 과금 FAQ](https://ai.google.dev/gemini-api/docs/billing#am-i-charged-for-failed-requests)

이 안내는 실패 요청이 곧 과금이라는 주장에 반대되는 근거다. 다만 문구의 400/500이 모든 4xx/5xx를 포괄하는지와
실제 계정 청구 대조까지 이번에 확인한 것은 아니다. 기존 원장을 소급 무료로 확정하거나 예약을 자동 환급하지 않았다.
과거 scene21은 **명시적 503/504 44건 + 응답 미확정 reserved 1건 + 200 2건**이다.
reserved는 실패 응답 코드가 아니므로 45건 전체를 같은 비과금 근거로 묶으면 안 된다.

thought image가 비과금이라는 설명과 thinking 토큰 과금 설명도 구분한다.
이번 요청은 usageMetadata가 없어 텍스트/이미지/사고 사용량의 실제 세부 구성을 판별할 수 없다.
[Google 이미지 생성 가이드](https://ai.google.dev/gemini-api/docs/image-generation)

## 7. 다음 단계

1. 현재 실패 증거와 원장을 보존한다. 재시도 루프, 모델/티어 하향 전환, 새 경로로 카운터 초기화는 하지 않는다.
2. 추가 유료 호출은 별도 승인 후 진행한다. 승인 시 기존 실패 이력·공유 냉각·예산 노출을 어떻게 이어갈지 명시한다.
3. 성공 응답에서 사용량을 확보한 다음에만 토큰별 추정과 청구 대조, 추가 표본 예산을 논의한다.
4. 정지 이미지의 텍스트·화풍 품질 검증과 Fal 단계는 여전히 별도 승인/검증 대상이다.
5. Git `apple`/`assemble` 담당자 확인 대기와 백업 태그 보존 상태는 유지한다.

# WO-REQUEST-01 후속 검증 및 8장면 실행 전 점검

기준: 2026-08-26 작업 트리. 이 문서는 이전 구현 체크포인트에 대한 후속 검증이다.

2026-08-27 후속: [사용량 저장 패치·승인된 단일 호출 결과](GEMINI_USAGE_PILOT_RESULT_2026-08-27.md).
단일 실호출은 503으로 종료되어 아직 사용량 실측값은 없다. 아래 8장 비용 보류 판단은 해제되지 않았다.

추가 1회도 503으로 종료됐다: [재시도 결과](GEMINI_USAGE_RETRY2_RESULT_2026-08-27.md).
현재는 [WO-IMG-01 오프라인 준비 점검](WO_IMG_01_OFFLINE_READINESS_2026-08-27.md)으로 전환했다.
아래 4절의 usageMetadata 미저장 설명은 8월 26일 당시 상태다. 저장 패치는 이후 완료됐지만
입력/thinking 포함 전체 비용 예약·시각 계약 완료를 의미하지는 않는다.

## 1. 결과와 실행 범위

- `scene-021`은 기존 유닛테스트에 실제 포함되어 있었다. 해당 정규화/기존 원장 관련 테스트 8개를 다시 실행해 통과했다.
- 추가 조사에서 보조 파일럿의 `pilot:gemini-3-pro-image:scene_021` 형식이 정규화되지 않는 것을 발견해 보완했다.
- 참조 25개를 **운영 필수 8 / 도구 입력 3 / 재생성 입력 1 / 조건부 정리 후보 13**으로 분류했다.
- 25개 모두 기존 백업 매니페스트의 SHA-256과 같다. 참조 픽셀·프롬프트·선택 알고리즘은 바꾸지 않았다.
- 8장면 유료 실행은 **비용 사전 검증에서 보류**했다. 이번 작업의 GenerateContent POST는 0회다.
- 운영 워커 미배포, Job 52/54 미변경, TTS/Fal/영상 조립 미실행. Git 필터/강제 푸시/태그 삭제/브랜치 삭제 없음.

## 2. zero-padding: 존재 확인에서 원장 우회 검증까지

대상: `backend/fastapi-workers/app/utils/image_request_control.py::canonical_scene`.

기존 정규식이 `scene-021`을 캡처한 뒤 `int("021")`로 처리하여 `scene:21`로 합치는 것을 확인했다.
기존 테스트는 이 경우를 이미 포함했다. 다만 `scripts/run_scene_image_model_pilot.py`의 실제 키는
`pilot:{model}:scene_{index:03d}`여서 구분자 `_`가 기존 패턴에서 빠져 있었다.
이번 변경은 허용 구분자 `[:-]`를 `[:_-]`로 보완한 것이다. 모델/프롬프트 변경이 아니다.

추가 회귀 검증:

- 9개 별칭이 `scene:21`로 합쳐진다. `scene_021`, 모델 접두사 포함 파일럿 키, `image:00021:variation:1` 포함.
- 기존 47회 원장이 `image:21`/`scene-021`/파일럿 underscore 형식일 때 새 감사 객체의 반대쪽 별칭도 차단된다.
- 차단 후 원장 항목은 47개 그대로이며 새 예약/POST를 만들지 않는다.
- `forecast_021`, `scene_021_details`, `company:21`, `scene-21a`는 다른 이름 그대로 유지한다.
  임의 문자열 끝의 숫자까지 모두 합치지 않는다. 사용자 정의 scene ID 전체를 해석한다는 주장도 하지 않는다.

테스트: `tests/test_image_request_control.py`, `tests/test_reference_cleanup_audit.py`.
격리 사본: `/tmp/wo_request_verify.vm7YND/backend/fastapi-workers/` (Docker 내부).
운영 `/app/app`의 실행 소스는 교체하지 않았다.

검증 결과: 전체 **916 passed, 19 warnings, 88.51초**. 최종 집중 검증 **51 passed, 0.61초**.
경고는 기존 matplotlib/Pillow 사용 중단 예정 API 경고다.
전체 실행 도중 감사 스크립트의 증거 필드(백업 hash 대조)를 추가했으며, 이후 최종 집중 검증과
실제 읽기 전용 감사 CLI를 다시 실행했다. 해당 CLI 전체 경로를 전체 pytest가 검증했다고 주장하지 않는다.
요청 제어 소스는 전체 실행 중 바꾸지 않았다.

- [전체 JUnit](evidence/request_pilot_preflight_20260826/full-pytest.xml)
- [최종 집중 JUnit](evidence/request_pilot_preflight_20260826/focused-pytest.xml)
- [격리 사본과 작업 트리 17개 파일 SHA-256 일치](evidence/request_pilot_preflight_20260826/source-comparison.json)

```sh
docker exec -w /tmp/wo_request_verify.vm7YND/backend/fastapi-workers pipeline_fastapi \
  python -m pytest -q --junitxml=/tmp/wo_request_verify.vm7YND/pilot-preflight-full.xml
docker exec -w /tmp/wo_request_verify.vm7YND/backend/fastapi-workers pipeline_fastapi \
  python -m pytest -q tests/test_image_request_control.py tests/test_reference_cleanup_audit.py \
  --junitxml=/tmp/wo_request_verify.vm7YND/pilot-preflight.xml
```

## 3. 참조 25개: 운영 필수와 도구 의존성 분리

재현 명령(외부 API 호출 및 Git 변경 없음):

```sh
python3 backend/fastapi-workers/scripts/audit_reference_cleanup.py \
  --output docs/evidence/request_pilot_preflight_20260826
```

- [25개 전체 분류표](evidence/request_pilot_preflight_20260826/reference-assets.md)
- [파일별 hash·분류·근거 파일/행·조사 소스 hash](evidence/request_pilot_preflight_20260826/reference-assets.json)
- [운영 로더 필수 화이트리스트 8개](evidence/request_pilot_preflight_20260826/runtime-reference-whitelist.txt)
- [도구/재생성 입력까지 포함한 Git 보존 목록 12개](evidence/request_pilot_preflight_20260826/reference-preserve-whitelist.txt)

### 운영 필수 8개

`app/v5/providers/gemini_provider.py`의 `_FACE_RANGE_REF_NAME`와 `_SCENE_STYLE_REF_NAMES`를 AST로 읽어
실제 코드 상수와 대조했다. `_load_default_references()`는 8개 중 하나라도 없으면 실패한다.
문맥 선택으로 전송하지 않는 파일도 로더의 존재 조건에는 포함된다.

- 얼굴 범위 1개: `channel_character_face_range_v1.png`.
- Job52 화풍 5개: `channel_style_job52_{briefing,data_lab,market_flow,risk_map,semiconductor}.png`.
- 반도체 장면 2개: `channel_style_semiconductor_{growth,production}_scene_v1.png`.

V5 문맥별 경로는 얼굴 1개와 장면 화풍 2개를 선택한다. 이는 8개 모두를 매번 전송한다는 뜻이 아니다.
`data_lab`, `semiconductor` 원본 두 파일은 현재 문맥별 그룹에 직접 선택되지 않아도 로더 필수 항목이다.
직접 공급자 경로의 기본 참조 사용과 워커의 사용자 명시 캐릭터 병합도 존재하므로, 파일 선택 빈도만으로
운영 자산을 지우면 안 된다.

### 별도 도구 입력 3개

- `character_reference_v4_identity_clean.png`, `style_reference_v4_medium_clean.png`:
  `run_gemini_benchmark`, `run_v5_archetype_validation`, `run_v5_verified_pilot_backgrounds`,
  `generate_three_visual_type_samples`, `run_v5_four_scene_actual_pilot`, `run_visual_mix_nine_scene_pilot`가 직접 읽는다.
- `layout_reference_v2_textless.png`: `render_v5_strict_textless_review_sheet.py`가 검토 시트 입력으로 읽는다.

**보존은 기본 생성 경로에 다시 주입한다는 뜻이 아니다.** 거부된 이전 화풍을 재활성화하지 않았다.

### 재생성 입력 1개와 조건부 후보 13개

- `source_05s.png`는 구형 `build_v5_gemini_references.py`가 `frames[0]`으로 읽는 실제 픽셀 입력이므로 보존한다.
  해당 빌더는 외부 Windows 영상 경로도 요구한다. 이 컴퓨터에서 즉시 재생성 가능하다고 가정하지 않는다.
- `source_20s/35s/50s.png`는 같은 빌더가 만들고 목록에 담지만 이후 픽셀을 소비하지 않는 캐시/출력이다: 후보 3개.
- `character_reference_v2_textless.png`, `style_reference_v2_textless.png`: 구형 빌더 출력/역사 매니페스트: 후보 2개.
- `style_scene_ref_01~05` 5개: 등록 스크립트의 복사 출력과 v4 매니페스트 항목이다.
  매니페스트를 읽는 현재 보조 호출자는 `character`/`style` 두 경로만 검증해 전송한다.
  `scene_style_example` 항목이 존재한다는 사실만으로 실제 전송된다고 분류하지 않았다: 후보 5개.
- 버전 없는 `character_reference.png`, `style_reference.png`, `layout_reference.png`:
  조사한 현재 코드에 직접 파일 소비가 확인되지 않음: 후보 3개.

411개 소스/입력/매니페스트 파일을 조사했다. 파일명 검색은 읽기와 쓰기를 모두 잡으므로 소비 경로를 따로 읽었다.
f-string으로 만드는 `source_*` 경로도 별도 근거로 기록했다.

**한계:** API의 `character_image_path`, CLI의 명시 참조, 진행 중 요청/DB의 동적 경로 전체를 조회한 것은 아니다.
따라서 후보 13개를 “죽은 파일 확정” 또는 “즉시 삭제 승인”으로 바꾸지 않는다.
정리 시에는 이 13개만 동적 참조·백업을 최종 대조하면 된다. 25개 전체를 같은 이유로 보류하지 않는다.
기존 필터 파일은 역사 증거로 유지했고 그대로 실행하면 여전히 위험하다. 어떤 파일도 삭제하지 않았다.

## 4. ₩1,600 파일럿: 새로 발견한 비용 누락

기존 `PricingConfig.java::GEMINI_3_PRO_IMAGE_2K_USD=0.134`는 주석대로 **이미지 출력 단가**다.
현재 감사 객체는 호출자가 준 단가를 누적 예약하지만 입력·thinking을 자동으로 더하지 않는다.
`_generate_gemini_api()` 또한 `usageMetadata`를 원장에 보존하지 않으며 별도 출력 토큰 상한을 설정하지 않는다.
따라서 기존 체크포인트의 “보수적 예약 노출액”은 **주입 단가 범위의 보수성**이지 전체 공급자 청구 상한 보장이 아니다.

공식 Standard 가격은 입력 $2/백만 토큰, 텍스트·thinking 출력 $12/백만 토큰,
이미지 출력 $120/백만 토큰이다. 2K 출력은 1,120토큰, 참조 입력은 이미지당 560토큰으로 설명돼 있다.
[Google 공식 가격표](https://ai.google.dev/gemini-api/docs/pricing#gemini-3-pro-image)

thinking은 기본 활성화되고 API에서 비활성화할 수 없으며, 내용을 표시하지 않아도 과금 대상이다.
`responseModalities=["IMAGE"]`를 비용 0의 thinking으로 해석할 수 없다.
[Google 이미지 생성 가이드](https://ai.google.dev/gemini-api/docs/image-generation#thinking_process)

중앙 환산율 ₩1,400/USD와 장면당 참조 3개를 사용한 계산:

| 항목 | 8장 합계 |
|---|---:|
| 현재 중앙값 $0.134만 곱한 출력 추정 | ₩1,500.80 |
| 공식 토큰 산식 $120 × 1,120 / 1,000,000로 계산한 출력 | ₩1,505.28 |
| 참조 입력 3 × 560토큰 × 8장 | ₩37.632 |
| 승인 상한 ₩1,600에서 텍스트 입력·thinking 등에 남는 금액 | ₩57.088 |

기존 문서의 ₩1,504는 반올림한 장당 ₩188을 8번 곱한 근삿값이었다.
예를 들어 장당 thinking 500토큰을 **가정**하면 프롬프트 입력도 제외한 합계가 ₩1,610.112다.
500은 관측값이나 예상 평균이 아니라 작은 추가 사용량에도 상한을 넘길 수 있음을 보이는 민감도 예시다.
아직 프롬프트 토큰 수, thinking 실사용량, QA 비용, 공급자 청구액을 측정하지 않았다.
이 계산은 실패 재시도·세금·환전 수수료·Grounding도 포함하지 않는다.

결론은 “8장에 반드시 ₩1,600 이상 청구된다”가 아니라 **현재 계약/계측으로는 8장 총비용 상한을 검증할 수 없다**다.
승인된 WO 6절은 QA 등 부대 비용이 상한을 벗어날 때 축소 실행 승인을 받거나 진행하지 않도록 규정한다.
모델/품질/참조 장수를 낮추거나 몰래 Flex로 바꾸지 않았고 유료 호출 전에 멈췄다.

### 다음 실행 전 보완 및 사용자 선택

1. 가격 상수는 `PricingConfig.java`에서 입력·thinking·정확한 이미지 토큰 산식까지 관리하고 워커에 전달해야 한다.
2. 응답의 사용량을 allowlist로 기록하고, 사전 예약 추정과 사후 토큰 추정, 실제 청구 확인을 구분해야 한다.
3. 미확정/실패 요청의 비용 노출액을 유지해야 한다. 사후 누적 확인만으로 이미 발송한 요청의 초과를 막았다고 주장하지 않는다.
4. ₩1,600을 유지한 소수 장면 실측으로 바꿀지, 8장 유지에 맞춰 총예산을 다시 승인할지 사용자 선택이 필요하다.
5. 예산 선택 후에도 WO-IMG-01 정보성 표면 계약/가독성 검증은 요청 제어 테스트와 별개로 통과해야 한다.
   이번 결과로 오탈자·화풍 품질이 개선됐다고 선언하지 않는다. 정지 이미지 검토 후에만 Fal로 넘어간다.

## 5. Git과 변경 범위

`apple`/`assemble` 활성 여부와 담당자 확인은 아직 사람의 응답 대기다. 승인으로 간주하지 않았다.
원격 백업 태그를 제거하지 않았고 히스토리를 변경하지 않았다.
이번 추가 코드 변경은 장면 별칭 보완과 읽기 전용 자산 감사 스크립트/테스트다.
기존 미커밋 요청 제어 변경과 사용자 변경은 보존했다. .env/.env.example을 읽어 문서에 노출하거나 수정하지 않았다.

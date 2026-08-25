# 2026-08-26 미커밋 변경 상세 Summary / Description

## Commit Summary

```text
feat(pipeline): align narration timing and harden scene image quality gates
```

승인 대본을 TTS·자막·이미지 장면의 단일 원문으로 고정하고, 실제 음성 길이 보정·문장/자막 경계 결박·Job 52 기반 이미지 화풍 범위·장면 로컬 텍스트 계약·결정론 금융 수치·캐릭터 무결성·Fal 국소 동작 검증을 하나의 감사 가능한 파이프라인으로 연결한다. GUIDED 작업의 중복 외부 호출을 막고 Gemini 일시 장애를 재개 가능한 상태로 분류한다.

## Commit Description

### 1. 5분 요청의 실제 음성 시간 보정

- 동일 ElevenLabs `voice_id + model_id + speed` 조합의 첫 실측 샘플부터 CPM 보정값을 사용한다.
- 실측값에 속도를 두 번 곱하던 위험을 제거한다.
- 관측 CPM은 80~900 범위에서만 저장하고 이후에는 80% 기존값 + 20% 새 관측값 이동 평균을 사용한다.
- TTS 길이 허용치는 환경값이 넓더라도 운영상 1~5% 범위로 제한한다.
- 5분 요청이 3분대 음성으로 생성되면 실제 음성과 감사 자료는 보존하지만 이미지 생성으로 진행하지 않고 SCRIPT 분량 보정을 요구한다.
- 긴 ElevenLabs 요청은 짧은 연결 제한과 최대 240초 읽기 제한을 분리해, 정상 렌더링 중 60초 timeout으로 같은 유료 요청을 반복하는 문제를 줄인다.
- 프론트의 예상 글자 수 표시는 과거 650자/분 고정값 대신 현재 실측에 가까운 475자/분 안내로 바꾼다. 실제 생성 계약은 UI 상수가 아니라 백엔드 voice calibration을 사용한다.

주요 파일:

- `app/utils/script_length.py`
- `app/workers/tts_worker.py`
- `app/utils/output_qc.py`
- `frontend/src/pages/JobDetail.jsx`

### 2. 문장·자막·이미지 전환 경계 단일화

- 승인 대본 원문의 문자·숫자·순서를 바꾸지 않고 문장 중간에 걸린 scene 경계를 다음 완결문 경계로 이동한다.
- 장면 경계 보정 시 과거 prompt, subtitle, screen text, scene spec 등 파생 메타데이터를 무효화해 이전 의미가 남지 않게 한다.
- SCRIPT 예상 자막과 TTS 강제 정렬 자막이 동일한 `split_script_into_caption_chunks()`를 사용한다.
- 최대 자막 길이뿐 아니라 조사, 관형형 어미, 짧은 꼬리 청크를 고려해 한국어 의미 단위를 보존한다.
- 각 이미지 scene은 하나 이상의 완전한 자막 chunk만 소유할 수 있다.
- 한 자막 chunk가 두 이미지 scene에 걸리거나 scene 원문과 자막 원문 hash가 다르면 다음 비용 단계 전에 실패한다.
- 이미지 전환 시점은 마지막 소유 자막 chunk 뒤로 고정한다.

주요 파일:

- `app/utils/caption_segmentation.py`
- `app/utils/narration_contract.py`
- `app/workers/script_worker.py`
- `app/workers/tts_worker.py`
- `app/workers/longform_worker.py`

### 3. Job 52 장점을 보존하는 이미지 생성 계약

- 한 얼굴, 네이비 금융 진행자 의상, 스튜디오, 보드 구도를 전역 고정하지 않는다.
- Job 52의 실제 양호 장면에서 얼굴 표현 범위와 장면 스타일 참조를 추출한다.
- 장면 의미에 따라 `semiconductor`, `risk_weather`, `market_flow`, `briefing` 그룹에서 가까운 참조 2장을 선택하고 얼굴 범위 1장과 함께 최대 3장만 Gemini에 전달한다.
- 참조 이미지는 선화, 셀 셰이딩, 정보 밀도, 장면별 색 분위기, 자연스러운 물리 표면 처리의 허용 범위로 사용한다.
- 참조의 글자·숫자·말풍선·소품·구도를 복사하지 않도록 명시한다.
- 분리형 투명 유리 카드가 아니라 장면 속 모니터, 인쇄판, 기계 게이지, 소품 표면을 우선한다. 홀로그램은 scene surface plan이 명시할 때만 허용한다.
- 연속 장면에 같은 정보형 아키타입이 반복되는 것을 줄이고, 명시 layout lock이 없으면 자동 안전 영역이 모든 장면을 같은 배치로 만들지 못하게 한다.

주요 파일:

- `app/v5/providers/gemini_provider.py`
- `app/v5/scene/prompt_builder.py`
- `app/v5/scene/runtime_contract.py`
- `app/v5/scene/scene_type_archetypes.py`
- `app/utils/art_direction.py`
- `app/pipeline/scene_director.py`
- `app/workers/images_worker.py`
- `out/references/channel_character_face_range_v1.png`
- `out/references/channel_style_job52_*.png`
- `out/references/channel_style_semiconductor_*.png`

### 4. 무문자화가 아닌 장면 로컬 텍스트 정확성

- `scene.screen_texts`와 `scene.screen_text_plan`을 장면에서 허용된 문자열의 단일 원천으로 사용한다.
- 전역 `verified_facts`는 다른 장면의 사실까지 포함할 수 있으므로 화면 허용 목록으로 직접 사용하지 않는다.
- 승인된 회사명·지수명·용어·인용구는 Gemini가 자연스러운 장면 표면에 직접 쓸 수 있다.
- 지수값, 등락률, 금액, 배수 등 금융 수치는 base raster에 쓰게 하지 않고 Pillow/FFmpeg 결정론 표면 렌더러로 보낸다.
- 허용 목록 밖의 quoted text, label, display, exact value 지시를 Gemini 호출 전에 탐지·중립화한다.
- 화면 문구가 없는 장면만 `strict_textless`이며, 승인 비수치 문구는 `approved_generated_surface_text`, 금융 수치는 `deterministic_surface_text`로 분리한다.
- 동일 승인 라벨은 비교 장면의 서로 다른 실제 소품 두 곳까지 허용하고, 무분별한 도배만 막는다.
- 승인 문구 누락, 승인 수치 누락, 비승인·훼손 문자열, 무단 말풍선을 서로 다른 하드 실패로 남긴다.

주요 파일:

- `app/utils/image_text_contract.py`
- `app/utils/scene_screen_text_planner.py`
- `app/postprocess/text_overlay.py`
- `app/v5/overlay/diegetic_trend_overlay.py`
- `app/v5/overlay/in_scene_fact_templates.py`
- `app/workers/images_worker.py`

### 5. 오탈자·이탈자, 국소 수리, 최종 프레임 무결성

- 최종 래스터에 대해 Tesseract `kor+eng` OCR을 실행하되 2K 원본을 960px 폭으로 줄여 장면별 장시간 정지를 방지한다.
- 희소 문자 PSM 11과 문단 PSM 6이 같은 위치의 같은 숫자열에 동의해야 숫자로 확정한다.
- OCR뿐 아니라 Gemini 시각 QA의 `visible_texts`를 장면 허용 목록과 대조한다.
- Gemini 시각 QA 연결/429/5xx가 반복되면 10분 circuit을 열고 Claude `claude-sonnet-4-6` JSON 판독으로 보완한다.
- 생성된 이미지는 SHA-256과 QA 정책 버전이 일치할 때만 캐시를 재사용한다.
- 잘못된 문자 영역은 Gemini와 Claude의 좌표 합의를 이용해 국소 inpaint 가능성을 판단한다.
- 국소 수리 후보는 원본과 비교해 얼굴, 포즈, 카메라, 배경, 소품, 색감, 선화가 유지되고 수리 표면에 blur/smear/ghost가 없는지 별도 검수한다.
- 결정론 표면 문구는 승인 문자열 SHA-256과 렌더 직후 영역 픽셀 SHA-256을 남긴다.
- 최종 프레임에서 OCR이 한글을 오판하더라도 승인 문자열과 픽셀 provenance가 모두 일치할 때만 보완 통과한다.

주요 파일:

- `app/utils/visual_qa.py`
- `app/services/overlay/surface_detector.py`
- `app/services/local_text_repair.py`
- `app/services/final_frame_text_integrity.py`
- `app/services/fal_motion_safety.py`
- `app/workers/images_worker.py`

### 6. 캐릭터 범위와 명백한 해부학 오류 분리

- Job 52의 서로 다른 표정·눈 구조·의상·크기·배치를 승인 범위로 본다.
- 하나의 얼굴, 눈, 의상, 모자, 카메라 각도를 강제하지 않는다.
- 공통 계약은 round gold-coin family, embossed rim, 표현 가능한 얼굴, compact cartoon anatomy, 호환되는 굵은 선화다.
- `pointing + arms crossed`처럼 동시에 수행할 수 없는 팔 행동을 prompt-stage에서 정리한다.
- scene-specific costume이 있으면 일반 금융 진행자나 무관한 경찰 의상으로 치환하지 못하게 한다.
- 추가·중복·분리·융합된 손과 팔, 두 번째 금화 마스코트를 하드 실패로 분류한다.
- 말풍선은 scene별 `bubble_policy`가 `allowed/required`일 때만 허용한다.

주요 파일:

- `app/utils/character_integrity_contract.py`
- `app/utils/visual_qa.py`
- `app/workers/images_worker.py`

### 7. Fal/Kling은 텍스트가 아닌 국소 사물·배경·캐릭터에만 적용

- 정지 이미지 승인 전에 Fal을 호출하지 않는 motion preflight를 만든다.
- 반도체 장면은 웨이퍼 컨베이어/회로의 빛 흐름 하나, 하락 장면은 화살표 하나, 환율 장면은 게이지 바늘 하나, 발표 장면은 커튼/리본/상자 하나를 1차 대상으로 삼는다.
- 캐릭터는 얼굴 반응과 한쪽 팔의 작은 동작만 보조 대상으로 삼는다.
- 카메라, 전체 배경, 모든 글자·숫자·차트 표면, 얼굴 구조, 사지 개수를 고정한다.
- 텍스트·수치·차트·기사 캡처·정보형 scene은 Fal 후보에서 제외한다.
- 생성 클립의 변경 픽셀 비율, 활성 타일 비율, 테두리 변경 비율을 검사해 전 화면 지글링, 카메라 흔들림, 배경 전체 왜곡을 차단한다.
- Fal 최종 프레임에도 결정론 문구 hash 검증을 적용한다.

주요 파일:

- `app/services/fal_motion_intent.py`
- `app/services/fal_motion_safety.py`
- `app/services/motion_locality.py`
- `app/services/final_frame_text_integrity.py`
- `app/utils/intro_motion.py`
- `app/workers/images_worker.py`
- `app/workers/longform_worker.py`

### 8. Gemini 비용·재시도·중단 처리

- Gemini Pro 2K 외에 명시적 파일럿용 Gemini 3.1 Flash 2K 요청도 비용 원장에서 별도 종류로 기록한다.
- Gemini의 실제 응답에는 청구액이 없으므로 환경에 설정된 예상 단가를 사용하고 콘솔 대조 전에는 `unverified` 상태를 유지한다.
- Pro 2K 요청의 연결 timeout과 읽기 timeout을 분리하고 `X-Server-Timeout`을 설정한다.
- `serviceTier`를 `generationConfig` 내부가 아니라 요청 최상위에 둔다.
- `.env.example`의 운영 기본을 concurrency 1, RPM soft cap 6, 동일 일시 오류 1회 circuit-open으로 낮춰 503 시 장면 전체가 연쇄 요청되는 것을 막는다.
- 동일 오류 circuit breaker가 열리면 다음 scene을 시작하지 않는다.
- HTTP 503/504/네트워크 오류를 credit 부족과 분리해 `IMAGE_PROVIDER_TEMPORARILY_UNAVAILABLE`로 반환한다.
- 이미 생성된 scene 파일은 보존하고 이미지 단계만 재개할 수 있게 한다.
- Spring은 provider 일시 장애 시 Job을 `IMAGES_PENDING`으로 돌리고 사용자에게 재시도 가능한 안내를 준다.
- 중복 이미지 생성 요청은 Redis 잠금 충돌을 작업 실패로 바꾸지 않고 `ALREADY_RUNNING`으로 처리한다.

주요 파일:

- `.env.example`
- `docker-compose.yml`
- `app/config.py`
- `app/runtime_config.py`
- `app/providers/real/image.py`
- `app/utils/budget.py`
- `app/main.py`
- `app/workers/images_worker.py`
- `PricingConfig.java`
- `GlobalExceptionHandler.java`
- `ImagesService.java`

### 9. GUIDED 워크플로 중복 과금 방지와 수동 게이트

- GUIDED/MANUAL에서 스크립트, TTS, 이미지, 조립을 Temporal과 UI가 동시에 호출하지 않게 한다.
- AUTO만 workflow activity가 생성 단계를 자동 실행한다.
- GUIDED/MANUAL은 UI/API의 명시 실행 후 해당 승인 gate를 기다린다.
- 기존 Temporal history와 비결정성 충돌을 피하려고 version marker를 사용한다.
- 정지 이미지 승인 전에 Fal/Kling, MP4 조립, 썸네일로 자동 진행하지 않는다.
- 기존 실제 Claude 의미 검토와 기사/사실 계보를 보존한 채 최신 결정론 문장·리듬 계약만 다시 검사하는 SCRIPT 재검증 API와 UI 버튼을 추가한다.
- Spring SCRIPT asset 보존 필드에 fact check log/round, news lineage, quality report, narration contract, market snapshot, LLM provider log 등을 추가한다.

주요 파일:

- `VideoPipelineWorkflowImpl.java`
- `ScriptService.java`
- `FastApiClient.java`
- `ScriptController.java`
- `ScriptGenerateResponse.java`
- `LongformService.java`
- `LongformController.java`
- `frontend/src/api/jobs.js`
- `frontend/src/pages/JobDetail.jsx`

### 10. 테스트 변경

- 수정된 FastAPI 테스트 파일: 41개
- 새 FastAPI 테스트 파일: 10개
- Spring 테스트 보강: 이미지 자동 게이트, 스크립트 증거 계보 보존
- 주요 신규 회귀 범위:
  - 자막/scene 원문 경계
  - TTS 실측 1회 보정과 5% 길이 하드 게이트
  - 비승인 텍스트, 승인 텍스트, 금융 수치 분리
  - 캐릭터 포즈 충돌과 말풍선 정책
  - OCR 숫자 이중 확인
  - 국소 문자 수리 보존
  - 최종 프레임 결정론 텍스트 provenance
  - Fal 국소 동작과 전 화면 지글링 차단
  - Gemini QA 전송 장애 fallback/circuit
  - 동일 일시 오류 circuit breaker와 다음 scene 미시작
  - GUIDED 이미지 중복 실행 방지

### 11. 감사·파일럿 산출물

미추적 산출물은 코드 변경의 원인과 결과를 재현할 수 있는 증거다. 총 305개 파일, 약 714MB이며 단일 파일 최대 크기는 약 14.9MiB다.

| 디렉터리 | 크기 | 파일 수 | 내용 |
|---|---:|---:|---|
| `artifacts/example_frames` | 16MB | 7 | 장면/표면 예시 프레임 |
| `artifacts/job52_direction_recovery_20260823` | 61MB | 29 | Job 52 방향 복구 참조·비교 결과 |
| `artifacts/job52_full_audit_20260824` | 158MB | 81 | 실제 프롬프트, 장면 계약, 생성/수리 파일럿 |
| `artifacts/job52_image_audit` | 4.5MB | 4 | 사용자가 지정한 00~47 접촉시트와 scene 048 |
| `artifacts/job52_process_regeneration_20260823` | 184KB | 2 | 과정 재생성 감사 |
| `artifacts/job52_quality_one_minute_e2e` | 131MB | 48 | 1분 E2E 이미지·진단·57초 영상 |
| `artifacts/job52_quality_one_minute_e2e_qc2` | 900KB | 8 | 2차 QC 결과 |
| `artifacts/job53_five_minute_successor_20260825` | 432KB | 5 | Job 53 후속 5분 계획·실패 증거 |
| `artifacts/job54_live_audit` | 273MB | 84 | Job 54 부분 생성·거절·재생성·표면 수리 감사 |
| `artifacts/job54_progress_contact_sheets_20260826` | 1.6MB | 3 | Job 54 현재 00~47 진행 접촉시트 |
| `artifacts/job54_scene01_flash_pilot` | 15MB | 5 | scene 01 Flash/결정론 수리 비교 파일럿 |

### 12. Job 52/54 포렌식 문서

- `docs/DEVELOPER_JOB52_IMAGE_FORENSICS_AND_JOB54_STATUS_2026-08-26.md`
  - Job 52 실제 commit·코드 분기·Claude 프롬프트 생성 규칙·Gemini payload·참조 3장·비용·후처리
  - 실제 scene 00~47 prompt corpus 경로
  - scene별 문제 유형과 prompt-stage/renderer-stage 원인
  - Job 54가 실제 실행 중이 아닌 `IMAGES_PENDING` 정체 상태인 이유
  - Job 54 Gemini 요청 126건과 상태별 비용 원장 분석
  - 현재 텍스트/수치 정책과 Fal 적용 가능 범위

## 변경 규모

- 기존 추적 파일 수정: 76개
- 추적 코드 diff: +6,414 / -1,002 lines
- 미추적 파일: 305개
- 미추적 파일 크기: 약 714MB
- 비밀값 패턴 검사: Google/Anthropic/OpenAI/GitHub 키, private key, 장문 bearer token 0건
- `.env.example`: 실제 비밀값 없이 재시도·timeout·비용 placeholder만 변경

## 검증 결과

- FastAPI 전체 테스트: `830 passed`, 경고 19건, 실패 0건
- 관련 핵심 회귀 테스트 재실행: `102 passed`
- Spring Gradle 테스트: `BUILD SUCCESSFUL`, 4 tasks executed
- Frontend Vite production build: 성공, 1,708 modules transformed
- `git diff --check`: 통과
- 최종 스테이징 382개 경로 비밀값 패턴 검사: 의심 항목 0건
- Frontend 의존성 설치 시 기존 의존성 트리에서 moderate 4건, high 2건의 `npm audit` 경고가 보고됐다. 이번 작업에서는 자동 breaking upgrade를 실행하지 않았다.
- Vite가 minified JavaScript chunk 527.82kB에 대해 500kB 초과 경고를 냈지만 빌드는 성공했다.

## 알려진 미완료 사항

- Job 54는 scene 00~25 파일만 존재하고 전체 56 scene 생성은 완료되지 않았다.
- Job 54의 현재 00~25는 과거·신규 계약과 수동 파일럿이 섞여 있어 최신 계약의 일관된 결과로 승인할 수 없다.
- Job 54에서 Fal은 실제 호출되지 않았으며 motion preflight만 존재한다.
- OCR은 작은 한국어를 놓칠 수 있으므로 멀티모달 QA가 unavailable이면 해당 scene을 자동 승인하지 않는다.
- Gemini 원장 금액은 설정 단가 기반 예상치이며 최종 콘솔 청구와 별도 대조가 필요하다.

# V5 실전 투입 킥오프: A/B/C 현황과 무료 검증

작성일: 2026-07-31

이 문서는 이미지·LLM·모션 API를 호출하지 않고 작성했다. 실제 이미지 생성, 모션 코드 변경, 40씬 렌더링은 별도 승인 대상이다.

## A. ScriptWorker → ImagesWorker V5 통합

### 적용한 연결

| 구간 | 파일 | 동작 |
|---|---|---|
| 씬 분류 | `backend/fastapi-workers/app/workers/script_worker.py` | 기존 `scene_type`과 `selection_reason`을 생성한다. |
| V5 운영 계약 | `backend/fastapi-workers/app/v5/scene/runtime_contract.py` | `scene_type`을 archetype, primary 표면, V5 프롬프트, Gemini tier, 오버레이 모드로 변환한다. |
| 운영 이미지 워커 | `backend/fastapi-workers/app/workers/images_worker.py` | 모든 씬에 `scene_type`이 있으면 V5 운영 계약을 붙이고, 직렬·병렬 프롬프트 경로에서 V5 프롬프트와 Gemini Pro 2K·`max_attempts=1`을 강제한다. V5는 기존 Batch/자동 변주/포즈 합성 경로를 우회한다. |
| 사실 합성 | `backend/fastapi-workers/app/v5/overlay/diegetic_fact_overlay.py` | 생성 후에만 `v5_verified_overlays`를 검증하고 Pillow로 합성한다. 값·출처·좌표가 없으면 합성하지 않는다. |

### 운영 규칙

| scene_type | 배경 모델/프롬프트 | 사실 수치 |
|---|---|---|
| `general` | Gemini Pro / `body`, 캐릭터 중심 V5 무대, `strict_textless` | 적용하지 않음 |
| `metric`, `graph`, `diagram`, `text` | Gemini Pro / `hero`, 추천 archetype의 primary 표면 계약, 장식 영문만 허용 | `verified_facts`와 `v5_verified_overlays`가 모두 있을 때만 생성 후 Pillow 합성 |

`klein`은 이 운영 계약에 선택되지 않는다. V5 router의 draft tier 예비 경로로만 남아 있다. V5 계약이 붙은 씬은 전역 `IMAGE_PROVIDER` 값과 무관하게 Gemini Pro 2K로 요청되고, 외부·내부 자동 재시도 모두 1회로 제한된다. `earnings_stage`는 `TYPE_CANDIDATES`에 없고 `RENDER_BLOCKED_ARCHETYPES`에도 남아 있어 자동 추천·실제 렌더가 모두 차단된다.

### 무료 드라이런 결과

입력: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/v5_pilot_input.json`

출력: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/images_worker_v5_dry_run.json`

| 씬 | 분류 | 선택 archetype | tier | 검증 오버레이 입력 |
|---|---|---|---|---|
| `kospi_july_01` | `graph` | `data_lab` | hero | 있음 |
| `kospi_july_02` | `graph` | `trade_calculator` | hero | 있음 |
| `kospi_july_03` | `metric` | `risk_control_room` | hero | 있음 |

드라이런은 ScriptWorker의 `_classify_scene_types()`와 ImagesWorker가 호출하는 동일한 `attach_v5_scene_contracts()`를 사용했다. API 요청 수는 0이다. 각 씬의 출력에는 primary 좌표와 최종 영문 프롬프트도 저장된다.

### 테스트

- 신규 운영 계약 및 기존 V5 테스트: `66 passed`
- Python 문법 검사: 통과
- 테스트 명령: `python -m pytest <tests/test_v5_*.py 전체 목록> -q`

## B. 현재 모션 구현과 레퍼런스 차이

### 현재 구현 사실

1. `LongformWorker`는 FAL 크레딧이 있고 `INTRO_MOTION_ENABLED=true`일 때만 영상 생성기를 사용한다.
2. 호출 모델은 FAL의 `fal-ai/kling-video/v2.6/pro/image-to-video`이다. Longform 경로는 `fal_only=True`를 넘기므로 FAL 실패 시 공식 Kling API로 넘어가지 않고 정적 FFmpeg 페이드로 폴백한다.
3. 동적 클립은 오프닝의 연속 구간만 선택한다. 기본값은 영상 길이가 660초 이하이면 앞 40초, 그보다 길면 앞 60초이며, 클립은 5초, 최대 12개다. 90초 이하 영상은 최대 4개로 추가 제한된다.
4. 이후 씬은 `_ffmpeg_static_image()`로 정지 화면이며, 팬·줌·Ken Burns는 없다. 영상 생성 실패 시도 0.5초 페이드가 있는 정지 클립으로 바뀐다.
5. 실제 FAL 프롬프트는 `app/services/kling_prompt_builder.py`의 `motion_type` 5종(`chart_shock`, `pointing_explain`, `thinking_desk`, `walking_intro`, `celebration`)이다. 모두 카메라 고정과 배경 정지를 요구한다.

### 지글링으로 보이는 원인

- 현재 설계는 카메라 지글링이 아니라, 5초 동안의 캐릭터 미세 동작(점프, 고개 기울임, 포인터 움직임, 눈 깜빡임)만 생성한다.
- 매 씬 끝에는 정지 프레임을 늘려 붙인다. 즉 한 장면 안에서 `짧은 AI 움직임 → 고정`이 생기며, 서로 다른 이미지 씬이 이어질 때는 컷 변화가 크다.
- `LongformWorker` 안의 `_build_kling_motion_prompt()`는 이름이 유사하지만 실제 호출되는 함수가 아니다. 실제 경로는 위 서비스의 `build_kling_motion_prompt(scene["motion_type"])`다. 향후 수정 때 두 경로를 혼동하면 안 된다.

### 0~8초 레퍼런스 관찰

대상: `C:/Users/song/Downloads/영상 참고 이미지/KakaoTalk_20260722_021311238.mp4`

- 0~약 3초: 절벽 장면에서 마스코트 팔·다리·표정과 밧줄이 변화한다. 카메라 프레이밍은 거의 고정이다.
- 약 3초: 무대 장면으로 명확한 컷 전환.
- 3~약 6초: 점프·착지, 캔들/스포트라이트 발광, 파티클 변화가 결합된다.
- 약 6초: 산길 장면으로 또 한 번 컷 전환.

따라서 사용자가 측정한 중간 프레임 변화(10~27)는 지속적인 카메라 이동보다 캐릭터·소품·광원·파티클의 조합 움직임에 가깝고, 60~110의 변화는 컷 전환과 일치한다. 레퍼런스의 핵심은 무작위 흔들림이 아니라 **장면별 한 가지 읽히는 행동 + 광원/소품 반응 + 짧은 리듬의 컷**이다.

### 다음 개선안 (실행 전 검토용)

1. 카메라 팬·줌을 먼저 추가하지 않는다. 숫자/오버레이 정합성이 깨질 위험이 있다.
2. `motion_type`을 현재의 템플릿 선택만으로 두지 말고, scene_type과 archetype별로 `행동 1개 + 반응 소품 1개 + 광원/파티클 1개`로 명시한다.
3. 사실 오버레이가 있는 `metric/graph/diagram` 씬은 배경·캐릭터만 움직이고, Pillow 사실 텍스트/그래프는 이미지와 함께 움직이는 단일 평면으로 유지한다.
4. 정적 body 씬에는 비용 없는 FFmpeg 전환 리듬(짧은 컷, 일부 reveal)부터 설계하고, 카메라 이동은 별도 안전 검증 후에만 검토한다.

코드·모션 API 호출은 이 문서 단계에서 수행하지 않았다.

## C. 40씬 파일럿 준비 상태

| 진입 조건 | 현재 상태 | 판단 |
|---|---|---|
| 실제 검증 대본 | 코스피 7월 전망 3씬 대본과 출처 사실은 있음 | 40씬짜리 실제 검증 대본은 없음 |
| `v5_verified_overlays` | 3씬 모두 출처 참조·값·anchor가 채워져 있음 | 40씬분은 아직 없음 |
| Gemini 비용 산정 | 승인 단가 `$0.14`와 최근 V5 원장 환율 스냅샷 `₩1,815/$` 사용 가능 | 40씬 실행 전 새 환율/콘솔 기준 재확인 필요 |
| 콘솔 대조 | 3씬 파일럿에서 수행한 이력 있음 | 새 파일럿은 새 요청 묶음 단위로 다시 대조 필요 |

### 개산 견적

- 40씬 본 요청: `40 × $0.14 = $5.60`, 최근 스냅샷 기준 약 `₩10,164`
- 수동 재시도 1회 예비: `$0.14`, 약 `₩254`
- 이미지 합계 사전 예약 제안: **약 ₩10,418**, 변동을 고려한 승인 상한은 **₩12,000**

V5 `CostLedger`의 현재 `IMAGE_FINAL` bucket 상한은 `₩7,000`이다. 총 영상 상한 `₩40,000`에는 들어가지만 40씬 이미지 파일럿을 한 묶음으로 수행하면 bucket이 먼저 차단한다. 실제 실행 전에는 `PricingConfig.java`를 기준으로 승인된 상한을 중앙 설정에 반영하거나, 3씬 첫 묶음 → 콘솔 대조 → 승인된 후속 묶음으로 나누는 방식 중 하나가 필요하다.

### 권장 실행 순서 (아직 실행하지 않음)

1. A의 무료 드라이런 결과를 승인한다.
2. 실제 40씬 대본과 씬별 `verified_facts`/`v5_verified_overlays`를 준비한다.
3. 첫 3씬만 Gemini Pro로 생성하고 사람 시각 검토와 콘솔 대조를 즉시 실시한다.
4. 재확인한 비용 버킷과 총 ₩40,000 상한 안에서 후속 묶음을 승인한다.

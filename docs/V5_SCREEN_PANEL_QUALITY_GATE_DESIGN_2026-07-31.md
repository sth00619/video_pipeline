# V5 화면형 보조 소품 QualityGate 설계·검증 기록

작성일: 2026-07-31  
상태: 구현 및 로직 검증 완료 / `earnings_stage` 재생성은 별도 승인 전까지 금지

## 1. 전환 배경

`earnings_stage`는 서로 다른 세 번의 프롬프트 계약을 적용했는데도, 중앙 실적 브리핑 표면 밖의 양옆 벽에 청록색 사각 발광 패널이 반복 생성됐다. 이는 `earnings stage`라는 무대 개념과 보조 스크린이 강하게 결합된 모델 경향으로 판단한다.

따라서 네 번째 프롬프트 보정이나 자동 재생성을 하지 않는다. 대신 생성 결과에서 primary 물리 표면 밖의 화면형 보조 소품을 감지하면 **자동 실패**로 기록하고, 다음 생성은 반드시 사람이 판단하도록 바꾼다.

## 2. 범위와 비범위

### 이 게이트가 하는 일

- primary 표면 좌표를 제외한 영역에서 사각형 경계와 고채도 발광 내부를 가진 화면형 후보를 찾는다.
- 후보가 하나라도 있으면 `primary 외 화면형 보조 소품 감지` 실패를 추가한다.
- 라우터가 `manual_review_required`를 반환하고, `HumanRegenerationDecisionRequired` 예외로 호출자에게 사람 결정을 요구한다.
- 해당 경로에서는 비용이 발생하는 재생성을 절대 자동 호출하지 않는다.

### 이 게이트가 하지 않는 일

- OCR, 로고·한글·워터마크 인식 또는 실제 금융 수치 검증
- 장식 영문·숫자가 사실인지 판정
- 모든 종류의 직사각형 물체를 화면으로 단정
- `earnings_stage`를 새로 생성하거나, 통과 확정 11개 archetype을 다시 생성

검증 금융 수치·등락률·출처는 계속 Pillow/FFmpeg 결정론적 오버레이의 책임이다. AI의 영문·표본 수치는 장면 질감 검증용 장식으로만 취급한다.

## 3. primary 좌표 계약

파일: `backend/fastapi-workers/app/v5/scene/scene_type_archetypes.py`

`PRIMARY_SURFACE_REGIONS`는 각 archetype의 실제 물리 primary 표면을 `(x, y, width, height)`의 0~1 정규화 프레임 좌표로 정의한다. 이 좌표는 후처리용 `LayoutPlan.fact_overlay` 안전영역과 다르며, 혼용하지 않는다.

`primary_surface_region()`은 다음을 보장한다.

- 모든 `ARCHETYPE_SURFACES` 항목에 좌표가 존재한다.
- 좌표가 프레임 밖으로 나가지 않는다.
- 누락 또는 범위 오류는 테스트·실행 시 즉시 실패한다.

이 좌표는 임의의 빈 카드 위치가 아니라, 이미 primary-surface 검증으로 확정한 실제 무대 안 표면의 검사 제외 영역이다.

## 4. 탐지 규칙

파일: `backend/fastapi-workers/app/v5/scene/quality_gate.py`

1. 입력을 최대 장변 384px로 축소한다.
2. 여러 사각 창 비율을 훑되, primary와 55% 이상 겹치는 창은 제외한다.
3. 너무 작은 후보(프레임 면적 3% 미만)는 제외한다.
4. 내부가 지나치게 복잡하지 않고, 청록/청색 또는 강한 적색의 고채도 발광 비율이 충분한 후보만 남긴다.
5. 사각 경계 대비를 확인한다. 좌·우 벽에 붙은 세로 발광 패널은 프레임 가장자리 특성상 네 변 중 일부가 약할 수 있어, 높은 발광 일관성과 세로 비율을 동시에 만족할 때만 예외적으로 허용한다.
6. 겹치는 후보를 합쳐 최대 6개만 결과에 보존한다.

이 규칙은 일반 액자·종이 안내물·금색 조명·마스코트 윤곽을 화면으로 오인하지 않도록 보수적으로 조정됐다. 반대로 이것은 객체 인식 모델이 아니므로, 감지 결과는 재생성 지시가 아니라 사람 검토 신호다.

## 5. 자동 처리 계약

```text
이미지 생성 1회
  → QualityGate.score()
  → primary 밖 화면형 후보 존재
      → 실패 상태 저장
      → manual_review_required
      → 자동 재시도 금지
      → 사람의 재생성/폐기/예외 허용 결정 대기
```

기존 빈 배경·소품 밀도 부족 등 일반 실패의 최대 1회 재시도 정책과 이 정책을 혼동하지 않는다. 화면형 보조 소품은 비용·품질 모두에 직접 연결되는 구조적 실패이므로, 최초 감지부터 사람 승인이 필수다.

## 6. 검증 증거

### 단위·통합 테스트

다음 파일을 실행했다.

```powershell
$env:PYTHONPATH='backend/fastapi-workers'
python -m pytest `
  backend/fastapi-workers/tests/test_v5_quality_gate.py `
  backend/fastapi-workers/tests/test_v5_scene_type_archetypes.py `
  backend/fastapi-workers/tests/test_v5_provider_router.py -q
```

결과: **16 passed**

추가 검증 항목:

- primary 밖의 청록 발광 패널은 `manual_review_required`가 된다.
- primary 안의 발광 정보 표면은 후보에서 제외된다.
- 화면형 소품 감지 시 `render_checked()`가 두 번째 API 호출을 하지 않는다.
- 모든 archetype의 primary 좌표 계약이 유효하다.

### 기존 실제 파일 리플레이

이미 존재하는 파일만 읽어 검사했다. 이미지 API 호출은 없었다.

| 파일 | 기대 판정 | 실제 판정 |
|---|---|---|
| `backend/fastapi-workers/out/v5_archetype_validation/earnings_stage_screenless_v3_manual_retry_01/earnings_stage_primary_validation.png` | 양옆 청록 발광 패널 감지 | 실패 / `manual_review_required` / 좌측 보조 패널 후보 1개 |
| `backend/fastapi-workers/out/v5_archetype_validation/job_market_hall_screenless_v3_manual_retry_01/job_market_hall_primary_validation.png` | 동결된 통과 이미지에 오탐 없음 | 통과 / 후보 0개 |

## 7. 운영 결정

- Gemini Pro final lane: `ImageProviderRouter`의 기본 `final_lane_approved=True`로 전환했다. P1 벤치마크에서 Gemini Pro가 우위였고, 11개 archetype의 primary-surface 검증이 통과한 상태를 반영한다.
- `earnings_stage`: **미검증 유지**. `RENDER_BLOCKED_ARCHETYPES`에 등록하여 QualityGate가 준비됐더라도 사람의 별도 승인 전에는 생성 API 호출 자체를 차단한다.
- 통과 확정 11개 archetype: 규칙 동결을 유지한다. 이번 게이트 검증을 이유로 재생성하지 않는다.
- 향후 `earnings_stage` 이미지가 필요할 때: 한 장을 비용 승인 후 생성하고, QualityGate 결과·후보 좌표·사람 육안 판정을 함께 제출한다. 실패 시 자동 재시도하지 않는다.
- 같은 유형의 새 archetype도 primary 좌표 계약을 먼저 등록한 뒤 이 게이트를 적용한다.

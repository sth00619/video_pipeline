# WO-IMG-03 모듈 B+D — 공통 이미지 체크리스트와 분리 정확도 집계

## 1. 결론

RESEARCH-03의 모듈 B와 D는 일부 기반 코드가 이미 있었지만 다음 두 공백 때문에 완료 상태가 아니었다.

1. 공통 Visual QA의 전체 항목 정확도와 장면 완전정확도는 있었지만, 각 항목별 통과·실패·보류 `N/M`이 없었다.
2. scene00·07·15·28 유료 canary 실행기는 사용자 육안 보류와 정확도 집계를 manifest에 연결하지 않았다.

이번 구현은 기존 `scene_accuracy_metrics.py`, `canary_visual_review.py`, `visual_judgment_disagreement_log.py`를 폐기하거나 복제하지 않는다. 신규 공통 어댑터로 이들을 연결하고 기존 집계를 확장했다. 유료 이미지 호출은 하지 않았다.

## 2. 선행 실패와 구현 계보

- 선행 실패 테스트 커밋: `f0ae116`
  - 결과: `ModuleNotFoundError: app.utils.visual_quality_checklist`
  - 의미: 공통 체크리스트 모듈과 항목별 집계가 실제로 없음을 고정했다.
- 최소 구현 커밋: `6c502a2`
  - 집중 회귀: `47 passed`
  - 전체 회귀: `1200 passed, 0 failed, 22 warnings`

경고는 기존 Pillow·matplotlib deprecation과 읽기 전용 검증 환경의 pytest cache 경고이며 이번 품질 계약 실패가 아니다.

## 3. 모듈 B — `visual_quality_checklist`

신규 `app/utils/visual_quality_checklist.py`는 다음 항목을 모든 장면에서 같은 순서로 유지한다.

1. `text_integrity`
2. `deterministic_numeric_integrity`
3. `physical_text_surface`
4. `scene_meaning`
5. `character_anatomy_and_face`
6. `style_fidelity`
7. `composition_and_density`
8. `unexpected_visual_anomaly`
9. `unlisted_failure_scan`

상태는 `pass`, `fail`, `pending`, `not_applicable`만 허용한다. 자동 판정이나 사용자 판정이 없는 항목은 `pending`이며 통과로 승격되지 않는다. 미판정 항목이 하나라도 있으면 `approval_blocked=true`다.

이는 특정 Job52 장면용 분기가 아니다. 공통 Visual QA와 실 이미지 canary가 공유하는 품질 항목 어휘다.

## 4. 모듈 D — 항목 정확도와 완전승인율 분리

`aggregate_scene_accuracy()`에 `per_item` 집계를 추가했다. 각 항목은 다음 값을 독립적으로 남긴다.

- `evaluated_count`
- `passed_count`
- `failed_count`
- `pending_count`
- `not_applicable_count`
- `accuracy`

동시에 기존 배치 전체 `item_accuracy`와 `fully_accurate_scene_rate`를 유지한다. 예를 들어 텍스트가 통과하고 물리 표면이 실패하면 항목 정확도는 1/2이지만 장면 완전승인은 0이다. 앞으로 “텍스트 4/4”만 강조하고 “표면 0/4”를 축소하는 보고 구조를 만들 수 없다.

## 5. 운영·canary 연결

공통 `visual_qa.py`는 이미 `aggregate_scene_accuracy()`를 사용하므로 이번 `per_item` 확장이 영상 생성 버튼이 타는 운영 Visual QA 결과에 그대로 반영된다.

`run_wo_img02a_before_after_canary.py`에도 다음을 추가했다.

- base raster 문자 게이트와 결정론 표면 게이트를 서로 다른 체크리스트 항목으로 기록
- 실물 이미지가 생성되면 사용자 육안 검토 packet 생성
- 사용자 확인 전 의미·얼굴·화풍·구성·예상 밖 이상 항목은 `pending`
- manifest에 `accuracy_metrics`를 항상 기록
- 공급자 503으로 이미지가 없으면 모든 시각 항목을 `pending`으로 유지하고 완전승인율은 0

따라서 HTTP 200, 자동 게이트, 사용자 육안 승인, 장면 완전정확도는 서로 대체되지 않는다.

## 6. 현재 범위와 다음 실증

오늘 scene00 유료 재시도는 중단했다. Flash 우회도 하지 않았다. 다음 Pro Priority 성공 응답부터 새 manifest에는 체크리스트, 항목별 정확도, 완전승인율, 사용자 육안 보류가 함께 생성된다.

이번 구현은 TTS, Fal, 영상 조립, scene42를 변경하지 않았다. 모델 정책도 `gemini-3-pro-image + Priority` 그대로다.


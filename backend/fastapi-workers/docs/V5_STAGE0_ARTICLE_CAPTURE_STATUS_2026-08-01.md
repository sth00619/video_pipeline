# V5 유형 3 기사 캡처형 — 현황 조사

작성일: 2026-08-01  
범위: 코드·테스트·현재 작업 환경 조사만 수행했다. URL 캡처, 브라우저 설치, 이미지 API 호출, 기능 코드는 실행·변경하지 않았다.

## 결론

기사 캡처형은 처음부터 새로 만드는 기능이 아니다. 공개 기사 URL의 DOM에서 **검증된 원문 인용구의 실제 좌표를 얻어 캡처하고**, Pillow로 밑줄·형광펜·동그라미를 결정론적으로 합성하는 기반이 이미 있다. 또한 `ImagesWorker`와 `LongformWorker`는 기사 증거 씬을 Gemini/FAL 생성 경로에서 제외한다.

다만 현재 로컬 실행 환경에는 Playwright 패키지가 설치되어 있지 않아 실제 브라우저 캡처를 수행할 수 없다. 그리고 사용자가 제공하는 뉴스/증권 **캡처 이미지 파일 자체를 입력으로 받는 전용 API·어댑터는 아직 없다.** 즉 URL→DOM 캡처형은 구현되어 있으나 런타임 미준비, 이미지 파일→강조형은 별도 구현이 필요하다.

## 1. 기존 구성요소

| 기능 | 파일·핵심 요소 | 입력 → 출력 | 다음 단계 전달 |
|---|---|---|---|
| 공개 기사 DOM 캡처 | `app/services/evidence_capture.py` / `EvidenceCaptureService.capture_dom()` | `EvidenceCaptureRequest`(공개 URL, 원문 인용구, 선택 키 구절) → 인용구 주변 PNG와 정규화 좌표 | `DATA_DIR/jobs/{job_id}/evidence/article_<hash>.png` 및 동명 JSON으로 저장. `ArticleCapture.local_path`에 기록 |
| 좌표 계약 | `app/models/article_evidence.py` / `ArticleCapture`, `NormalizedBBox`, `EvidenceAnnotation` | DOM Range 또는 검토된 좌표 → 0~1 정규화 bounding box | 씬의 `article_capture`, `annotations` 메타데이터로 전달 |
| 결정론적 강조 | `app/services/annotate.py` / `render_annotations()` | 캔버스 크기 + `underline`, `highlighter`, `ellipse`, `rect`, `dashed_ellipse`, `arrow` | 투명 RGBA 레이어. Pillow만 사용, AI 좌표 추정 없음 |
| 기사 씬 편집 | `app/services/article/frame_editor.py`, `app/services/scene_frames/article_scene.py` / `ArticleSceneRenderer` | `ArticleCapture` + 강조 계획 → 16:9 기사 프레임 | 원본 캡처를 읽기 폭으로 재배치하고 동일 좌표를 다시 매핑. 별도 모드에서는 원문을 재조판할 수 있음 |
| 증거 씬 선택 | `app/services/article/evidence_planner.py` / `ArticleEvidencePlanner.attach()` | 검증 사실, 씬, 기사 후보 → 일치한 기사 캡처와 강조 계획 | `visual_kind="article_scene"`, `visual_type="article_evidence"`, `article_capture`, `emphasis_plan`을 씬에 추가 |
| 이미지 생성 우회 | `app/workers/images_worker.py` / `_article_evidence_path()` | 위 메타데이터 + 유효 `local_path` | `generation_method="article_evidence"`로 원본을 사용하고 Gemini/Kling 생성을 건너뜀 |
| 최종 영상 조립 | `app/workers/longform_worker.py` / `_article_capture_for_scene()` 및 주석 오버레이 경로 | 기사 캡처 이미지 + 결정론적 annotations | FAL/Kling 대상에서 제외하고 정지 증거 프레임으로 조립 |
| API 표면 | `app/main.py` | `POST /workers/evidence/discover`, `/capture`, `/render-quote-card` | URL 탐색·DOM 캡처·명시적 인용 카드 렌더링 제공 |

### 안전 경계

- `capture_dom()`은 공개 HTTP(S) URL만 허용하고, loopback·사설 IP·비표준 포트·URL 내 자격 증명을 거부한다.
- 로그인·구독·결제 제한으로 보이는 페이지는 캡처하지 않는다. 우회·인증·paywall 해제 기능은 없다.
- `EvidenceCaptureRequest`의 인용구는 원문 DOM에서 정확히 찾아야 한다. 찾지 못하면 실패한다.
- 강조 좌표는 DOM `Range.getClientRects()` 또는 사전 검토된 정규화 좌표에서만 온다. 모델이 숫자·텍스트 위치를 추측하지 않는다.

## 2. Playwright 설치·실행 상태

| 항목 | 확인 결과 |
|---|---|
| 의존성 선언 | `requirements.txt`에 `playwright==1.49.1` 선언됨 |
| 배포 Docker 이미지 설계 | `Dockerfile`이 requirements 설치 후 `playwright install chromium`을 실행하도록 정의됨 |
| 현재 작업 환경 | `python -m pip show playwright` → 미설치, `python -m playwright --version` → 모듈 없음 |
| 실제 DOM 캡처 | 이번 조사에서 실행하지 못함. `EvidenceCaptureService`는 import 실패 시 503으로 실패하도록 구현됨 |
| 기존 실제 산출물 | 저장소 범위에서 `article_<hash>.png/.json`, `evidence_plan.json` 실사용 산출물을 찾지 못함 |
| 테스트 | 관련 단위 테스트 13개 통과, 실제 Playwright/Chromium을 쓰는 통합 테스트 1개는 현재 환경에서 skip |

따라서 Docker 이미지를 재빌드한 배포 환경에서는 Chromium 설치를 시도하도록 되어 있지만, **현재 로컬 환경에서 실제 기사 한 건을 성공적으로 캡처한 증거는 없다.** 단위 테스트 통과와 실제 외부 기사 캡처 성공은 구분해야 한다.

## 3. 요청한 유형 3의 필요 범위와 현 상태

| 필요 기능 | 현 상태 | 후속 구현 시 계약 |
|---|---|---|
| 기사 URL 입력 후 크롭·리사이즈 | URL→DOM 캡처는 구현. 16:9 배치도 구현 | 공개 URL, 정확한 원문 인용구, 출처 정보를 입력. Playwright 런타임 준비 필요 |
| 기사 캡처 이미지 입력 후 크롭·리사이즈 | 미구현 | `source_image_path` 또는 검토된 업로드 ID를 받는 별도 `user_image` 입력 계약 필요 |
| 검증된 텍스트·숫자에 밑줄/형광펜 | 구현 | 검증 단계가 제공한 `quote_bboxes`/`key_phrase_bboxes` 또는 사람이 확정한 `EvidenceAnnotation` 좌표만 사용 |
| 텍스트 매칭 | DOM 원문 정확 매칭 구현 | 이미지 파일에서는 OCR 추정 좌표를 자동 확정값으로 쓰지 않는다. OCR은 후보 제안으로만 쓰고, 최종 좌표는 사람 검토 또는 검증 산출물에서 확정 |
| 실제 차트/증권 화면 강조 | 원본 이미지 입력 경로 미구현 | 화면 이미지, 출처 URL/시간, 강조할 검증 항목, 정규화 좌표를 묶은 증거 패킷 필요 |

`ArticleCapture` 모델은 이미 `capture_mode="user_image"`와 `bbox_source="ocr_estimate"` 값을 표현할 수 있다. 그러나 이를 생성·검증·저장하는 서비스와 API는 아직 없으므로, 모델 선언만으로 기능이 완성된 것은 아니다.

## 4. 씬 분류에 대한 제안

기사 캡처형은 `metric`·`graph`와 경쟁하는 의미 분류가 아니라, **근거를 보여주는 렌더 방식**이다. 따라서 새 `scene_type="article_evidence"`를 만들기보다 다음 두 축을 유지하는 편이 안전하다.

```text
scene_type: general | metric | graph | diagram | text
visual_kind:  generated_cartoon | article_scene
```

- `scene_type`은 대본의 의미와 V5 archetype/사실 오버레이 필요성을 결정한다.
- `visual_kind="article_scene"`은 이미 `ImagesWorker`와 `LongformWorker`가 인식하며, Gemini/FAL을 건너뛰고 기사 증거 프레임을 사용한다.
- 예: 실제 수치의 출처를 보여주는 씬은 `scene_type="metric"` + `visual_kind="article_scene"`이 될 수 있다. 같은 의미의 설명 씬은 `scene_type="metric"` + `visual_kind="generated_cartoon"`으로 V5 배경과 Pillow 사실 오버레이를 쓴다.

이 분리는 “정보를 어떤 의미로 설명하는가”와 “그 정보를 어떤 출처 화면으로 보여주는가”를 섞지 않는다.

## 5. 유형 3 구현 전 결정할 사항

1. URL DOM 캡처를 먼저 운영 검증할지, 사용자 제공 캡처 이미지 입력을 먼저 만들지 결정한다.
2. 실제 사용 환경에 Playwright와 Chromium이 설치된 worker를 준비하고, 허용된 공개 기사 1건으로 end-to-end 캡처를 검증한다.
3. 이미지 입력형을 만들 경우, OCR 결과를 자동 강조 좌표로 확정하지 않고 검증 패킷의 좌표/사람 검토를 필수로 한다.
4. 출처 URL·발행 시각·캡처 시각·파일 SHA-256·강조 좌표를 한 증거 메타데이터로 보존한다.

이번 단계에서는 위 항목을 구현하거나 외부 사이트에 접속하지 않았다.

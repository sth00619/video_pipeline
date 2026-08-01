# V5 사용자 업로드 기사 캡처

기사 URL을 브라우저로 다시 캡처하지 않아도, 사용자가 확보한 기사·차트 스크린샷을 증거 이미지로 등록할 수 있다.

## API

`POST /workers/evidence/capture-upload` (multipart/form-data)

| 필드 | 필수 | 설명 |
|---|---:|---|
| `image` | 예 | PNG/JPEG 등의 기사 또는 차트 캡처. 25 MiB 이하, 최소 320×180, 한 변 최대 7680px |
| `job_id` | 예 | 작업 번호 |
| `source_url` | 예 | 검증에 사용한 원문 URL |
| `quote` | 예 | 화면에서 강조할, 이미 검증된 원문 인용 |
| `target_bbox_json` | 예 | 인용 전체 영역의 정규화 좌표 객체 |
| `quote_bboxes_json` | 예 | 줄별 인용 영역 배열. 빈 배열 불가 |
| `source_title`, `publisher`, `published_at` | 아니오 | 출처 메타데이터 |
| `key_phrase`, `key_phrase_bboxes_json` | 함께 사용 | 핵심 수치·문구와 그 정규화 좌표 배열 |

좌표는 모두 `{ "x": 0..1, "y": 0..1, "width": 0..1, "height": 0..1 }` 형식이다. `key_phrase`를 전달하면 `key_phrase_bboxes_json`도 반드시 전달한다.

## 안전 계약

- OCR·LLM·자동 좌표 추정을 사용하지 않는다. 좌표는 크로스체크 단계에서 사람이 확인해 입력한다.
- 업로드 원본은 PNG로 정규화해 보관하고 SHA-256을 메타데이터에 남긴다.
- `capture_mode=user_image`, `bbox_source=verified_input`으로 명시해 DOM 측정 결과와 구분한다.
- 원본 `local_path`와 함께, 노란 형광펜·빨간 밑줄·핵심 문구 원형 표시가 합성된 `annotation_preview_path`를 반환한다. 이 미리보기로 좌표를 확인한 뒤, 실제 영상 조립은 같은 원본과 좌표로 결정론적으로 수행한다.
- 이 기능은 기사 캡처형 이미지 전용이다. Gemini archetype 배경이나 V5 카드형 수치 오버레이에는 적용하지 않는다.

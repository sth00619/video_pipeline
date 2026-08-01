# V5 사용자 업로드 스크린샷 증거 입력 설계

## 목적과 범위

기사 URL을 브라우저로 캡처할 수 없는 경우에도, 사용자가 제공한 원본 스크린샷에 검증자가 확정한 강조를 결정론적으로 합성한다. 이 경로는 AI·OCR이 수치나 위치를 추측하지 않는다.

현재 `ArticleCapture.capture_mode`에는 `user_image` 값이 이미 있으나, 업로드 요청 모델·저장 서비스·API 엔드포인트는 없다. 따라서 아래는 운영 구현 전 설계이며, `scripts/run_user_image_annotation_preview.py`는 원본과 정규화 좌표만으로 결과를 확인하는 로컬 시안 도구다.

## 제안 입력 계약

```json
{
  "job_id": 42,
  "source_image_path": "승인된_로컬_원본.png",
  "source_url": "https://출처-기사-또는-차트-페이지",
  "publisher": "발행처",
  "captured_at": "2026-08-01T00:00:00Z",
  "quote": "검증된 원문 또는 차트 설명",
  "target_spans": [
    {
      "text": "검증된 대상 문자열",
      "bboxes": [[0.12, 0.34, 0.25, 0.06]],
      "bbox_source": "verified_input"
    }
  ],
  "annotations": ["highlighter", "underline"]
}
```

## 필수 안전 규칙

1. `source_url`, 발행처, 캡처 시각, 원본 SHA-256을 함께 저장한다.
2. `target_spans[].bboxes`는 크로스체크 또는 사람 검토가 확정한 좌표만 허용한다.
3. OCR은 후보 탐색 보조로만 쓸 수 있고, OCR 결과만으로 최종 좌표를 확정하지 않는다.
4. 업로드 원본은 Gemini/FAL에 전달하지 않는다. `visual_kind=article_scene`으로 ImagesWorker와 모션 경로를 우회한다.
5. 강조는 Pillow로만 합성하며, 원본 픽셀과 강조 JSON을 별도 보관한다.

## 씬 분류 연결

`scene_type`은 이야기 성격(`general`, `metric`, `graph` 등)을 유지하고, 기사 캡처 선택은 직교 필드 `visual_kind="article_scene"`으로 표현한다. 따라서 `metric` 씬도 카툰 정보형·결정론적 오버레이형·기사 증거형 중 하나를 선택할 수 있다.

## 운영 구현 전 확인할 것

- 업로드 파일 크기·확장자·악성 파일 검사 및 원본 보관 정책
- `bbox_source="verified_input"`을 모델 계약에 추가하는 마이그레이션
- 검증 UI에서 텍스트 구간과 좌표를 사람이 승인하는 흐름
- 기사 저작권·출처 표기 및 영상 사용 권한 정책

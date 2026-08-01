# V5 세 이미지 유형 혼합 롱폼 스모크 테스트 (2026-08-01)

## 목적

실제 롱폼 조립 경로에서 아래 세 유형이 한 요청 안에 함께 들어가고, 서로 다른
처리 규칙이 충돌하지 않는지 확인한다.

1. **정보형**: Gemini가 생성하고 Pillow로 검증 사실을 합성한 V5 PNG
2. **일반형**: 캐릭터 중심의 일반 Gemini 카툰 PNG
3. **기사 캡처형**: 사람이 검증한 좌표를 가진 기사 원본을 조립 직전에 결정론적 강조 프레임으로 렌더링한 장면

## 실행 환경 정합성

검증 전 실행 중이던 `pipeline_fastapi` 컨테이너는 작업 폴더보다 이전 소스였다.
특히 V5 런타임 계약, scene-type archetype, 사실 오버레이 모듈이 누락된 상태였다.

`docker compose build fastapi-workers`와 서비스 재기동 후 아래 파일의 SHA-256이
호스트와 컨테이너에서 일치함을 확인했다.

- `app/workers/images_worker.py`
- `app/workers/longform_worker.py`
- `app/v5/scene/runtime_contract.py`
- `app/v5/scene/scene_type_archetypes.py`
- `app/v5/overlay/diegetic_fact_overlay.py`
- `app/services/evidence_capture.py`
- `app/main.py`

## 발견·수정한 실제 결함

최신 컨테이너에서 첫 조립을 실행했을 때, 세 장면의 MP4 클립 생성과
기사 강조 렌더링, 자막·오디오 합성은 끝났으나 결과 manifest 작성 단계에서
`scene_duration_seconds`의 import 누락으로 `NameError`가 발생했다.

`app/workers/longform_worker.py`에서 해당 helper를 명시적으로 import했고,
관련 회귀 테스트 44건이 통과했다.

## 스모크 입력과 비용 정책

| 순서 | 유형 | 입력 | 조립 규칙 |
|---|---|---|---|
| 0 | 정보형 | 기존 Gemini/Pillow V5 `data_lab` PNG | `v5_verified_overlays`가 있어 FAL 후보에서 제외, 정지 클립 |
| 1 | 일반형 | 기존 Gemini `port_emergency` PNG | 일반 정지 클립 |
| 2 | 기사 캡처형 | 사람이 검증한 원본 캡처·좌표 | `article_scene` 렌더러가 plain/emphasized PNG 생성, Gemini/FAL 우회 |

테스트는 이미 생성된 PNG, 로컬 무음 WAV, FFmpeg만 사용했다. Gemini, FAL/Kling,
TTS, 외부 기사 API 호출은 없었다.

## 결과

`POST /workers/longform/generate`를 실제 FastAPI 컨테이너에 호출했다.

- 최종 MP4: 1920×1080, 6.0초, 자막 3개, 오디오 포함
- 정보형/일반형 입력 PNG 존재 확인
- 기사 캡처 plain/emphasized 프레임 생성 확인
- 세 장면의 FAL/Kling 호출: 0건
- 조립 결과: 성공

산출물:

- `out/v5_pilot/mixed_three_image_type_longform_smoke.mp4`
- `out/v5_pilot/mixed_three_image_type_contact_sheet.png`
- `out/v5_pilot/mixed_three_image_type_longform_smoke_report.json`

## 판정 범위와 남은 검증

이번 통과는 **최신 배포본이 세 유형의 완성 자산을 한 롱폼 요청에서 올바르게
조립한다**는 것을 입증한다.

다음은 별도 실비 검증 대상이다.

- 최신 참조 자산을 사용한 상태에서 `ImagesWorker`가 정보형·일반형 2장을 새로
  Gemini로 생성하고, 같은 요청에 기사 캡처형 1장을 섞어 전체 워크플로를 실행하는
  운영 스모크 테스트
- 실제 TTS 음성으로 opening-TTS 품질 항목까지 통과하는지 확인

이번 테스트의 무음 WAV는 비용 없는 조립 검증용이므로, `output_qc.tts_opening`은
의도적으로 미통과다. 이는 세 이미지 유형 조립 실패가 아니다.

또한 정보형 첫 장면은 기존의 좌상단 카드 배치 문제가 있는 파일을 의도적으로
재사용했다. 이 문서는 해당 카드의 시각 품질이나 배치 수정 통과를 주장하지 않는다.

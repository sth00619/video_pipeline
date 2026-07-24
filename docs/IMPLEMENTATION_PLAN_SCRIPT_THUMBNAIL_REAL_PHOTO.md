# 스크립트·실제 영상 장면 기반 썸네일·실사 인물 합성 구현 계획

작성일: 2026-07-23  
입력 문서:

- `DEV_PLAN_script_thumbnail_generator.md`
- `DEV_PLAN_addendum_real_photo_thumbnails.md`

## 1. 결론과 구현 원칙

두 문서의 기능은 현재 파이프라인에 구현할 수 있다. 다만 현재 코드와 사용자 요구를 함께 만족하려면 다음 네 가지를 우선 원칙으로 삼는다.

1. 기존 `ScriptWorker → TTS → ImagesWorker → Kling/정적 씬 → LongformWorker → ASS 자막` 흐름을 유지한다.
2. 롱폼 썸네일의 기본 원본은 새로 생성한 별도 이미지가 아니라 실제 최종 영상에 사용된 `SCENE_IMAGE` 또는 조립 매니페스트가 가리키는 프레임으로 한다.
3. 캐릭터는 작업 생성 시 확정한 한 개의 캐릭터 정체성만 사용한다. 사용자 선택 캐릭터와 기본 금화 캐릭터를 동시에 Gemini 참조로 전달하지 않는다.
4. 실존 인물은 생성형 모델에 넣지 않는다. 승인된 실사 사진을 로컬 누끼·크롭·톤 보정·외곽선 처리한 뒤 결정론적으로 합성한다.

## 2. 현재 코드에서 확인한 문제와 문서 보정 사항

### 2.1 현재 썸네일이 실제 영상 장면이 아닌 원인

- `app/main.py`의 `/workers/youtube/thumbnail`은 영상 씬 에셋을 받지 않고 제목만 받아 Gemini로 별도 이미지를 생성한다.
- Spring `JobService.generateYoutubePackage()`도 `SCENE_IMAGE` 또는 롱폼 조립 결과를 넘기지 않는다.
- 따라서 현재 썸네일은 영상에 사용되지 않은 별도 생성 이미지가 되는 것이 정상적인 코드 동작이다.

### 2.2 선택하지 않은 금화 캐릭터가 섞일 수 있는 원인

- `ImagesWorker`가 `DEFAULT_CHARACTER_SHEET`를 항상 첫 번째 참조로 넣고 선택한 `character_image_path`를 추가 참조로 붙인다.
- 일부 호출은 `character_reference_paths[0]`만 사용하므로 사용자 선택 캐릭터보다 기본 금화 캐릭터가 우선될 수 있다.
- 영상 이미지 생성은 작업별 `characterOverride`를 반영하지만, 썸네일 생성의 Spring 경로는 `channelId`만 조회한다. 영상과 썸네일의 캐릭터 해석 규칙이 서로 다르다.

### 2.3 썸네일 규격 버그

- 현재 FastAPI 코드는 롱폼을 `1920×1920`, 쇼츠를 `1080×1080`으로 설정할 수 있는 조건문 오류가 있다.
- 롱폼 기본 산출물은 `1280×720`, 쇼츠 커버는 `1080×1920`으로 명시하고 종횡비 회귀 테스트를 추가한다.

### 2.4 문서의 기술 정보 중 수정할 부분

- Anthropic 1시간 캐시 쓰기 비용은 현재 기본 입력의 `2배`이며 `+25%`가 아니다. `+25%`는 5분 캐시 쓰기에 해당한다. 캐시 읽기는 기본 입력의 `0.1배`다.
- `gemini-3.1-flash-image`는 최대 14개 입력 이미지를 지원하지만 캐릭터 일관성용 참조는 최대 4개 범주다. 캐릭터 시트 14장을 모두 인물 참조로 보내는 설계는 피한다.
- Wikimedia Commons의 자유 라이선스는 저작권 외 초상권·인격권·상표권을 자동 해결하지 않는다. 사진 등록 모델에 저작권 라이선스와 별도로 `rights_review_status`를 둔다.

## 3. 목표 아키텍처

```text
검증 데이터 + 기존 스크립트 생성
  └─ 기존 scenes[] 유지
     ├─ narration / TTS / ASS 자막 계약 유지
     ├─ overlay_numbers.source_ref 검증
     └─ thumbnail_brief 추가
          ├─ hook_line / punch_line / badge
          ├─ source_scene_ids[]
          ├─ selected_character_identity
          └─ persons[] (대본에 실제 등장한 인물만)

롱폼 조립
  └─ assembly_manifest.json 신규
       ├─ scene_id, image_path, 실제 사용 여부
       ├─ 시작/종료 시각, Kling 여부
       ├─ character_identity_hash
       └─ article/chart/normal provenance

ThumbnailGenerator v2
  ├─ 실제 사용 씬 후보 수집 및 점수화
  ├─ 상위 3개 장면 선택
  ├─ 선택 캐릭터 또는 승인된 인물 사진 합성
  ├─ Pillow 텍스트·수치·배지·강조 효과 렌더
  ├─ 라이선스/숫자/정체성 하드 가드
  └─ PREVIEW 단계에서 후보 선택
```

썸네일 레이어 순서는 다음으로 고정한다.

| 레이어 | 내용 | 생성 방식 |
|---|---|---|
| L0 | 실제 영상 사용 장면 | 조립 매니페스트의 씬 이미지 또는 확정 프레임 |
| L1 | 크롭, 어두운 그라데이션, 비네팅, 대비 보정 | Pillow/OpenCV |
| L2 | 선택 캐릭터 또는 승인된 실사 인물 최대 2명 | 결정론적 알파 합성 |
| L3 | 검증된 수치 배지, 화살표, 빨간 원/밑줄 | Pillow/OpenCV |
| L4 | 2~3줄 훅 텍스트 | Pillow |
| L5 | 자체 채널 워터마크 | Pillow |

AI 배경 생성은 실제 장면 후보가 모두 품질 기준을 통과하지 못했을 때만 사용하는 명시적 fallback으로 둔다. fallback에서도 선택 캐릭터 외 참조와 실존 인물 생성은 금지한다.

## 4. 단계별 구현 계획

### Phase 0 — 회귀 방지와 캐릭터 정체성 단일화

목표: 새 썸네일 기능 전에 기존 캐릭터·Kling·자막 흐름을 고정한다.

1. `CharacterIdentity` 계약을 만든다.
   - 필드: `profile_id`, `character_key`, `source_asset_paths`, `asset_sha256`, `style_prompt`, `lora_model_id`, `version`.
   - 작업 생성 시 이 값을 스냅샷으로 저장해 채널 프로필이 나중에 바뀌어도 진행 중 작업이 변하지 않게 한다.
2. Spring에 공통 `CharacterAssetResolver`를 두고 영상 이미지와 썸네일이 같은 우선순위를 사용하게 한다.
   - `job.characterOverride → 해당 프로필 → job.channelId 프로필 → 명시적 기본 프로필`.
3. 사용자 선택 프로필이 있으면 `DEFAULT_CHARACTER_SHEET`를 참조 목록에서 제거한다.
4. Gemini 호출 직전 `character_identity_hash`와 참조 파일 해시를 기록하고, 한 요청에 서로 다른 정체성이 섞이면 즉시 실패시킨다.
5. 현재 롱폼/쇼츠 썸네일 종횡비 조건문을 수정하고 회귀 테스트를 추가한다.
6. 기존 Kling 인트로 선택, 기사 캡처, 그래프 강조, 말풍선, ASS 자막의 골든 테스트를 먼저 고정한다.

완료 기준:

- 선택 캐릭터 작업에서 기본 금화 시트가 Gemini 입력에 포함되지 않는다.
- 영상 씬과 썸네일 메타데이터의 `character_identity_hash`가 동일하다.
- 기존 자막 파일과 오디오 타이밍 생성 코드에는 변경이 없다.

### Phase 1 — 스크립트 계약 확장과 검증기

목표: 별도 스크립트 생성기를 중복 구축하지 않고 현재 `ScriptWorker`를 확장한다.

1. `app/services/script/`에 구조화 계약을 분리한다.
   - `schemas.py`: `SceneScript`, `ThumbnailBrief`, `PersonMention`, `VerifiedValueRef`.
   - `number_validator.py`: narration, overlay, badge의 숫자가 `verified_facts`/market snapshot에 존재하는지 검증.
   - `person_validator.py`: `persons[].name`이 실제 narration과 검증된 인물 목록에 등장하는지 검증.
   - `thumbnail_brief_builder.py`: 승인된 scenes에서 후보 씬과 훅을 생성.
2. 현재 존댓말 고정 시스템 프롬프트를 채널별 `script_style_profile`로 바꾼다.
   - 반말/존댓말은 채널 설정으로 선택한다.
   - 레퍼런스 채널의 고유 문구, 채널명, 고정 아웃트로는 복사하지 않는다.
   - 아웃트로는 사용자 채널 프로필의 고정 문자열만 주입한다.
3. 기존 number-safe 문장 분리, TTS 원문, ASS 자막 입력은 그대로 사용한다.
4. `thumbnail_brief`에는 다음을 추가한다.

```json
{
  "hook_line": "{y:핵심 표현}",
  "punch_line": "{r:결론 표현}",
  "badge": {"value": "+13.74%", "source_ref": "facts[2]"},
  "source_scene_ids": ["S1", "S4", "S6"],
  "persons": [{"name": "젠슨 황", "mood": "serious", "source_scene": "S2"}],
  "character_identity_hash": "..."
}
```

5. 현재 Anthropic 캐시 헬퍼를 재사용하되 다음을 보강한다.
   - 고정 시스템/스타일/few-shot 접두부와 가변 데이터 분리.
   - `cache_creation.ephemeral_5m_input_tokens`, `ephemeral_1h_input_tokens`, read 토큰을 비용 원장에 저장.
   - 5분은 1회 재사용부터, 1시간은 최소 2회 재사용 예상 시에만 비용상 유리한 정책으로 선택.

완료 기준:

- 입력에 없는 숫자와 인물이 브리프에 들어가면 생성이 중단된다.
- 기존 스크립트/TTS/자막 결과가 동일한 입력에서 호환된다.
- 썸네일 브리프 실패가 전체 스크립트를 mock 대본으로 바꾸지 않고 명시적 검토 상태로 반환된다.

### Phase 2 — 실제 영상 장면 기반 ThumbnailGenerator v2

목표: 영상에 쓰이지 않은 별도 AI 이미지가 썸네일이 되는 문제를 제거한다.

1. `LongformWorker`가 `assembly_manifest.json`을 저장하도록 한다.
   - 실제 사용한 이미지, 씬 역할, 타임라인, Kling/static, 기사/그래프 여부, 오버레이 영역, 캐릭터 영역을 기록한다.
2. `thumbnail/candidate_collector.py`를 만든다.
   - 매니페스트에 실제 사용된 씬만 후보로 허용한다.
   - 필요한 경우 FFmpeg로 해당 타임스탬프의 대표 프레임을 추출한다.
   - 최종 영상의 자막이 번인된 프레임보다 원본 `SCENE_IMAGE`를 우선해 텍스트 충돌을 줄인다.
3. 후보 점수는 결정론적으로 계산한다.
   - 선명도, 밝기/대비, 과도한 빈 화면·검정 화면 여부.
   - 인물/캐릭터가 텍스트 안전 영역을 침범하는 정도.
   - 브리프의 `source_scene_ids`와 씬 역할 일치도.
   - 기사 캡처는 읽을 핵심 영역이 충분할 때만, 차트는 강조 좌표가 존재할 때만 허용.
4. 상위 3개 서로 다른 씬을 선택해 레이아웃 변형을 생성한다.
5. 기존 `/workers/youtube/thumbnail`을 내부 호환 어댑터로 남기고 신규 계약 `/workers/thumbnails/generate`로 옮긴다.
6. AI fallback은 feature flag로 분리하고 비용 원장에 별도 기록한다.

완료 기준:

- 각 썸네일 후보에 `source_scene_id`, `source_path`, `source_sha256`, `used_in_final_video=true`가 존재한다.
- 실제 장면 모드에서는 썸네일을 위해 Gemini 이미지 호출이 발생하지 않는다.
- 16:9, 9:16 결과가 각각 정확한 규격과 안전 영역을 만족한다.

### Phase 3 — 결정론적 텍스트·강조 렌더러

1. `layout_presets.py`에 16:9/9:16 좌표를 정규화 비율로 정의한다.
2. `text_renderer.py`에서 `{y:}`, `{r:}` 마크업, 한글 줄바꿈, 최소 폰트 크기, `textbbox`, 검정 stroke를 구현한다.
3. 배지는 반드시 `source_ref`가 있는 검증 숫자만 렌더한다.
4. 빨간 점선 원, 화살표, 밑줄은 기존 기사/차트 annotation 좌표 체계를 재사용한다.
5. 텍스트·캐릭터·인물·워터마크 충돌을 사각형 배치 검증으로 차단한다.
6. 폰트 파일과 사용 라이선스를 채널 프로필에 등록하고, 미등록 폰트는 운영 렌더링에서 거부한다.

완료 기준:

- 같은 입력은 픽셀 해시가 동일한 결과를 만든다.
- 잘림, 넘침, 금칙 태그 노출, 숫자 source 누락이 모두 테스트에서 차단된다.
- 기사/차트의 기존 강조와 영상 자막 렌더링에는 영향이 없다.

### Phase 4 — 실사 인물 사진 레지스트리와 누끼 캐시

책임 분리는 다음과 같이 한다.

- Spring: JWT, 등록/승인 API, DB, 라이선스 게이트, 관리자 UI.
- FastAPI: 승인된 사진 조회 결과를 받아 누끼·톤 보정·합성만 수행.
- MinIO: 원본, 누끼 캐시, 중간 레이어, 라이선스 증적 저장.

DB 모델:

- `person_asset`: 이름, 별칭, 상태.
- `person_photo`: 원본/누끼 경로, SHA-256, 라이선스, 출처, 크레딧, 감정/포즈, 승인 상태.
- 추가 필드: `license_version`, `author`, `source_page_url`, `source_file_url`, `retrieved_at`, `transformation_log`, `rights_review_status`, `approved_by`, `approved_at`.

구현 순서:

1. 관리자 전용 `POST /api/assets/person`, `POST /api/assets/person/{id}/photos`, 승인/거절 API를 만든다.
2. 라이선스 ENUM과 하드 가드를 구현한다.
   - 자동 합성 허용: `PRESS_KIT`, `KOGL_TYPE1`, `CC_BY`, `CC_BY_SA`, `OWNED`, `STOCK_LICENSED`, 승인된 `AGENCY_LICENSED`.
   - `UNKNOWN`, 승인 전 사진, 초상권 검토 미완료 사진은 렌더 직전 실패.
3. 사진 수집은 자동화하지 않는다. Wikimedia API나 공식 뉴스룸은 후보 메타데이터 보조에만 사용하고 사람이 원본 페이지와 이용 조건을 승인한다.
4. `rembg[cpu]`의 `isnet-general-use`, `birefnet-portrait`, `birefnet-general`을 20장 정도의 내부 평가셋으로 비교한 뒤 기본 모델을 정한다.
5. `new_session()`을 프로세스 단위로 재사용하고, `photo_id + 원본 sha256 + model_version + mask_params`를 누끼 캐시 키로 쓴다.
6. alpha mask를 morphology open/close와 약한 feather로 정리하고, 원본 얼굴 픽셀은 생성형 편집하지 않는다.
7. 인물 최대 2명, 마스코트와 인물 동시 배치는 명시적 프리셋에서만 허용한다.
8. 미등록 인물은 선택 캐릭터 단독 구성으로 fallback하고 검토 UI에 사유를 표시한다.

완료 기준:

- `UNKNOWN` 또는 미승인 사진은 합성 함수 내부에서 반드시 예외가 난다.
- 같은 사진의 두 번째 요청은 모델 추론 없이 누끼 캐시를 재사용한다.
- Gemini/Fal/Kling에 실사 인물 원본 또는 누끼가 전달되는 코드 경로가 없다.
- CC/공공누리 사진은 크레딧과 변경 내역이 영상 설명 메타데이터에 자동 추가된다.

### Phase 5 — 기존 7게이트와 UI 통합

현재 `GateName`은 7개이므로 별도 여덟 번째 Temporal 게이트를 바로 추가하지 않는다.

1. 스크립트는 기존 `SCRIPT` 게이트에서 narration, verified source, thumbnail brief를 함께 검토한다.
2. 썸네일 후보 선택은 기존 `PREVIEW` 게이트 안에 `thumbnail_review` 패널로 추가한다.
3. 후보 카드에 다음을 표시한다.
   - 실제 사용 씬 번호/시각.
   - 선택 캐릭터 이름과 identity hash 축약값.
   - 인물 사진 출처·라이선스·크레딧.
   - 검증 숫자의 출처.
   - fallback 또는 경고 사유.
4. MANUAL/GUIDED는 후보를 고른 뒤 PREVIEW 승인, AUTO는 가장 높은 유효 후보를 선택한다.
5. 거절 사유 코드를 표준화한다.
   - `CHARACTER_IDENTITY_MISMATCH`
   - `THUMBNAIL_SOURCE_NOT_IN_VIDEO`
   - `NUMBER_MISMATCH`
   - `PHOTO_LICENSE_MISSING`
   - `RIGHTS_REVIEW_REQUIRED`
   - `TEXT_OVERFLOW`
   - `LAYOUT_COLLISION`

완료 기준:

- 기존 Temporal 워크플로 상태 전이가 바뀌지 않는다.
- PREVIEW에서 영상과 썸네일 3종을 함께 확인하고 하나를 선택할 수 있다.
- 썸네일만 다시 생성해도 TTS, 영상 씬, Kling 클립을 재생성하지 않는다.

### Phase 6 — 테스트, 관측성, 점진 배포

테스트 계층:

1. 단위 테스트
   - 캐릭터 resolver 우선순위와 해시.
   - 숫자/인물 검증기.
   - 마크업 파서와 한글 줄바꿈.
   - 라이선스 하드 가드.
   - 누끼 캐시 키와 session 재사용.
2. 통합 테스트
   - FastAPI 가짜 이미지 공급자로 실제 씬 모드에서 외부 이미지 API 호출 0회 확인.
   - Spring 등록/승인/거절 및 크레딧 append 확인.
   - MinIO 원본/누끼/중간 레이어 저장 확인.
3. 골든 이미지 테스트
   - 16:9 캐릭터형, 16:9 실사 인물형, 9:16형.
   - 픽셀 해시 또는 허용 오차 기반 비교와 텍스트 bounding box 검증.
4. E2E 테스트
   - 샘플 작업 1건을 스크립트부터 PREVIEW까지 실행.
   - Kling 인트로, 기사 캡처, 그래프 강조, 말풍선, ASS 자막이 유지되는지 확인.
   - 최종 썸네일의 원본 해시가 assembly manifest 후보 중 하나와 일치하는지 확인.

관측 지표:

- `thumbnail.source_mode=scene|video_frame|ai_fallback`
- `thumbnail.character_identity_mismatch_count`
- `thumbnail.rembg_cache_hit_rate`
- `thumbnail.external_image_cost_krw`
- `thumbnail.variant_reject_reason`
- `anthropic.cache_5m_write_tokens`, `cache_1h_write_tokens`, `cache_read_tokens`

배포 순서:

1. `thumbnail.pipeline_v2_enabled=false`로 코드만 배포.
2. 내부 샘플 작업에서 기존 방식과 v2를 동시에 생성하는 shadow mode 실행.
3. 실제 장면 출처, 캐릭터 해시, 라이선스, 텍스트 잘림을 수동 검수.
4. 신규 작업 일부만 v2로 전환.
5. 오류율과 비용이 기준 이하일 때 기본값을 v2로 변경.
6. 기존 엔드포인트는 일정 기간 호환 어댑터로 유지한 뒤 제거.

## 5. 예상 파일 변경 범위

FastAPI:

- `app/services/script/schemas.py`
- `app/services/script/number_validator.py`
- `app/services/script/person_validator.py`
- `app/services/script/thumbnail_brief_builder.py`
- `app/services/thumbnail/thumbnail_generator.py`
- `app/services/thumbnail/candidate_collector.py`
- `app/services/thumbnail/layout_presets.py`
- `app/services/thumbnail/text_renderer.py`
- `app/services/thumbnail/person_compositor.py`
- `app/services/thumbnail/license_guard.py`
- `app/workers/script_worker.py`
- `app/workers/images_worker.py`
- `app/workers/longform_worker.py`
- `app/main.py`
- `app/runtime_config.py`

Spring:

- `domain/PersonAsset.java`, `PersonPhoto.java`
- `repository/PersonAssetRepository.java`, `PersonPhotoRepository.java`
- `service/CharacterAssetResolver.java`
- `service/PersonAssetService.java`
- `service/JobService.java`
- `service/FastApiClient.java`
- 관리자/썸네일 선택 controller와 DTO
- `schema.sql`의 idempotent DDL

Frontend:

- 인물 사진 등록·라이선스 승인 화면
- PREVIEW 내 썸네일 3종 선택 패널
- 씬 출처, 캐릭터, 라이선스, 숫자 근거 표시

## 6. 최종 Definition of Done

1. 선택하지 않은 캐릭터가 영상 또는 썸네일에 섞이지 않는다.
2. 롱폼 썸네일 후보 3종은 모두 실제 최종 영상에 사용된 장면을 원본으로 사용한다.
3. 텍스트, 숫자, 배지, 빨간 강조는 결정론적 렌더러가 처리한다.
4. 실사 인물은 승인된 실제 사진만 사용하고 얼굴 생성·변형 API 호출이 없다.
5. 숫자는 검증 데이터의 `source_ref` 없이는 화면에 표시되지 않는다.
6. 기존 Kling 인트로, 카툰 씬, 캐릭터 베이스 이미지, 기사 캡처, 그래프 강조, 말풍선, ASS 자막이 유지된다.
7. 썸네일 재생성이 영상·TTS·Kling 재생성을 유발하지 않는다.
8. PREVIEW에서 썸네일 후보, 실제 씬 출처, 라이선스, 크레딧을 확인하고 선택할 수 있다.
9. 외부 이미지 생성 비용, 누끼 캐시, 캐릭터 정체성 오류가 지표로 남는다.
10. feature flag와 shadow mode를 거쳐 단계적으로 활성화된다.

## 7. 조사 근거

- Anthropic Prompt Caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Anthropic Pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Gemini Image Generation: https://ai.google.dev/gemini-api/docs/image-generation
- Pillow ImageDraw: https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html
- OpenCV Morphological Transformations: https://docs.opencv.org/master/d9/d61/tutorial_py_morphological_ops.html
- rembg 공식 저장소: https://github.com/danielgatis/rembg
- FFmpeg Filters: https://ffmpeg.org/ffmpeg-filters.html
- PySceneDetect 공식 저장소/문서: https://github.com/Breakthrough/PySceneDetect
- YouTube Thumbnail API: https://developers.google.com/youtube/v3/docs/thumbnails
- Wikimedia Commons 재사용 가이드: https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
- 공공누리: https://www.kogl.or.kr


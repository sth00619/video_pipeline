# 현재 영상 파이프라인 구조 현황

작성일: 2026-07-30
목적: 현재 구현의 **대본 → TTS → 이미지 → 영상 조립** 연결을 설명한다. 설계 제안이나 기능 변경 문서가 아니다.

## 먼저 알아둘 구분

저장소에는 두 경로가 함께 있다.

| 경로 | 현재 역할 | 실제 운영 워크플로 연결 여부 |
|---|---|---|
| 기본 운영 경로(V3/V4 계열) | Spring + Temporal이 대본, TTS, 이미지, FFmpeg 조립을 순서대로 실행 | 연결됨 |
| V5 파일럿 경로 | Gemini 이미지 품질 검증, `v5_verified_overlays` 검증, 장면 속 소품에 수치를 합성하는 실험·검증 도구 | 기본 운영 워커에 자동 연결되지 않음 |

따라서 현재 V5의 좋은 카툰 결과와 수치 소품 합성은 파일럿에서 검증되었지만, 일반 운영 작업 하나가 생성될 때 V5 `prompt_builder.py`가 자동으로 선택되는 상태는 아니다. 아래에서 두 경로를 구분해 설명한다.

---

## 전체 흐름

```text
사용자 키워드·작업 설정
  → Spring ScriptService / FastAPI ScriptWorker
  → 검증 사실 + sections(씬 메타데이터)
  → Spring DB Asset(SCRIPT) 저장·게이트 승인
  → TtsWorker: MP3 + 자막 chunks
  → Spring DB Asset(TTS) 저장·게이트 승인
  → ImagesWorker: scene PNG + 이미지 메타데이터
  → Spring DB Asset(SCENE_IMAGE) 저장·게이트 승인
  → LongformWorker: 씬별 duration 재계산 → MP4 clips → concat → ASS 자막/BGM 병합
  → MP4 + 품질 보고서 + 조립 manifest
```

Spring의 `VideoPipelineWorkflowImpl`이 Temporal workflow로 위 단계를 오케스트레이션한다. 각 큰 단계 사이에는 키워드·대본·TTS·이미지·미리보기 게이트가 있다.

---

## 1. 대본 → 씬 분할

### 1-1. 기본 운영 경로

#### 관련 파일과 역할

| 파일 | 핵심 함수/클래스 | 한 줄 역할 |
|---|---|---|
| `backend/fastapi-workers/app/workers/script_worker.py` | `ScriptWorker.generate()` | 시장 데이터·뉴스를 근거로 Claude를 호출해 검증 대본과 씬 메타데이터를 만든다. |
| 같은 파일 | `_multi_round_fact_check()` | 사실 후보 → 교차 검토 → JSON 확정의 3회 사실 검토를 수행한다. |
| 같은 파일 | `_generate_with_verified_facts()` | 검증 사실만으로 대본 원문을 생성한다. |
| 같은 파일 | `_parse_sections()` | `## 씬`, `[대사]`, `[비주얼 설명]`, `[비주얼 프롬프트]`, `[감정]` 등에서 초기 씬 배열을 만든다. |
| 같은 파일 | `_split_sections_for_visual_pacing()` | 긴 씬을 시각적 호흡 단위로 나누고 `section`을 다시 배정한다. |
| `backend/fastapi-workers/app/utils/quality_gate.py` | `enrich_scene_plans()` | `section`에 따라 기본 `visual_type`·`visual_plan`을 추가한다. |
| `backend/fastapi-workers/app/utils/art_direction.py` | `direct_scenes()` | 씬마다 무대 계열, 마스코트 위치, 소품, 데이터 표면 후보를 결정론적으로 부여한다. |
| `backend/fastapi-workers/app/utils/script_delivery.py` | `annotate_sections()` | 낭독용 문장, 감정, 예상 시작·종료, 편집 마커를 붙인다. |
| `backend/spring-app/.../service/ScriptService.java` | `generate()`, `confirm()` | FastAPI 결과를 `SCRIPT` Asset으로 DB에 저장하고, 확정 시 운영용 씬을 다시 정규화한다. |

#### 입력 → 출력

`ScriptWorker.generate()`의 주요 입력은 다음과 같다.

```json
{
  "keyword": "코스피 7월 전망",
  "category": "KOSPI",
  "target_minutes": 20,
  "market_data": { "kr": {}, "us": {} },
  "data_visuals_enabled": true
}
```

반환되는 전체 대본 계약의 핵심 형태는 다음과 같다.

```json
{
  "script": "전체 한국어 내레이션",
  "verified_facts": [
    { "fact": "...", "figure": "...", "source_field": "...", "confidence": 1.0 }
  ],
  "sections": [
    {
      "title": "씬 제목",
      "content": "이 씬의 낭독문",
      "prompt_ko": "한국어 비주얼 설명",
      "prompt_en": "영문 이미지 프롬프트 초안",
      "prompt": "prompt_en의 호환 필드",
      "pose": "happy|worried|...",
      "motion_type": "chart_shock|... 또는 빈 값",
      "bubble_text": "검증된 짧은 말풍선 또는 빈 값",
      "bubble_validation": { "passed": true, "reasons": [] },
      "scene_rejected": false,
      "section": "intro|background|data|scenario|action|conclusion",
      "char_count": 42,
      "visual_type": "data_visual 등",
      "visual_plan": { "objective": "...", "overlay_type": "fact_card 또는 null" },
      "art_direction": { "family": "...", "data_surface_kind": "..." },
      "style_profile": "editorial_comic_2d",
      "image_profile": { "tier": "...", "model": "..." },
      "market_chart": {},
      "data_overlay_plan": {},
      "editorial_overlay_plan": {},
      "phase": "hook|context|twist|resolution",
      "emotion_tag": "highlight|...",
      "edit_marker": "data_overlay|emphasis_zoom|scene_change",
      "sentences": []
    }
  ]
}
```

모든 필드가 항상 존재하지는 않는다. 특히 `market_chart`, `data_overlay_plan`, `editorial_overlay_plan`, `index_data`는 해당 씬이 선택·검증된 경우에만 추가된다.

#### 씬 분할 시점과 다음 단계 전달 방식

1. Claude가 먼저 `## 씬` 단위의 풍부한 대본을 만든다.
2. `ScriptWorker._parse_sections()`가 이를 초기 씬 객체로 변환한다.
3. 이후 시각적 호흡을 위해 분할·재배정될 수 있다. 즉 **대본 생성과 동일한 FastAPI 단계 안에서 씬 분할이 일어나며, 별도 배치 작업이 아니다.**
4. FastAPI 반환 객체는 HTTP 응답으로 Spring `ScriptService`에 돌아간다.
5. Spring은 이 JSON을 DB의 `AssetType.SCRIPT` `metaJson`에 저장한다.
6. 대본 확정 시 `ScriptService.confirm()`은 긴 내레이션을 최대 78자 단위로 다시 나눌 수 있다. 이때 운영용 `sections`가 다시 DB에 저장된다.

즉, 메모리 객체로 바로 TTS까지 넘어가는 구조가 아니다. **Script Asset(JSON) → 게이트 → 다음 서비스가 DB에서 다시 읽는 방식**이다.

#### “수치/그래프에 적합한 씬” 필드는 이미 있는가?

부분적으로 있다. 다만 사용자가 구상한 단일한 `scene_type` 분류는 아직 없다.

- `section == "data"`: 데이터 설명 구간이라는 가장 강한 기존 신호다.
- `visual_type == "data_visual"`: `enrich_scene_plans()`가 `section=data`에서 부여한다.
- `market_chart`: 검증된 시계열에서 그래프를 만들 수 있는 씬에만 붙는다.
- `data_overlay_plan`: 차트·비교·구성비 등 결정론적 데이터 오버레이의 계약이다.
- `art_direction.data_surface_kind`, `art_direction.data_surface`: 이미지 안의 물리 소품 후보와 위치 계약이다.
- `edit_marker == "data_overlay"`: 낭독문에 숫자가 있으면 붙는 편집 힌트다.
- `bubble_text`/`editorial_overlay_plan`: 짧은 화면 문구를 별도 레이어로 처리할 수 있는 계약이다.

반면 다음은 **현재 없다.**

```json
{
  "scene_type": "graph|metric|diagram|text|general",
  "selection_reason": "검증 사실의 성격과 장면 적합성",
  "render_mode": "diegetic_metric|background_only|..."
}
```

현재는 `section`, 단어 탐지, `extract_market_chart()`, 시각 연출 규칙의 조합으로 간접 분기한다.

### 1-2. V5 파일럿 경로

#### 관련 파일과 역할

| 파일 | 핵심 함수/클래스 | 한 줄 역할 |
|---|---|---|
| `backend/fastapi-workers/scripts/run_v5_kospi_july_pilot.py` | `collect_evidence()` | NAVER 뉴스 검색 결과 중 기사 원문까지 확인 가능한 근거를 수집한다. |
| 같은 파일 | `cross_check()` | Claude 3회 검토 뒤 원문에 실제 존재하는 숫자만 확정한다. |
| 같은 파일 | `generate_script()` | 확정된 사실만 사용한 3씬 파일럿 대본 JSON을 생성한다. |
| 같은 파일 | `build_pilot_input()` | 대본 씬·배경 경로·검증 사실·오버레이 좌표를 하나의 V5 입력으로 만든다. |
| `backend/fastapi-workers/scripts/validate_v5_pilot_input.py` | `validate_payload()` | 출처, 값의 원문 존재 여부, 좌표, 배경 파일, 1~3씬 제한을 차단형으로 검증한다. |

#### 입력 → 출력

V5 파일럿 씬은 기본 운영 `sections`와 별도 형태다.

```json
{
  "scene_id": "kospi_july_01",
  "background_path": "out/.../bench_08_datalab.png",
  "narration": "이 씬의 검증 대본",
  "visual_intent": "시각적 의도",
  "verified_facts": [
    {
      "fact": "기사 원문에 있는 사실",
      "figure": "원문 그대로의 수치",
      "source_url": "https://...",
      "source_title": "..."
    }
  ],
  "v5_verified_overlays": [
    {
      "label": "표시 라벨",
      "value": "figure와 일치하는 값",
      "source_ref": "facts[0]",
      "anchor": { "x": 0.06, "y": 0.12, "width": 0.27, "height": 0.16, "kind": "placard" }
    }
  ]
}
```

#### 다음 단계 전달 방식

V5 파일럿은 `out/v5_pilot/.../*.json` 파일로 저장해 넘긴다. `build_v5_pilot_assembly_manifest.py`는 이를 읽어 순서·배경 경로·출처를 담은 조립 manifest를 만든다. TTS 실측 길이가 아직 없으면 `duration_seconds: null`로 유지한다.

기본 Spring workflow와는 아직 자동 접점이 없다.

---

## 2. 씬 → 이미지 프롬프트 → 이미지 생성

### 2-1. 기본 운영 경로

#### 관련 파일과 역할

| 파일 | 핵심 함수/클래스 | 한 줄 역할 |
|---|---|---|
| `backend/fastapi-workers/app/workers/images_worker.py` | `ImagesWorker.generate()` | 스크립트 Asset의 `sections`를 받아 이미지 작업을 준비하고 결과를 반환한다. |
| 같은 파일 | `_generate_parallel_scenes()` | 씬별 컨텍스트·비용 가드·요청 감사를 준비하고 병렬 생성한다. |
| 같은 파일 내부 | `make_context()` | 원본 씬에 시각 계획·템플릿·프롬프트·데이터 오버레이 필드를 합친다. |
| `backend/fastapi-workers/app/pipeline/scene_director.py` | `SceneDirector.direct_batch()` | 낭독문별 역할·의상·소품·무대·카메라를 한 번의 Claude 호출로 조율한다. |
| `backend/fastapi-workers/app/providers/real/prompt_builder.py` | `build_prompt()` | 운영 이미지 생성기에 보내는 최종 영문 프롬프트를 조립한다. |
| `backend/fastapi-workers/app/services/info_surface/info_scene_templates.py` | `select_template()` | 검증 데이터 장면에 적용할 물리적 표면 템플릿을 고른다. |
| `backend/fastapi-workers/app/providers/real/image.py` | `NanaBananaProvider.generate_image()` 등 | Gemini/FAL 계열 실제 이미지 API 호출을 수행한다. |
| `backend/spring-app/.../service/ImagesService.java` | `generate()` | 이미지 결과를 `SCENE_IMAGE` Asset으로 DB에 저장한다. |

#### 입력 → 출력

이미지 워커는 Spring에서 다음 성격의 값을 받는다.

```json
{
  "job_id": 123,
  "script_meta_json": "{ sections: [...] }",
  "tts_meta_json": "{ total_duration, chunks, ... }",
  "character_image_path": "...",
  "character_poses_dir": "...",
  "character_style_prompt": "..."
}
```

각 씬은 `make_context()`에서 대략 다음과 같이 변환된다.

```text
section 원본
  → enrich_scene_plan()
  → _apply_info_scene_template() (해당할 때만)
  → SceneDirector.direct_batch() 결과의 SceneSpec 결합
  → build_prompt(spec, market_chart, template)
  → 이미지 공급자 1회 요청용 context
```

생성 결과의 대표 구조는 다음과 같다.

```json
{
  "index": 0,
  "image_path": "/app/data/jobs/123/images/scene_000.png",
  "clean_plate_path": "...scene_000_bg.png 또는 null",
  "generation_method": "pro_gemini|flash_gemini|flux_lora|resumed_existing",
  "prompt_en": "실제 요청 프롬프트",
  "section": "data",
  "scene_spec": {},
  "art_direction": {},
  "market_chart": {},
  "data_overlay_plan": {},
  "quality_score": 0,
  "quality_flags": [],
  "retry_recommended": false
}
```

#### 이미지 호출 횟수

- 정상 경로는 **씬 1개당 이미지 API 요청 1회**다.
- 이미지 공급자 내부 재시도는 `gemini_max_attempts=1`로 호출되도록 전달되지만, 워커 바깥의 씬 실행기는 설정값 범위 안에서 재시도할 수 있다.
- 물리 표면 감지 실패이면서 템플릿 재생성이 승인된 경우에만 `template_regen:{index}`라는 **추가 1회 요청** 경로가 있다.
- 완료 이미지는 fingerprint가 같으면 재사용한다. 재실행 때 무조건 새로 생성하지 않는다.

#### 씬별 그래프형/일반형 분기 지점

있다. 현재는 한 함수로 완전히 동일하게 처리하지 않는다.

1. `section == "data"` → `direct_scenes()`가 `data_surface`, `data_surface_kind`, `layer_pipeline`을 계획한다.
2. `extract_market_chart()`가 가능한 검증 시계열을 찾으면 `_attach_verified_market_charts()`가 `market_chart`, `data_overlay_plan`, `embedded_copy`를 붙인다.
3. `ImagesWorker.make_context()` → `_apply_info_scene_template()` → `select_template()`가 해당 장면을 물리 표면 템플릿으로 분기한다.
4. `build_prompt(spec, market_chart, template)`는 템플릿 유무와 `market_chart` 존재 여부에 따라 프롬프트를 다르게 만든다.
5. 생성 직후 `_apply_image_overlays()` / `_apply_info_surface_plan()`가 결정론적 그래프·도식·문구를 합성한다.

다만 기본 운영 `prompt_builder.py`는 현재도 `market_chart`가 있으면 큰 빈 보드/패널을 요구하는 유산이 남아 있다. 이는 사용자가 선호한 “장면 속 원래 소품에 자연스럽게 수치를 새김” 방식과 완전히 일치하지 않는다.

### 2-2. V5 이미지 프롬프트 경로

#### 관련 파일과 역할

| 파일 | 핵심 함수/클래스 | 한 줄 역할 |
|---|---|---|
| `backend/fastapi-workers/app/v5/scene/prompt_builder.py` | `SceneSpec`, `build_prompt()` | V5 벤치마크/파일럿용 마스코트·무대·정보 밀도·문자 정책 프롬프트를 만든다. |
| 같은 파일 | `ARCHETYPES` | 항만, 소매, 교실, 날씨 지도, 위험 관제실 등 무대 레시피다. |
| `backend/fastapi-workers/app/v5/scene/layout_sketcher.py` | `LayoutSketcher.for_mascot_position()` | 마스코트 좌/중/우 위치와 자막·로고·사실 표면 안전영역을 계산한다. |
| `backend/fastapi-workers/app/v5/scene/quality_gate.py` | `QualityGate.score()` | 종횡비·빈 화면·소품 밀도 등 재현 가능한 1차 품질 조건을 검사한다. |
| `backend/fastapi-workers/app/v5/overlay/diegetic_fact_overlay.py` | `apply_verified_scene_facts()` | 검증된 값을 지정된 소품 표면 좌표 안에 결정론적으로 합성한다. |

#### 입력 → 출력

```python
SceneSpec(
  scene_id="bench_05_weather",
  archetype="weather_map",
  emotion="explain",
  costume="reporter",
  pose="present",
  frame_occupancy=0.42,
  character_position="right"
)
```

`build_prompt()`는 이를 단일 영문 문자열로 바꾼다. 기본값 `visual_text_policy="textless"`는 AI 문자 생성을 금지한다. `diegetic_decorative`를 선택하면 AI 문자·숫자는 장식으로만 허용하되, 지도·명패·계기판 같은 기존 소품 재질 안에 있어야 한다고 지시한다.

V5는 현재 8개 `BENCHMARK_SCENES`와 파일럿 스크립트에서 개별 실행된다. 기본 `ImagesWorker`가 V5 `SceneSpec`을 자동 생성해서 쓰지는 않는다.

---

## 3. TTS 생성 → 자막 → 이미지 타이밍 매칭

### 관련 파일과 역할

| 파일 | 핵심 함수/클래스 | 한 줄 역할 |
|---|---|---|
| `backend/fastapi-workers/app/workers/tts_worker.py` | `TtsWorker.generate()` | 대사만 추출해 TTS MP3와 문자 단위 자막 chunks를 만든다. |
| 같은 파일 | `_extract_timestamps_with_forced_alignment()` 등 | TTS 오디오와 자막 텍스트를 정렬한다. |
| `backend/fastapi-workers/app/tts/forced_alignment_srt.py` | `words_to_cues()`, `cues_to_srt()` | 단어/문자 시각을 읽기 쉬운 자막 cue로 묶는다. |
| `backend/fastapi-workers/app/workers/longform_worker.py` | `_assign_scene_durations_from_chunks()` | 최종 TTS chunk 시간과 씬 낭독문 길이를 이용해 씬 duration을 정한다. |
| `backend/spring-app/.../service/TtsService.java` | `generate()` | TTS 결과를 `TTS` Asset으로 DB에 저장한다. |

### 입력 → 출력

TTS 입력은 확정 대본의 **낭독문**이다. 이미지 프롬프트나 비주얼 설명은 `extract_narration()`으로 제거된다.

```json
{
  "script": "대본 전체 또는 [대사]가 포함된 대본",
  "voice_id": "...",
  "target_seconds": 1200
}
```

출력:

```json
{
  "audio_path": "/app/data/jobs/123/tts/full.mp3",
  "total_duration": 1197.2,
  "chunks": [
    { "text": "자막 한 덩어리", "start": 0.2, "end": 2.6, "duration": 2.4 }
  ],
  "duration_validation": {},
  "quality_report": {}
}
```

### 실제 순서와 매칭 방식

- 기본 workflow 순서는 **대본 확정 → TTS 완료 → 이미지 생성 → 조립**이다. TTS와 이미지가 병렬로 시작하지 않는다.
- 하지만 현재 이미지 생성은 TTS `chunks`마다 1장을 만드는 구조가 아니다. 이미지는 **씬(`sections`)마다 1장**이다.
- 자막은 문장/호흡 단위의 `chunks`로 더 잘게 나뉜다. 따라서 한 씬에는 여러 자막 chunk가 들어갈 수 있다.
- `LongformWorker._assign_scene_durations_from_chunks()`가 씬의 `content` 문자 길이를 전체 문자 길이와 비교하고, TTS chunk의 실측 start/end 시각에 비례시켜 `start_time`, `end_time`, `duration`을 산출한다.
- 즉 현재 매칭은 “자막 1개 = 이미지 1장”이 아니라 **여러 자막 cue → 하나의 씬 이미지**다.

### duration은 어떻게 결정되는가?

1. 대본 단계 `annotate_sections()`의 `start_seconds`, `end_seconds`는 목표 길이와 글자 수에 따른 **사전 추정값**이다.
2. 최종 조립 직전 `LongformWorker._assign_scene_durations_from_chunks()`가 실제 TTS 길이와 chunk 시각으로 **재계산한 값**이 우선이다.
3. chunk가 없거나 매칭이 실패하면 씬 문자 수 비례, 그마저도 불가하면 씬 수 균등 분배로 폴백한다.

V5 파일럿 조립 manifest는 TTS 실측 audio가 들어오기 전에는 duration을 의도적으로 비워 둔다. 이 역시 최종 TTS 결과가 있어야 정확히 확정할 수 있다는 같은 원칙이다.

---

## 4. 최종 영상 조립

### 관련 파일과 역할

| 파일 | 핵심 함수/클래스 | 한 줄 역할 |
|---|---|---|
| `backend/fastapi-workers/app/workers/longform_worker.py` | `LongformWorker.assemble()` | 씬 PNG/클립, TTS, BGM, 자막을 FFmpeg로 최종 MP4로 만든다. |
| 같은 파일 | `_generate_scene_clips()` | 각 씬을 정지 이미지 클립 또는 선택된 Kling 모션 클립으로 만든다. |
| 같은 파일 | `_ffmpeg_static_image()` / `_ffmpeg_static_image_with_fade()` | 정지 이미지를 씬 duration 길이의 1920×1080 MP4로 변환한다. |
| 같은 파일 | `_apply_editorial_overlays()` | 검증 차트, 말풍선, 문구 등 씬별 후처리 레이어를 적용한다. |
| 같은 파일 | `_generate_ass()` | TTS chunks와 선택적 씬 자막 override에서 ASS 자막을 만든다. |
| `backend/spring-app/.../service/LongformService.java` | `generate()` | DB의 TTS·SCENE_IMAGE Asset을 정렬해 FastAPI 조립 요청을 보낸다. |
| `backend/spring-app/.../service/FastApiClient.java` | `assembleLongform()` | FastAPI `/workers/longform/generate` HTTP 요청을 보낸다. |

### 입력 → 출력

`LongformWorker.assemble()`의 핵심 입력은 JSON 문자열 세 개다.

```json
{
  "tts_meta": { "audio_path": "...", "total_duration": 120.0, "chunks": [] },
  "scenes_meta": [
    { "index": 0, "image_path": "...png", "content": "...", "section": "data", "market_chart": {} }
  ],
  "gifs_meta": []
}
```

출력:

```json
{
  "video_path": "/app/data/jobs/123/final.mp4",
  "duration_seconds": 120.0,
  "scene_count": 24,
  "has_subtitles": true,
  "quality_report": {}
}
```

### 다음 단계 전달 방식

1. Spring `LongformService`가 DB `SCENE_IMAGE`, `TTS`, `GIF_CLIP` Assets를 읽고 순서를 정한다.
2. FastAPI longform worker가 임시 디렉터리에 씬 MP4들을 쓴다.
3. FFmpeg concat으로 `silent.mp4`를 만들고, ASS 자막·TTS·BGM을 합성한다.
4. 최종 MP4 경로와 품질 보고서는 FastAPI 응답으로 Spring에 돌아가며, Spring이 `VIDEO` 계열 Asset으로 저장한다.

### 씬별 다른 영상 처리 가능 여부

가능하며, 이미 일부 분기점이 존재한다.

- `motion_type`, `use_kling`, `image_profile` 등에 따라 일부 씬은 Kling/FAL 모션, 나머지는 정지 이미지 클립이 된다.
- 정지 이미지 기본은 흔들림 없는 고정 이미지 또는 0.5초 페이드다.
- `market_chart`, `data_overlay_plan`, `editorial_overlay_plan`, `subtitle_text`에 따라 그래프·문구·자막 override 후처리가 달라진다.
- `_apply_editorial_overlays()`와 `_generate_scene_clips()`가 씬 타입별 전환·노출 방식을 추가할 수 있는 가장 직접적인 위치다.

기본적으로는 모든 이미지를 먼저 개별 MP4 클립으로 만들고 concat한다. 따라서 “그래프 씬은 정지 유지, 일반 배경 씬은 짧은 모션” 같은 정책은 구조상 가능하지만, 현재의 단일 명시적 `scene_type` 정책으로 통합되어 있지는 않다.

---

## 현재 구조에서의 판단: 씬 타입 분류를 넣기 좋은 지점

### 결론

가장 자연스러운 위치는 **대본 생성 직후의 씬 계획 단계**다. 구체적으로는 `ScriptWorker.generate()`에서 검증 사실과 `sections`가 모두 확정된 뒤, `direct_scenes()`와 `_attach_verified_market_charts()` 사이 또는 그 직후가 적합하다.

이유:

1. 이 시점에는 씬의 낭독문, 검증 사실, 출처, 시장 시계열, 섹션 역할이 동시에 있다.
2. 이후 이미지 프롬프트·결정론적 합성·영상 조립이 같은 분류를 공유할 수 있다.
3. 프롬프트 빌더만 분기하면 “왜 이 씬에 실제 수치가 필요한지”와 “무엇을 검증했는지”를 알 수 없다.

권장 책임 분리:

```text
대본/사실 검증 단계
  → scene_type 후보와 근거를 결정
  → 이미지 단계
     → scene_type에 맞는 V5 무대·소품·프롬프트를 선택
     → 검증 데이터가 있을 때만 결정론적 합성
  → 영상 조립 단계
     → scene_type별 정지/모션/노출 규칙 적용
```

### 필드 하나만 추가하면 되는가?

아니다. 시작은 필드 하나로 가능하지만, 완성된 기능은 여러 파일의 계약 변경이다.

최소 시작 필드는 예를 들면 다음과 같다.

```json
{
  "scene_type": "general|metric|graph|diagram|text"
}
```

그러나 이 필드만 추가하면 프롬프트만 달라지고 검증·출처·합성·조립의 일관성이 없다. 실제 운영에 쓰려면 적어도 다음 연결이 필요하다.

| 계층 | 필요한 연결 |
|---|---|
| 대본/검증 | `scene_type`와 선택 근거, 참조 사실·출처를 장면 메타데이터에 저장 |
| 이미지 계획 | 타입에 맞는 V5 archetype/물리 소품/마스코트 배치 선택 |
| 합성 | `metric/graph/diagram/text`는 검증된 payload가 있을 때만 해당 소품 내부에 렌더링 |
| 품질 게이트 | 실제 수치가 원문·출처와 일치하고, 소품 밖의 UI 카드가 아닌지 검사 |
| 영상 조립 | 타입별 노출 시간·모션 허용 여부·강조 타이밍을 적용 |

따라서 이는 “필드 하나를 추가하는 작업”으로 시작할 수 있으나, 사용자 목표인 정확한 수치와 자연스러운 카툰 소품 통합까지 달성하려면 **여러 파일이 같은 장면 계약을 공유하도록 정리하는 구조 변경**이다.

## 현 시점의 핵심 사실

- 기본 운영 파이프라인은 이미 `section=data`, `market_chart`, `data_overlay_plan`이라는 데이터 장면 단서를 가진다.
- V5는 자연스러운 카툰 무대·소품 안의 수치 합성 검증을 별도 파일럿으로 갖고 있다.
- 두 경로의 장면 계약은 아직 다르다.
- 따라서 다음 설계 논의의 핵심은 “V5 표현 계약을 기본 운영 `sections`에 어떤 최소 공통 필드로 연결할 것인가”이지, 단순히 이미지 프롬프트를 하나 더 만드는 문제가 아니다.

# 세 목표 실제 파이프라인 통합 현황 감사

작성일: 2026-08-02  
기준 커밋: `4c01a7894c85de8a3cfae73df6ea11bcdebf4739` (`main == origin/main`)  
범위: 코드·기존 산출물·기존 실행 기록의 읽기 전용 조사. 코드 수정, API 호출, 브라우저 실행은 하지 않았다.

## 1. 결론

세 목표(3종 이미지, 인트로 Kling 모션, 자동 썸네일)는 모두 일부 또는 상당한 구현과 production 호출 경로를 갖는다. 그러나 **한 작업에서 세 기능이 함께 실행되어 완성 영상과 롱폼/쇼츠 썸네일까지 생성된 E2E 기록은 확인하지 못했다.** 단위 테스트, 독립 pilot, 개별 PNG/MP4는 존재하지만 통합 완료 증거로는 부족하다.

특히 현재 코드는 승인된 정책과 다음 충돌을 가진다.

1. 폐기 지시된 OpenCV `composite_planar` 경로가 production `ImagesWorker`에서 계속 호출된다.
2. 모션 정책이 `40초/60초`이며 사용자 의도인 `45초/60초`와 다르다.
3. Fal billing endpoint 호출 및 403→usable 우회가 남아 있다.
4. FastAPI JSON 비용 원장과 Spring DB `CostLedger`가 분리되어 있으며, 20분 이상 8만원 상한도 없다.
5. Pro→Flash 자동 강등이 여전히 예산 preflight에 구현돼 있다.
6. YouTube 패키지와 썸네일 오류가 무음 처리되며, `publishVideo()`는 mock URL을 저장한다.
7. 기사 bbox의 `ocr_estimate`를 AUTO에서 GUIDED로 승격하는 정책은 구현돼 있지 않다.

## 2. 증거 수준 정의

| 등급 | 의미 |
|---|---|
| 코드 배선 확인 | production API 또는 workflow에서 호출되는 코드를 확인했다. |
| 독립 E2E | 실제 URL/파일을 입력해 PNG 또는 MP4가 나온 기록이다. 전체 영상 workflow를 의미하지 않는다. |
| 통합 E2E | Spring workflow → 이미지 → 영상 조립 → 패키지/썸네일까지 하나의 job으로 남은 실행 로그와 산출물이다. |

이 감사에서 확인한 것은 코드 배선과 일부 독립 E2E까지다. 통합 E2E는 **미확인**이다.

## 3. 목표 1 — 3종 이미지 라우팅

### 3.1 씬 타입 라우터

파일: `backend/fastapi-workers/app/workers/script_worker.py`

```python
SCENE_TYPES = {"general", "metric", "graph", "diagram", "text"}

def _scene_type_source_text(scene: dict) -> str:
    fields = ("title", "content", "text", "prompt_ko", "prompt_en", "visual_intent")
    return "\n".join(str(scene.get(field) or "") for field in fields).lower()

def _classify_scene_types(sections: list[dict]) -> list[dict]:
    classified: list[dict] = []
    for original in sections:
        scene = dict(original)
        scene_type, selection_reason = _classify_scene_type(scene)
        if scene_type not in SCENE_TYPES:
            raise ValueError(f"지원하지 않는 scene_type: {scene_type}")
        scene["scene_type"] = scene_type
        scene["selection_reason"] = selection_reason
        classified.append(scene)
    return classified
```

확정 사항:

- 반환 라벨은 `general`, `metric`, `graph`, `diagram`, `text` 다섯 가지다.
- 입력은 제목, 본문, 프롬프트, 시각 의도이며 씬 ID는 참조하지 않는다. 과거의 “씬 ID 숫자를 수치로 오인”한 종류의 버그는 이 함수의 현재 입력에서는 재발하지 않는다.
- 기사 캡처형은 이 enum에 없다. 즉 사용자가 정의한 ② 기사형은 `scene_type` 분류기가 아니라 별도 evidence 경로다.

### 3.2 기사 캡처형은 별도 경로

파일: `backend/fastapi-workers/app/services/article/evidence_planner.py`

```python
scene["visual_kind"] = "article_scene"
scene["visual_type"] = "article_evidence"
scene["article_capture"] = capture.model_dump(mode="json")
scene["emphasis_plan"] = plan.model_dump(mode="json")
scene["key_phrase"] = capture.key_phrase or ""
scene["source_credit"] = f"출처: {capture.publisher} · {capture.published_at or ''}".rstrip(" ·")
```

`ImagesWorker`는 해당 타입을 탐지해 생성 모델을 우회한다.

파일: `backend/fastapi-workers/app/workers/images_worker.py`

```python
def _article_evidence_path(scene: dict) -> str:
    capture = scene.get("article_capture")
    kind = str(scene.get("visual_kind") or scene.get("visual_type") or "")
    if kind not in {"article_evidence", "article_scene"} or not isinstance(capture, dict):
        return ""
    return str(capture.get("local_path") or scene.get("image_path") or "")

if evidence_path:
    generated.append({
        **scene,
        "image_path": evidence_path,
        "generation_method": "article_evidence",
        "generation_cost_krw": 0,
        "use_kling": False,
        "quality_score": 100,
    })
    continue
```

판정: 기사 캡처형은 실제 production 배선이 있다. Gemini/Fal과 Kling을 명시적으로 우회한다.

### 3.3 정보형 V5는 production에 연결됨

파일: `backend/fastapi-workers/app/workers/images_worker.py`

```python
if scenes_meta and all(scene.get("scene_type") for scene in scenes_meta):
    scenes_meta = attach_v5_scene_contracts(scenes_meta)
```

V5 검증 수치가 있으면 후처리에서 물리 표면 합성으로 전달된다.

```python
if isinstance(scene.get("v5_render_contract"), dict):
    if scene.get("v5_verified_overlays") or scene.get("market_chart"):
        from app.v5.overlay.verified_surface_payload import market_chart_from_verified_scene
        chart = market_chart_from_verified_scene(scene)
        if chart is None:
            raise ValueError("V5 정보형 씬에는 검증된 물리 표면 데이터가 필요합니다")
        scene["market_chart"] = chart
        self._apply_info_surface_plan(scene, img_path)
    return
```

검증 데이터 계약은 `verified_facts` 원문과 `facts[n]` source reference를 연결한다.

파일: `backend/fastapi-workers/app/v5/overlay/verified_surface_payload.py`

```python
rendered_facts = validated_facts_from_verified_scene(scene)
source_index = int(rendered.source_ref.removeprefix("facts[").removesuffix("]"))
raw_facts = scene.get("verified_facts")
if not isinstance(raw_facts, list) or source_index >= len(raw_facts):
    raise ValueError("검증 사실 원문을 찾을 수 없습니다")

return {
    "verified": True,
    "source_ref": rendered.source_ref,
    "source_url": str(raw.get("source_url") or ""),
    "source_date": str(raw.get("published_at") or raw.get("source_date") or "")[:10],
    "hero_stat": {
        "headline_value": rendered.value,
        "headline_unit_label": rendered.label,
        "source_refs": [rendered.source_ref],
    },
}
```

판정: 과거의 “V5가 benchmark/pilot 전용” 정황은 현재 main에는 맞지 않는다. 다만 아래 OpenCV 충돌 때문에 사용자 승인 정책의 정본 경로로 인정할 수는 없다.

### 3.4 OpenCV 광역 합성 경로가 아직 활성화됨 — 정책 충돌

파일: `backend/fastapi-workers/app/workers/images_worker.py`

```python
from app.services.info_surface.warp_compositor import composite_planar, render_data_cutaway
...
result = composite_planar(
    Image.open(source_path).convert("RGBA"),
    chart,
    plan,
    detection,
    content_override=diagram,
)
```

`composite_planar` 정의는 `backend/fastapi-workers/app/services/info_surface/warp_compositor.py`에 있다. 따라서 OpenCV 광역 합성은 격리·비활성 상태가 아니다. “폐기 유지, 추가 개발 금지” 요구와 충돌한다.

### 3.5 승인 archetype 자산

코드상 `earnings_stage`는 렌더 차단이다.

파일: `backend/fastapi-workers/app/v5/providers/router.py`

```python
RENDER_BLOCKED_ARCHETYPES = frozenset({"earnings_stage"})
```

실측 및 기존 감사 기록상 승인 사용 가능은 10개, 차단은 1개다. 승인 파일과 SHA-256 앞 12자는 다음 문서에 정리돼 있으며, 감사 시 해시를 재계산했다.

- `docs/V5_EMERGENCY_ARCHETYPE_PATH_AUDIT_2026-08-02.md` 79~94행
- 승인 파일 루트: `backend/fastapi-workers/out/v5_archetype_validation/`

따라서 과거의 “통과 11/전체 12”는 현재 코드·파일 기준의 개수와 일치하지 않는 과거 표기다.

### 3.6 기사 캡처 구현과 독립 E2E

주요 파일:

- `backend/fastapi-workers/app/services/evidence_capture.py`
- `backend/fastapi-workers/app/services/annotate.py`
- `backend/fastapi-workers/app/services/article/frame_editor.py`
- `backend/fastapi-workers/app/services/verbatim_guard.py`

`annotate.py`는 `underline`, `ellipse`, `rect`, `dashed_ellipse`, `arrow`, `highlighter`, `callout_block`, `render_annotations` 프리미티브를 제공한다.

Playwright와 한글 폰트는 Docker image에 설치된다.

```dockerfile
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-nanum \
    fontconfig \
    && fc-cache -fv
...
RUN ... && playwright install chromium
```

`requirements.txt`에는 `playwright==1.49.1`이 명시돼 있다.

독립 E2E 증거:

- 보고서: `backend/fastapi-workers/out/article_capture_pilot_v4/jobs/20260802/evidence/article_d557e25890a6480c_pilot_report.json`
- 원본/강조 PNG: 같은 디렉터리의 `article_d557e25890a6480c.png`, `article_d557e25890a6480c_emphasized.png`
- 보고서는 연합뉴스 URL, `capture_mode=dom`, `bbox_source=dom_range`, quote/key phrase bbox, annotation 목록, SHA-256을 기록하며 `status=passed`다.
- 사용자가 직접 좌표를 준 업로드 경로도 존재한다: `POST /workers/evidence/capture-upload` (`app/main.py`). 관련 독립 산출물은 `backend/fastapi-workers/out/article_capture_upload_endpoint_pilot/`에 있다.

주의: 숫자 verbatim guard는 존재하지만 불일치 시 전체 작업을 hard reject하지 않는다.

```python
numeric_gate = validate_verbatim(sentence, {"verified_facts": [fact]})
if required_numbers and not numeric_gate.passed:
    continue
```

즉 현재 동작은 후보를 건너뛰는 방식이며, 요구된 “무음 삭제가 아닌 게이트 반려”는 아니다.

## 4. 목표 2 — 인트로 Fal/Kling 모션

### 4.1 현재 시간 예산과 확정할 정책

파일: `backend/fastapi-workers/app/config.py`

```python
INTRO_MOTION_SECONDS_SHORT = float(os.getenv("INTRO_MOTION_SECONDS_SHORT", "40"))
INTRO_MOTION_SECONDS_LONG = float(os.getenv("INTRO_MOTION_SECONDS_LONG", "60"))
INTRO_MOTION_SHORT_THRESHOLD = float(os.getenv("INTRO_MOTION_SHORT_THRESHOLD", "660"))
```

현재 값은 10분 이하 40초, 10분 초과 60초다. 사용자 문서가 요구한 정본은 **10분 미만 45초 / 10분 이상 60초**로 확정하고, 다음 작업 지시서에서 config·테스트·preflight를 함께 바꿔야 한다.

`min(60, total_duration)` 방식은 현재 사용하지 않는다. `intro_motion.py`가 길이 구간과 씬 길이로 실제 초 단위 선택을 한다.

```python
def intro_motion_budget_seconds(total_duration, *, short_seconds, long_seconds, short_threshold):
    if total_duration <= 0:
        return 0.0
    return float(short_seconds if total_duration <= short_threshold else long_seconds)

def select_intro_motion_scene_indices(...):
    ...
    for index, scene in enumerate(scene_list):
        slice_seconds = min(max(1.0, min(float(clip_seconds), 5.0)), scene_duration_seconds(scene))
        if slice_seconds <= 0 or actual + slice_seconds > target + 1e-6:
            break
        selected.add(index)
```

### 4.2 실제 호출 체인

Kling 선택 결과는 견적 전용이 아니다. `LongformWorker`가 선택하고 같은 실행에서 video provider를 호출한다.

```python
intro_kling_indices, intro_motion_target, intro_motion_actual = _select_intro_kling_scenes(
    scenes, total_duration, max_clips_cap
)
...
asset = video_provider.generate(
    prompt=prompt,
    duration=motion_duration,
    output_path=clip_path,
    image_path=img_path,
    image_url=start_image_url,
    negative_prompt=negative_prompt,
    fal_only=True,
)
```

실제 image-to-video provider는 `animate_image()`라는 이름이 아니라 `KlingVideoProvider.generate()` 및 `_generate_fal_api()`다.

```python
model_id = "fal-ai/kling-video/v2.6/pro/image-to-video" if image_url else "fal-ai/kling-video/v1.6/pro/text-to-video"
payload = {
    "prompt": prompt,
    "duration": "10" if int(duration) >= 10 else "5",
    "generate_audio": False,
}
if image_url:
    payload["start_image_url"] = image_url
```

`start_image_url`와 `generate_audio=False`의 코드 근거는 있다. 다만 이를 실제 OpenAPI schema로 검증한 파일 또는 실행 로그는 찾지 못했다. B7의 schema 검증 상태는 **미검증**이다.

### 4.3 단일 씬 실제 MP4 증거

다음은 독립 motion pilot이다.

- MP4: `backend/fastapi-workers/out/v5_motion_pilot/general_port_walking_intro_20260801/general_port_walking_intro.mp4`
- request audit: 같은 디렉터리의 `_request_audit.json`
- audit 내용: Fal endpoint/model, `generate_audio=false`, 5초, Fal request ID, 생성 MP4 bytes, static fact overlay가 없는 일반 씬임을 기록한다.

이 증거는 Fal 호출 자체가 실제로 성공했음을 보여 준다. 그러나 여러 씬이 들어간 production longform의 0~45/60초 프레임 변화율 측정 로그는 없다. 따라서 통합 E2E 증거는 아니다.

### 4.4 차단, 폴백, 남은 결함

기사 캡처와 V5 검증 사실 오버레이는 motion 후보에서 제외된다.

```python
def _should_request_kling_for_scene(scene, *, selected_for_intro_motion, has_manual_kling_selection):
    if not selected_for_intro_motion:
        return False
    if _article_capture_for_scene(scene) or _has_v5_verified_fact_overlay(scene):
        return False
    return bool(scene.get("use_kling")) if has_manual_kling_selection else True
```

실패 시 정지 이미지 MP4로 폴백하고, 실제 motion delivery가 계획의 75% 미만이면 최종 영상을 거부한다. 따라서 모션 실패는 완전히 무음은 아니다.

그러나 다음 문제는 남아 있다.

1. `GET https://api.fal.ai/v1/account/billing` 사전 체크가 남아 있다.
2. 403을 “추론 키 사용 가능”으로 바꾸는 우회가 있다.
3. 실제 실행은 `build_kling_motion_prompt(scene.get("motion_type"))`만 사용한다. `emotion_tag`, `character_action`, `edit_marker`를 반영하는 `_build_kling_motion_prompt(scene)`는 존재하지만 호출되지 않는다.
4. 성공한 Kling만 `record_cost(job_id, "kling")`를 호출한다. 실패했지만 공급자가 과금했을 가능성까지 원장에 남기는 구조는 아니다.

## 5. 목표 3 — 자동 썸네일 추천

### 5.1 실제 renderer와 포맷 분리

현재 ThumbnailV2 renderer는 있다.

파일: `backend/fastapi-workers/app/services/thumbnail/v2/compose.py`

```python
aspect = "9:16" if str(format_name).lower() == "shorts" else "16:9"
...
image = template.render(..., aspect)
variant_path = target.with_name(f"{target.stem}_v{variant_index + 1}{target.suffix or '.png'}")
image.convert("RGB").save(variant_path, "PNG", optimize=True)
```

템플릿 크기 역시 별도다.

```python
SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
```

현재 세 creative preset은 `person_led`, `mascot_led`, `chart_led`다. 따라서 과거의 “유형 C builder 없음”은 현재 main에는 맞지 않는다. `chart_led`는 `chart_warning` template으로 배선된다.

### 5.2 실사 인물 처리와 라이선스 게이트

실제 registry 이름은 `person_asset_registry`가 아니라 Spring의 `PersonAsset`, `PersonPhoto` 엔터티 및 repository다. 자동 선택은 `ThumbnailPersonResolver`가 담당한다.

파일: `backend/fastapi-workers/app/services/thumbnail/person_compositor.py`

```python
def validate_photo(photo: dict[str, Any]) -> None:
    license_type = str(photo.get("license_type") or "UNKNOWN").upper()
    if license_type not in ALLOWED_LICENSES:
        raise PhotoLicenseError(f"PHOTO_LICENSE_MISSING: {photo.get('photo_id') or 'unknown'}")
    if not bool(photo.get("approved")):
        raise PhotoLicenseError(f"PHOTO_LICENSE_MISSING: {photo.get('photo_id') or 'unknown'} is not approved")
```

승인된 사진은 local rembg로 cutout을 만들고, 원본 인물 픽셀에는 생성형 변형을 하지 않는다.

```python
from rembg import new_session, remove
...
result = remove(original.convert("RGBA"), session=session, post_process_mask=True)
result.save(output, "PNG")
```

이후 처리는 alpha mask 기반 red glow, white outline, drop shadow다. 인물 썸네일 경로 자체에서 생성형 이미지 API를 호출하는 코드는 확인되지 않았다. 단, 저장소 전체에 다른 용도의 image provider가 존재하므로 “저장소 전체 API 호출 0건”으로 일반화하면 안 된다.

인물 미등록이면 planner는 mascot template 또는 chart template으로 내려갈 수 있다. 다만 mascot asset도 없고 유효한 씬 후보도 없을 때의 성공적 단독 마스코트 폴백은 보장되지 않으며 실패할 수 있다.

### 5.3 데이터 추적성과 실제 산출 증거

ThumbnailV2 brief는 `source_ref`를 검증한다. 이 때문에 사실 기반 badge/evidence는 검증 facts와 연결될 수 있다. 반면 “인트로 훅/클라이맥스/결론”의 서사 위치를 명시적으로 선택하는 별도 selector는 찾지 못했다. 현재는 `source_scene_ids`, 후보 씬 점수, `facts[0]` 중심의 계획이다.

로컬 PNG와 provenance는 있다.

- `.artifacts/thumbnail_job49_provenance.json`
- `.artifacts/thumbnail_job49_mascot_clean_provenance.json`
- `.artifacts/thumbnail_job49_applied.png` 등

하지만 Spring `JobService → FastAPI → longform PNG + shorts PNG`를 한 job에서 실행한 로그와 두 산출물은 확인되지 않았다. 이 문서의 E2E 기준에서는 “적격 통합 증거 0건”이다.

## 6. 전체 production 통합

### 6.1 현재 호출 흐름

```text
Temporal Workflow
  → ScriptService / ScriptWorker
      → scene_type 분류
  → ImagesService
      → POST /workers/images/generate
          ├─ Article Evidence Planner: 기사 PNG 직접 사용
          └─ V5 계약: Gemini 배경 + 검증 수치 후합성
  → LongformService
      → POST /workers/longform/generate
          ├─ 일반 인트로 씬만 Fal/Kling
          └─ 기사/검증 정보형은 정지 이미지
  → JobService.generateYoutubePackage
      → metadata + longform/shorts thumbnail
```

Spring workflow의 이미지 생성 activity는 `ImagesService.generate(jobId, "AUTO")`를 호출하고, 이것이 FastAPI `/workers/images/generate`로 이어진다. Longform은 `/workers/longform/generate`로 이어진다.

### 6.2 무음 실패와 mock publish

파일: `backend/spring-app/src/main/java/com/pipeline/video/service/JobService.java`

```java
try {
    longformMeta = fastApiClient.generateYoutubeMetadata(scriptText, false);
} catch (Exception e) {
    log.error("롱폼 유튜브 메타데이터 생성 실패: {}", e.getMessage());
}
...
try {
    longformThumbnailResult = fastApiClient.generateThumbnailImage(...);
} catch (Exception e) {
    log.error("롱폼 썸네일 생성 실패: {}", e.getMessage());
}
```

예외는 기록만 하고 패키지 생성은 계속된다. 요구된 게이트 노출/실패 전파가 아니다.

```java
String mockYoutubeUrl = "https://youtu.be/mock_youtube_video_" + jobId + "_" + System.currentTimeMillis();
job.setYoutubeUrl(mockYoutubeUrl);
job.setStatus(JobStatus.PUBLISHED);
```

`publishVideo()`는 실제 publish 결과를 구분하지 않고 mock URL을 저장한다.

### 6.3 비용 정책 충돌

FastAPI 설정은 하나의 4만원 상한만 사용한다.

```python
MAX_BUDGET_PER_VIDEO_KRW = min(40_000, int(os.getenv("MAX_BUDGET_PER_VIDEO_KRW", "40000")))
```

20분 이상 8만원 상한은 없다. 또한 예산 preflight는 Pro→Flash 강등을 수행한다.

```python
if estimated > max_budget and pro_count:
    ...
    actions.append(f"pro_scenes:{pro_count}->{affordable_pro}")
    pro_count = affordable_pro
```

비용 원장은 둘로 분리돼 있다.

- FastAPI: `/app/data/jobs/{job_id}/cost_ledger.json`
- Spring: DB table `cost_ledger` (`CostLedger` entity)

이 둘을 하나의 비용 한도로 합산하는 코드와 `PricingConfig.java`는 확인하지 못했다.

### 6.4 keyword와 autonomy

`CreateJobRequest`와 `VideoJob`에 `keyword` 필드가 있고, `ScriptService`는 빈 keyword를 거부한다. 하지만 “입력 키워드가 뉴스 빈도/YouTube 지표보다 절대 우선”을 API 경계부터 강제하는 전용 정책 필드는 확인하지 못했다.

AUT0/GUIDED/MANUAL 분기는 일반 workflow gate에 있다. 그러나 article evidence의 `bbox_source=ocr_estimate`를 감지하여 AUTO를 GUIDED 승인으로 강제하는 코드는 확인하지 못했다.

## 7. 다음 작업 지시서에 반영할 우선순위

### WP-정책-0: 충돌 제거

1. OpenCV `composite_planar`를 폐기하거나, 사용자 승인으로 예외 처리할지 확정한다.
2. intro budget을 45초/60초로 고정한다.
3. Fal billing precheck와 403 usable 우회를 제거한다.
4. 이미지 모델 정책을 Nano Banana Pro 단일로 강제하고 Flash/Hybrid/자동 강등을 제거한다.

### WP-통합-1: 비용·오류 게이트

1. 이미지, Kling, 썸네일 비용을 단일 원장으로 합친다.
2. 20분 미만 4만원, 20분 이상 8만원 상한을 강제한다.
3. package/thumbnail 오류를 job 실패 또는 승인 게이트로 전파한다.
4. mock publish URL을 제거하고 실제 publish 미구현 상태를 명시적 실패로 바꾼다.

### WP-기능-2: 세 목표 완주 E2E

1. 한 job에서 일반형·기사형·정보형 씬을 혼합한다.
2. 정보형/기사형이 Kling에서 제외되고, 일반 인트로 씬만 45/60초 예산 안에서 motion 처리되는지 기록한다.
3. longform과 shorts PNG를 실제로 생성한다.
4. job 로그, 비용 원장, 최종 MP4, 프레임 변화율, 두 썸네일 경로를 하나의 증적 bundle로 남긴다.

## 8. 감사 시 확인한 주요 증적 경로

| 구분 | 경로 |
|---|---|
| 기사 DOM capture E2E 보고서 | `backend/fastapi-workers/out/article_capture_pilot_v4/jobs/20260802/evidence/article_d557e25890a6480c_pilot_report.json` |
| 기사 사용자 업로드 E2E | `backend/fastapi-workers/out/article_capture_upload_endpoint_pilot/endpoint_result.json` |
| V5 ImagesWorker dry-run | `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/images_worker_v5_dry_run_20260801.json` |
| 단일 Kling motion MP4 | `backend/fastapi-workers/out/v5_motion_pilot/general_port_walking_intro_20260801/general_port_walking_intro.mp4` |
| Kling request audit | `backend/fastapi-workers/out/v5_motion_pilot/general_port_walking_intro_20260801/_request_audit.json` |
| 썸네일 provenance | `.artifacts/thumbnail_job49_provenance.json` |
| archetype 자산 감사 | `docs/V5_EMERGENCY_ARCHETYPE_PATH_AUDIT_2026-08-02.md` |


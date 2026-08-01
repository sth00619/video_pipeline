# 현재 구현 현황 감사: 썸네일 자동 생성과 유튜브 메타데이터

- 조사일: 2026-07-31
- 기준 커밋: `main @ 34bfb8e` (`대본의 스타일 맞추기`)
- 범위: `backend/fastapi-workers`, `backend/spring-app`
- 방법: 코드 경로 추적, 저장소 산출물/요청 원장 확인, 관련 테스트 실행
- 변경: 이 문서는 조사 결과만 기록하며, 기존 구현 파일은 수정하지 않았다.

> 주의: 조사 시점 작업 트리에는 V5 관련 코드·산출물을 포함한 미커밋 변경이 106개 있었다. 아래 표기에서 **main**은 기준 커밋에 있는 코드, **로컬 미커밋**은 현재 작업 폴더에만 있는 코드를 뜻한다. 두 상태를 혼동하면 V5가 운영 영상 경로에 연결된 것으로 잘못 판단할 수 있다.

## 1. 결론 요약

| 영역 | 판정 | 근거 |
|---|---|---|
| 장면 기반 썸네일 | 구현됨 | 최종 영상 장면 후보를 받아 Pillow 기반으로 longform/shorts 썸네일을 렌더한다. |
| 썸네일 서사 계약 | 구현됨 | `ThumbnailNarrativePlan`, `OverlaySlot`, `DataOverlayPlan`, `SceneEditorialOverlayPlan`이 Pydantic 모델로 존재한다. |
| 실제 자동 썸네일 실행 증거 | 없음 | 저장소 및 `pipeline-autostart.log`에 실제 자동 썸네일 PNG와 해당 실행 로그가 없다. 테스트의 PNG는 임시 디렉터리에 생성된다. |
| 메타데이터 생성 API | 구현됨 | 제목 3개, 설명, 태그를 생성하는 FastAPI 엔드포인트가 Spring의 자동 패키지 생성 경로에 연결돼 있다. |
| 실제 YouTube 업로드 반영 | 미구현 | `publishVideo()`는 실제 업로드 대신 mock URL을 기록한다. |
| V5 장면 생성 | 벤치마크/파일럿 경로만 존재 | 운영 `ImagesWorker`는 기존 `app.pipeline.scene_director.SceneSpec`만 사용하며, V5 `SceneSpec`을 호출하지 않는다. |
| A/B/C 후보 선택 | 미구현 | 현재 builder는 수치 사실이 있으면 P2 사실형, 없으면 P3 질문형만 만든다. 결과형(C) 선택 로직은 없다. |

## 2. 검증 실행

다음 테스트는 이 조사에서 실제 실행해 통과했다.

```text
python -m pytest -q \
  tests/test_thumbnail_v2.py \
  tests/test_thumbnail_narrative_plan.py \
  tests/test_thumbnail_generator.py \
  tests/test_data_overlay_plan.py \
  tests/test_scene_editorial_plan.py \
  tests/test_editorial_overlay.py

........................                                                 [100%]
24 passed in 11.89s
```

이 결과는 로컬 렌더링 및 계약 검증을 보장할 뿐, 실제 Spring/FastAPI 배포 환경에서의 자동 패키지 생성이나 YouTube 업로드 성공을 증명하지는 않는다.

---

## 3. 썸네일 자동 생성: 실제 실행 경로

### 3.1 FastAPI 진입점

파일: `backend/fastapi-workers/app/main.py` — `ThumbnailRequest`, `_render_thumbnail_request`, `POST /workers/youtube/thumbnail`

```python
class ThumbnailRequest(BaseModel):
    job_id: int
    title: str
    format: str  # "longform" | "shorts"
    output_path: str
    character_image_path: Optional[str] = None
    character_style_prompt: Optional[str] = None
    lora_model_id: Optional[str] = None
    lora_trigger_word: Optional[str] = None
    lora_scale: Optional[float] = 1.0
    scene_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    thumbnail_brief: Dict[str, Any] = Field(default_factory=dict)
    character_identity: Dict[str, Any] = Field(default_factory=dict)
    person_photos: List[Dict[str, Any]] = Field(default_factory=list)
    watermark_path: Optional[str] = None
    variants: int = 3
    reference_style_profile: str = "black_han_sans_v1"
    preset: Optional[Literal["person_led", "mascot_led", "chart_led"]] = None


def _render_thumbnail_request(req: ThumbnailRequest):
    try:
        if req.scene_candidates:
            from app.services.thumbnail import ThumbnailGenerator
            return ThumbnailGenerator().render(
                job_id=req.job_id,
                format_name=req.format,
                output_path=req.output_path,
                candidates=req.scene_candidates,
                brief=req.thumbnail_brief,
                character_asset_path=req.character_image_path,
                character_identity=req.character_identity,
                person_photos=req.person_photos,
                watermark_path=req.watermark_path,
                variants=req.variants,
                reference_style_profile=req.reference_style_profile,
                forced_preset=req.preset,
            )

        # 이전 조립 manifest가 없는 구 작업의 호환 fallback
        provider = get_image_provider()
        prompt = f"YouTube Video Thumbnail: {req.title}. {theme_style}"
        width, height = (1080, 1920) if req.format == "shorts" else (1280, 720)
        provider.generate_image(prompt=prompt, output_path=req.output_path, ...)
        return {"status": "ok", "mode": "ai_fallback", "output_path": req.output_path, "variants": []}
    except Exception as e:
        # 계약 위반은 422, 그 밖의 렌더 실패는 500
        ...


@app.post("/workers/youtube/thumbnail")
def generate_thumbnail(req: ThumbnailRequest):
    return _render_thumbnail_request(req)


@app.post("/workers/thumbnail/regenerate")
def regenerate_thumbnail(req: ThumbnailRequest):
    if not req.scene_candidates:
        raise HTTPException(status_code=422, detail={"code": "THUMBNAIL_SOURCE_NOT_IN_VIDEO"})
    return _render_thumbnail_request(req)
```

핵심 판정:

- 정상 경로는 `scene_candidates`가 있을 때만 사용된다. 이 경로는 생성 모델로 별도 포스터를 만들지 않고 이미 최종 영상에 사용된 장면을 사용한다.
- 후보가 없는 legacy fallback은 `req.title`을 이미지 모델 프롬프트에 직접 넣는다. 따라서 “모든 읽히는 문자는 결정론적 렌더러만 그린다”는 전역 규칙에는 예외가 있다.
- 재생성 엔드포인트는 final-video 후보가 없으면 fail-closed한다.

### 3.2 썸네일 렌더러와 비율 분기

파일: `backend/fastapi-workers/app/services/thumbnail/generator.py`

```python
LONGFORM_SIZE = (1280, 720)
SHORTS_SIZE = (1080, 1920)


def output_size(format_name: str) -> tuple[int, int]:
    return SHORTS_SIZE if str(format_name).lower() == "shorts" else LONGFORM_SIZE


class ThumbnailGenerator:
    def render(self, *, job_id: int, format_name: str, output_path: str,
               candidates: list[dict[str, Any]], brief: dict[str, Any] | None = None,
               character_asset_path: str | None = None,
               character_identity: dict[str, Any] | None = None,
               person_photos: list[dict[str, Any]] | None = None,
               watermark_path: str | None = None, variants: int = 3,
               reference_style_profile: str = "black_han_sans_v1",
               forced_preset: str | None = None) -> dict[str, Any]:
        brief = brief or {}
        if bool(runtime_config.value("thumbnail_v2_enabled")) and brief.get("template"):
            from .v2.compose import ThumbnailV2Composer
            # 승인 인물/채널 마스코트 여부에 따라 v2 계약을 조정한다.
            ...
            return ThumbnailV2Composer().render(...)
        # 기존 scene-backed Pillow renderer 경로
        ...
```

파일: `backend/fastapi-workers/app/services/thumbnail/v2/compose.py`

```python
class ThumbnailV2Composer:
    def render(self, *, output_path: str, format_name: str,
               candidates: list[dict[str, Any]], brief: dict[str, Any],
               person_photos: list[dict[str, Any]] | None = None,
               mascot_path: str | None = None, watermark_path: str | None = None,
               verified_facts: list[dict] | None = None, narration: str = "",
               variants: int = 3, reference_style_profile: str = "black_han_sans_v1",
               forced_preset: str | None = None) -> dict[str, Any]:
        contract = ThumbnailBriefV2.model_validate(brief)
        raw_narrative = brief.get("narrative_plan")
        if isinstance(raw_narrative, dict):
            narrative = ThumbnailNarrativePlan.model_validate(raw_narrative)
            contract.editorial_overlays = narrative.overlays
            contract.pattern_id = narrative.pattern_id
        errors = validate_brief(contract, verified_facts, narration)
        if errors:
            raise ValueError("BRIEF_VALIDATION_FAILED: " + "; ".join(errors))
        sources = choose_many(candidates, contract.template, limit=3,
                              preferred_scene_ids=preferred)
        if not sources:
            raise ValueError("THUMBNAIL_SOURCE_NOT_IN_VIDEO")
        aspect = "9:16" if str(format_name).lower() == "shorts" else "16:9"
        ...
        image.convert("RGB").save(variant_path, "PNG", optimize=True)
        ...
```

파일: `backend/fastapi-workers/app/services/thumbnail/v2/templates/base.py`

```python
SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920)}

class BaseTemplate:
    def background(self, source: dict[str, Any], size: tuple[int, int]) -> Image.Image:
        path = Path(str(source.get("image_path") or source.get("path") or ""))
        if not path.is_file():
            raise FileNotFoundError("THUMBNAIL_SOURCE_NOT_IN_VIDEO")
        with Image.open(path) as loaded:
            return ImageOps.fit(loaded.convert("RGBA"), size, Image.Resampling.LANCZOS)
```

정리:

- longform과 shorts는 각각 Spring에서 별도 호출하고, 렌더러도 별도 캔버스 비율을 사용한다.
- `ThumbnailV2Composer`는 후보 장면이 파일로 실제 존재하지 않으면 `THUMBNAIL_SOURCE_NOT_IN_VIDEO`으로 실패한다.
- 읽히는 텍스트·배지·말풍선은 V2 template 및 `editorial_overlay`의 Pillow 렌더러에서 그린다.

### 3.3 썸네일 서사 계약 전체

파일: `backend/fastapi-workers/app/services/thumbnail/v2/narrative_plan.py`

```python
def build_from_video_manifest(*, keyword: str, sections: list[dict],
                              verified_facts: list[dict]) -> "ThumbnailNarrativePlan":
    source_scene_ids: list[str] = []
    for index, section in enumerate(sections):
        phase = str(section.get("phase") or section.get("section") or "")
        if index == 0 or phase in {"data", "scenario", "action", "conclusion"}:
            source_scene_ids.append(str(section.get("scene_id") or section.get("id") or index))
        if len(source_scene_ids) == 3:
            break
    source_scene_ids = source_scene_ids or ["0"]

    fact_index = next((index for index, fact in enumerate(verified_facts or [])
                       if any(char.isdigit() for char in str(
                           fact.get("figure") or fact.get("value") or ""))), None)
    if fact_index is not None:
        fact = verified_facts[fact_index]
        value = str(fact.get("figure") or fact.get("value") or "").strip()[:24]
        reference = f"facts[{fact_index}]"
        return ThumbnailNarrativePlan(
            pattern_id="P2", candidate_kind="fact", source_scene_ids=source_scene_ids,
            decision_hook=CopyClaim(text=hook, claim_type="derived_hook", source_refs=[reference]),
            fact_anchor=CopyClaim(text=value, claim_type="verbatim_fact", source_refs=[reference]),
            overlays=[OverlaySlot(kind="metaphor_label", text=value,
                claim_type="verbatim_fact", source_refs=[reference], anchor="target",
                target_bbox=(.48, .18, .28, .16), text_style="outline", tone="warning")],
            rationale="검증된 수치를 장면의 데이터 표면에만 배치해 영상 근거와 추천 썸네일을 연결합니다.",
        )
    return ThumbnailNarrativePlan(
        pattern_id="P3", candidate_kind="question", source_scene_ids=source_scene_ids,
        decision_hook=CopyClaim(text=hook, claim_type="derived_hook",
                                source_refs=[f"scene:{source_scene_ids[0]}"]),
        overlays=[OverlaySlot(kind="burst", text="지금 확인할 변화", claim_type="derived_hook",
            source_refs=[f"scene:{source_scene_ids[0]}"], anchor="upper_left",
            text_style="gradient", tone="warning")],
        rationale="수치 근거가 없는 경우에는 사실처럼 보이는 숫자 대신 질문형 훅으로 안전하게 호기심을 만듭니다.",
    )


class ThumbnailNarrativePlan(BaseModel):
    schema_version: Literal[1] = 1
    pattern_id: Literal["P1", "P2", "P3", "P4", "P5", "P6", "P8"]
    candidate_kind: Literal["question", "fact", "result"]
    source_scene_ids: list[str] = Field(min_length=1, max_length=3)
    decision_hook: CopyClaim
    fact_anchor: CopyClaim | None = None
    overlays: list[OverlaySlot] = Field(default_factory=list, max_length=2)
    rationale: str = Field(min_length=12, max_length=240)

    @model_validator(mode="after")
    def candidate_grammar(self):
        if self.candidate_kind == "question":
            if not any(item.kind == "burst" and item.text_style == "gradient"
                       for item in self.overlays):
                raise ValueError("question candidate requires gradient burst")
        if self.candidate_kind == "fact" and not self.fact_anchor:
            raise ValueError("fact candidate requires fact_anchor")
        if self.candidate_kind == "result" and sum(
            bool(any(char.isdigit() for char in item.text)) for item in self.overlays
        ) > 1:
            raise ValueError("result candidate permits at most one numeric overlay")
        return self
```

현재 선택 로직의 한계는 명확하다.

1. P2 사실형과 P3 질문형만 실제로 생성한다.
2. `candidate_kind="result"`은 타입에는 있으나 builder가 만들지 않는다.
3. `port_emergency` 등 scene archetype이나 대본의 사건 단계로 A/B/C를 선택하지 않는다.

### 3.4 오버레이·데이터 계약 전체

파일: `backend/fastapi-workers/app/services/overlay/editorial_overlay.py`

```python
class OverlaySlot(BaseModel):
    kind: OverlayKind
    text: str = Field(min_length=1, max_length=48)
    claim_type: Literal["reaction", "derived_hook", "verbatim_fact"] = "reaction"
    source_refs: list[str] = Field(default_factory=list)
    anchor: Literal["upper_left", "upper_right", "subject_gaze", "subject_hand",
                    "target", "lower_left"] = "upper_left"
    target_bbox: tuple[float, float, float, float] | None = None
    text_style: Literal["solid", "outline", "gradient"] = "solid"
    tone: Literal["neutral", "danger", "benefit", "warning"] = "neutral"
    max_area_ratio: float = Field(default=.18, ge=.04, le=.18)
    spans: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contract(self):
        if self.claim_type != "reaction" and not self.source_refs:
            raise ValueError("grounded overlay requires source_refs")
        if self.kind in {"cloud", "metaphor_label", "article_callout", "chalk_note"} and not self.target_bbox:
            raise ValueError("target-bound overlay requires target_bbox")
        if self.text_style == "gradient" and not (
            self.kind == "burst" and self.claim_type == "derived_hook"
        ):
            raise ValueError("gradient is reserved for question burst overlays")
        return self
```

파일: `backend/fastapi-workers/app/services/overlay/plans.py`

```python
class CopyClaim(BaseModel):
    text: str = Field(min_length=2, max_length=24)
    claim_type: Literal["reaction", "derived_hook", "verbatim_fact"]
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def requires_source_when_grounded(self):
        if self.claim_type != "reaction" and not self.source_refs:
            raise ValueError("grounded copy requires source_refs")
        return self


class DataOverlayPlan(BaseModel):
    chart_kind: Literal["trend", "change", "composition", "comparison"]
    primary_metric: str = Field(min_length=1)
    unit: str = Field(min_length=1, max_length=12)
    source_refs: list[str] = Field(min_length=1)
    comparison_basis: str | None = None
    focus_target: Literal["latest_point", "largest_slice", "larger_bar"]
    callout: CopyClaim | None = None
    callout_anchor: Literal["target", "upper_left", "lower_right"] = "target"
    diegetic: list[DiegeticNumberPlan] = Field(default_factory=list, max_length=2)
    subtitle_emphasis_ref: str | None = None
    date_stamp_ref: str | None = None

    @model_validator(mode="after")
    def no_repeated_metric_in_callout(self):
        if self.callout and re.search(r"\\d", self.callout.text):
            raise ValueError("data callout must not restate a numeric value")
        if self.chart_kind == "comparison" and not self.comparison_basis:
            raise ValueError("comparison requires a common comparison_basis")
        return self


class SceneEditorialOverlayPlan(BaseModel):
    section: Literal["intro", "background", "scenario", "action", "conclusion"]
    message_role: Literal["hook", "reaction", "cause", "decision", "takeaway", "evidence_quote"]
    overlay: OverlaySlot
    target_id: str | None = None
    subtitle_text: str = ""
```

파일: `backend/fastapi-workers/app/workers/longform_worker.py`

```python
def _render_typed_editorial_overlay(scene: dict, clip_path: str, temp_dir: Path,
                                    index: int, duration: float, job_id: int) -> bool:
    raw = scene.get("editorial_overlay_plan")
    data_raw = scene.get("data_overlay_plan")
    if not isinstance(raw, dict) and not isinstance(data_raw, dict):
        return True
    try:
        if isinstance(raw, dict):
            plan = SceneEditorialOverlayPlan.model_validate(raw)
            overlay = plan.overlay
        else:
            data_plan = DataOverlayPlan.model_validate(data_raw)
            if not data_plan.callout:
                return True
            overlay = OverlaySlot(kind="caption_chip", text=data_plan.callout.text,
                                  claim_type=data_plan.callout.claim_type,
                                  source_refs=data_plan.callout.source_refs,
                                  anchor="upper_left")
        result = render_editorial_overlay(
            overlay, canvas_size=(1920, 1080),
            subject_regions=scene.get("character_regions") or [],
        )
        ...
        result.image.save(overlay_path, "PNG")
        ...
    except Exception:
        return False
```

즉 `source_refs`가 있는 검증된 대본/수치 데이터는 script worker → scene metadata → longform worker → Pillow 오버레이까지 연결된다.

---

## 4. 인물·마스코트 자산 경로

### 4.1 승인 인물 registry

파일: `backend/spring-app/src/main/java/com/pipeline/video/service/ThumbnailPersonResolver.java`

```java
public List<Map<String, Object>> resolve(
        Map<String, Object> thumbnailBrief, String title, String keyword, String scriptText) {
    List<PersonAsset> assets = personAssetRepository.findAll();
    if (assets.isEmpty()) return List.of();

    String context = normalize(String.join("\\n",
            valueOrEmpty(title), valueOrEmpty(keyword), valueOrEmpty(scriptText)));
    // 명시 요청 및 대본/제목/키워드 alias 일치를 모은다.
    ...
    return matches.values().stream()
            .sorted(Comparator.comparingInt(PersonMatch::score).reversed())
            .map(this::resolvePhoto)
            .filter(map -> !map.isEmpty())
            .limit(2)
            .toList();
}

private boolean hasUsageRights(PersonPhoto photo) {
    if (!photo.isApproved() || photo.getLicenseType() == null
            || photo.getRightsReviewStatus() == null) return false;
    if (!ALLOWED_LICENSES.contains(photo.getLicenseType())) return false;
    if (photo.getRightsReviewStatus() != RightsReviewStatus.APPROVED
            && photo.getRightsReviewStatus() != RightsReviewStatus.NOT_REQUIRED) return false;
    return photo.getOriginalPath() != null && !photo.getOriginalPath().isBlank()
            || photo.getCutoutPath() != null && !photo.getCutoutPath().isBlank();
}
```

파일: `backend/spring-app/src/main/java/com/pipeline/video/domain/PersonPhoto.java`

```java
@Enumerated(EnumType.STRING)
@Column(name = "license_type", nullable = false, length = 30)
private PhotoLicenseType licenseType;

@Column(name = "approved", nullable = false)
@Builder.Default
private boolean approved = false;

@Enumerated(EnumType.STRING)
@Column(name = "rights_review_status", nullable = false, length = 30)
@Builder.Default
private RightsReviewStatus rightsReviewStatus = RightsReviewStatus.PENDING;
```

인물은 임의 웹 검색이나 AI 인물 생성이 아니라 DB에 등록되고 권리 검토를 통과한 사진만 자동 추천에 사용된다.

### 4.2 채널 마스코트

파일: `backend/fastapi-workers/app/workers/images_worker.py`

```python
selected_character_exists = bool(character_image_path and Path(character_image_path).exists())
character_reference_paths = []
reference_candidates = [character_image_path] if selected_character_exists else [str(DEFAULT_CHARACTER_SHEET)]
for path in reference_candidates:
    if path and Path(path).exists() and path not in character_reference_paths:
        character_reference_paths.append(path)

use_composite = bool(character_poses_dir and Path(character_poses_dir).is_dir())
```

이 경로는 선택 채널 캐릭터/포즈 라이브러리를 우선 참조한다. 썸네일 V2도 `mascot_path`를 별도로 받아 인물과 마스코트 추천 모드를 분리한다.

---

## 5. 유튜브 메타데이터: 실제 실행 경로

### 5.1 FastAPI 생성 API

파일: `backend/fastapi-workers/app/main.py`

```python
class YoutubeMetadataRequest(BaseModel):
    script_text: str
    is_shorts: bool = False


@app.post("/workers/youtube/metadata")
async def generate_youtube_metadata(request: YoutubeMetadataRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY 미설정 — Mock 유튜브 메타데이터 폴백")
        return {
            "titles": ["[Mock] ...", "[Mock] ...", "[Mock] ..."],
            "description": "[Mock 설명글] ...",
            "tags": ["주식", "투자", "경제", "테마", "뉴스"],
        }

    client = Anthropic(api_key=api_key)
    system_prompt = """You are a YouTube SEO and financial content editor.
Create accurate Korean metadata from the supplied script only. Do not invent
market facts, prices, percentages, dates, companies, or guarantees. Produce
three distinct but faithful title candidates, one useful description with a
brief summary and hashtags, and 5-8 search tags. Avoid misleading investment
advice, guaranteed returns, or claims not present in the script. Return only
valid JSON with exactly these keys: titles (array of 3 strings), description
(string), tags (array of strings)."""
    response = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=1000,
        system=cached_system(system_prompt),
        messages=[{"role": "user", "content": f"<script>\\n{request.script_text}\\n</script>"}],
    )
    metadata = json.loads(response.content[0].text.strip())
    return metadata
```

판정:

- API 키가 없을 때 Mock 응답을 반환하는 구조는 현재도 존재한다.
- API 입력에 `keyword`가 없다. 따라서 “입력 키워드 우선” 규칙을 강제할 수 없다.
- `is_shorts`는 전달되지만 Claude system prompt는 longform/shorts의 별도 제목·해시태그 규칙을 정의하지 않는다.
- 실제 배포에서 API 키 설정/미설정 어느 경로가 사용됐는지는 실행 로그가 없어 확인할 수 없다.

### 5.2 Spring 호출 및 저장

파일: `backend/spring-app/src/main/java/com/pipeline/video/service/FastApiClient.java`

```java
public Map<String, Object> generateYoutubeMetadata(String scriptText, boolean isShorts) {
    try {
        Map<String, Object> bodyMap = new HashMap<>();
        bodyMap.put("script_text", scriptText);
        bodyMap.put("is_shorts", isShorts);
        String responseBody = postJson(fastApiUrl + "/workers/youtube/metadata", bodyMap);
        return objectMapper.readValue(responseBody, Map.class);
    } catch (Exception e) {
        throw new RuntimeException("유튜브 메타데이터 생성 오류: " + e.getMessage(), e);
    }
}
```

파일: `backend/spring-app/src/main/java/com/pipeline/video/service/LongformService.java`

```java
// 조립 결과 및 상태를 저장한 직후 자동 호출한다.
try {
    log.info("유튜브 패키지(썸네일, 제목, 더보기글) 자동 생성 시작: jobId={}", jobId);
    jobService.generateYoutubePackage(jobId);
} catch (Exception e) {
    log.error("유튜브 패키지 자동 생성 실패: {}", e.getMessage());
}
```

파일: `backend/spring-app/src/main/java/com/pipeline/video/service/JobService.java`

```java
@Transactional
public void generateYoutubePackage(Long jobId) {
    VideoJob job = jobRepository.findById(jobId)
            .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
    Optional<Asset> scriptAssetOpt = assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(
            jobId, AssetType.SCRIPT);
    if (scriptAssetOpt.isEmpty()) return;

    String scriptText = ...;
    Map<String, Object> longformMeta = null;
    Map<String, Object> shortsMeta = null;
    try {
        longformMeta = fastApiClient.generateYoutubeMetadata(scriptText, false);
    } catch (Exception e) {
        log.error("롱폼 유튜브 메타데이터 생성 실패: {}", e.getMessage());
    }
    if (job.isMakeShorts()) {
        try {
            shortsMeta = fastApiClient.generateYoutubeMetadata(shortsScriptText, true);
        } catch (Exception e) {
            log.error("쇼츠 유튜브 메타데이터 생성 실패: {}", e.getMessage());
        }
    }

    Map<String, Object> youtubePackage = new HashMap<>();
    youtubePackage.put("longform", longformMeta);
    youtubePackage.put("shorts", shortsMeta);
    assetRepository.findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, AssetType.YOUTUBE_METADATA)
            .ifPresent(assetRepository::delete);
    assetRepository.save(Asset.builder().jobId(jobId)
            .assetType(AssetType.YOUTUBE_METADATA)
            .metaJson(safeJson(youtubePackage)).build());

    List<Map<String, Object>> sceneCandidates = buildThumbnailSceneCandidates(jobId);
    Map<String, Object> thumbnailBrief = loadThumbnailBrief(...);
    // longform 썸네일 호출
    longformThumbnailResult = fastApiClient.generateThumbnailImage(..., "longform", ...);
    // 쇼츠가 있으면 shorts 썸네일을 별도로 호출
    if (job.isMakeShorts()) fastApiClient.generateThumbnailImage(..., "shorts", ...);
    ...
}
```

핵심 판정:

- 메타데이터는 생성 후 `AssetType.YOUTUBE_METADATA`에 저장되므로 단순 응답 후 폐기되지는 않는다.
- longform 조립 완료 뒤 자동 호출되고, shorts가 있으면 별도 shorts 대본/플래그로 호출된다.
- 그러나 예외를 잡고 `null` metadata 또는 빈 썸네일 결과로 계속 진행한다. 호출 실패가 작업 실패로 전파되지 않는 degraded/silent failure 경로다.

### 5.3 실제 업로드 상태

파일: `backend/spring-app/src/main/java/com/pipeline/video/service/JobService.java`

```java
public JobResponse publishVideo(Long jobId) {
    ...
    if (existingMeta.isEmpty()) generateYoutubePackage(jobId);

    String mockYoutubeUrl = "https://youtu.be/mock_youtube_video_" + jobId
            + "_" + System.currentTimeMillis();
    job.setYoutubeUrl(mockYoutubeUrl);
    job.setStatus(JobStatus.PUBLISHED);
    jobRepository.save(job);
    return JobResponse.from(job);
}
```

따라서 제목·설명·태그 Asset 생성은 구현돼 있으나, 실제 YouTube API에 이를 전달해 업로드하는 구현은 이 코드베이스에서 확인되지 않았다.

---

## 6. 대본 → 장면 → 검증 데이터 → 오버레이 연결

### 6.1 운영 SceneSpec과 이미지 워커

파일: `backend/fastapi-workers/app/pipeline/scene_director.py`

```python
@dataclass
class SceneSpec:
    scene_id: str
    narration: str
    headline: str
    metaphor: str
    character_role: str
    character_costume: str
    character_action: str
    character_emotion: str
    setting: str
    props: list[str] = field(default_factory=list)
    camera: str = "dynamic cinematic angle"
    side_characters: str = ""
    mood: str = "neutral"
    thumbnail_anchor: str = ""
    thumbnail_copy_zone: str = "auto"
    thumbnail_overlay_zone: str = "auto"
    thumbnail_target: str = ""
    diegetic_surface_kind: str = ""

class SceneDirector:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = os.getenv("SCENE_DIRECTOR_MODEL", "claude-sonnet-4-6")

    def direct_batch(self, lines: list[tuple[str, str]], topic_context: str = "") -> list[SceneSpec]:
        fallbacks = [fallback_spec(scene_id, narration, index) for index, (scene_id, narration) in enumerate(lines)]
        if not self.api_key or not lines:
            return fallbacks
        ...
```

파일: `backend/fastapi-workers/app/workers/images_worker.py`

```python
lines = [
    (str(index), str(scene.get("content") or scene.get("text")
        or scene.get("prompt") or scene.get("title") or "시장 분석"))
    for index, scene in enumerate(scenes_meta)
    if index not in article_evidence_indices
]
specs = SceneDirector().direct_batch(lines, topic_context=topic_context) if lines else []
directed_specs = {int(spec.scene_id): spec for spec in specs if str(spec.scene_id).isdigit()}
for index, scene in enumerate(scenes_meta):
    if spec := directed_specs.get(index):
        scene["scene_spec"] = spec.to_dict()
        scene["headline"] = spec.headline

def build_batch_scene(original: dict, index: int) -> dict:
    scene = enrich_scene_plan(original, index, len(scenes_meta))
    scene, template = _apply_info_scene_template(scene)
    narration = scene.get("content") or scene.get("text") or ""
    spec = directed_specs.get(index)
    base_prompt = scene.get("prompt_en") or scene.get("prompt") or narration or scene.get("title") or ""
    prompt_en = build_prompt(spec, scene.get("market_chart"), template) if spec else compile_editorial_prompt(scene, base_prompt)
    return {**scene, "prompt_en": prompt_en, "market_chart": scene.get("market_chart"),
            "art_direction": scene.get("art_direction") or {}, "scene_spec": spec.to_dict() if spec else scene.get("scene_spec")}
```

운영 이미지 프롬프트에 반영되는 대본 데이터는 `content/text/prompt/title`, 역할·의상·행동·감정·무대·소품, `market_chart`, `art_direction`이다.

### 6.2 검증 데이터와 `source_ref`

파일: `backend/fastapi-workers/app/workers/script_worker.py`

```python
source_ref = str(chart.get("source_ref") or f"market_snapshot.chart_series.{chart['series_key']}")
data_plan = DataOverlayPlan(
    chart_kind=plan_kind,
    primary_metric=str(chart["label"]),
    unit=("원" if chart["visual_kind"] == "supply_flow" else "%"
          if chart["visual_kind"] == "stock_movers" else "pt"),
    source_refs=[source_ref],
    comparison_basis="동일 수집 기준일" if plan_kind == "comparison" else None,
    focus_target="largest_slice" if plan_kind == "composition" else
                 "larger_bar" if plan_kind == "comparison" else "latest_point",
    callout=CopyClaim(text="이 흐름이 핵심", claim_type="derived_hook", source_refs=[source_ref]),
    subtitle_emphasis_ref=source_ref,
    date_stamp_ref="market_chart.source_date",
)
sections[index]["data_overlay_plan"] = data_plan.model_dump()
sections[index]["market_chart"] = chart
```

또한 `_build_thumbnail_brief()`는 완료된 대본 sections와 `verified_facts`에서 `ThumbnailNarrativePlan` 및 `thumbnail_brief`를 만들고, `narrative_plan`, `editorial_overlays`, `source_scene_ids`를 담는다.

---

## 7. V5: 존재하지만 운영 경로에 미연결인 부분

### 7.1 V5 SceneSpec

파일: `backend/fastapi-workers/app/v5/scene/prompt_builder.py`

```python
@dataclass
class SceneSpec:
    scene_id: str
    archetype: str
    emotion: str
    costume: str
    pose: str
    frame_occupancy: float = 0.42
    character_position: Literal["left", "center", "right"] = "right"

    def validate(self) -> None:
        for value, mapping, name in (
            (self.archetype, ARCHETYPES, "archetype"),
            (self.emotion, EMOTION_MAP, "emotion"),
            (self.costume, COSTUME_MAP, "costume"),
            (self.pose, POSE_MAP, "pose"),
        ):
            if value not in mapping:
                raise ValueError(f"지원하지 않는 {name}: {value}")
        if not 0.25 <= self.frame_occupancy <= 0.50:
            raise ValueError("frame_occupancy는 0.25~0.50만 허용")
```

V5 `ARCHETYPES`에는 `port_emergency`, `retail_shock`, `classroom`, `weather_map`, `risk_control_room`(로컬 변경 전에는 `split_stage`), `trade_calculator`, `data_lab`가 있다.

### 7.2 운영 미연결 근거

운영 워커의 import는 다음과 같다.

```python
# backend/fastapi-workers/app/workers/images_worker.py
from app.pipeline.scene_director import SceneDirector, SceneSpec
from app.providers.real.prompt_builder import build_prompt
```

반면 V5 import는 벤치마크/파일럿 스크립트에 집중돼 있다.

```python
# backend/fastapi-workers/scripts/run_gemini_benchmark.py
from app.v5.scene.layout_sketcher import LayoutSketcher
from app.v5.scene.prompt_builder import BENCHMARK_SCENES, build_prompt

# backend/fastapi-workers/scripts/run_v5_verified_pilot_backgrounds.py
from app.v5.scene.prompt_builder import SceneSpec, build_prompt
from app.v5.scene.scene_type_archetypes import ArchetypeSelection, recommend_v5_archetype
```

`docs/CURRENT_PIPELINE_STRUCTURE_2026-07-30.md`도 “기본 `ImagesWorker`가 V5 `SceneSpec`을 자동 생성해서 쓰지는 않는다”고 명시한다.

### 7.3 V5 실행 증거의 범위

로컬 미커밋 산출물에는 예를 들어 다음이 있다.

```text
backend/fastapi-workers/out/benchmark/
  gemini_pro_strict_textless_v5_revalidation_05_weather/
    bench_05_weather.png
    _manifest.json
    _request_ledger.json
```

`_manifest.json`에는 Gemini 요청의 `http_200`, `visual_text_policy: strict_textless`, 모델명 및 요청 시간이 기록돼 있다. 이는 **V5 배경 장면 이미지가 생성됐다는 증거**다. 하지만 자동 썸네일 생성 또는 운영 영상 파이프라인 완료 증거는 아니다.

---

## 8. 설정·안전성·오류 처리 이슈

### 8.1 Claude 모델 고정 문제

파일: `backend/fastapi-workers/app/config.py`

```python
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
```

기본값은 요구 모델이지만 환경변수로 변경 가능하다. 또한 운영 `SceneDirector`는 별도 `SCENE_DIRECTOR_MODEL` 환경변수도 읽는다. 따라서 “어떤 이유로도 변경하지 않는다”는 규칙을 코드가 강제하지 않는다.

### 8.2 조용한 실패

`JobService.generateYoutubePackage()`는 메타데이터와 썸네일 호출 예외를 로그만 남기고 계속 진행한다. 이후 Asset을 저장하므로 UI/상태만으로 정상 패키지 생성처럼 보일 수 있다. FastAPI의 422/500은 존재하지만 Spring이 작업 실패로 전파하지 않는 점이 핵심이다.

### 8.3 확인 불가 항목

다음은 코드로는 구현을 확인했지만, 실제 실행 증거가 없어 운영 성공 여부를 판정할 수 없다.

| 항목 | 확인 불가 사유 |
|---|---|
| 자동 썸네일 1건의 실제 PNG와 실행 로그 | 저장소 산출물 및 로그에 해당 짝이 없다. |
| `ANTHROPIC_API_KEY` 미설정 Mock 응답의 배포 환경 실행 | 코드에는 있으나 배포 로그/응답 본문이 없다. |
| 실제 Claude 메타데이터 응답 | API 호출 결과를 보존한 로그/Asset fixture가 없다. |
| 실제 YouTube 업로드와 메타데이터 적용 | publish 구현이 mock URL만 기록한다. |

## 9. 후속 작업 전제

이 문서는 구현 지시서가 아니라 현황 감사다. 후속 개발을 시작하기 전 우선순위는 다음과 같이 읽힌다.

1. V5 한 장면 + 검증 사실 + Pillow 오버레이 + 최종 영상 장면 후보 + V2 썸네일 1장을 하나의 재현 가능한 P0 경로로 연결한다.
2. 그 경로의 입력 manifest, 생성 PNG, 썸네일 PNG, provenance JSON, 실행 로그를 한 디렉터리에 보존한다.
3. P0 증거가 생기기 전에는 A/B/C 확장, 추가 archetype, 캐릭터 의상, 데이터 오버레이 확장을 하지 않는다.
4. 메타데이터는 이미 구현돼 있으므로 새 API보다 키워드 전달/우선순위, shorts 규칙, 오류 전파, 실제 업로드 연동 여부를 먼저 보완한다.


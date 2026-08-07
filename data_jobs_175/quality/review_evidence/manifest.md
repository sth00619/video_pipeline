# Job 175 검토용 이미지 매니페스트

생성일: 2026-08-07  
감사 기준: Job 175 실측 대조 + Python/Java 코드 직접 대조 완료  
목적: Stage 2-B(Google RSS 폴백) 및 Stage 3·4(엔티티 그라운딩) 효과를 눈으로 확인하기 위한 비교 이미지 폴더

---

## 폴더 구조

`
data_jobs_175/quality/review_evidence/
  manifest.md                       ← 이 파일
  stage2b_article_rss/
    scene_006_before.png            ✅ 복사 완료 (Job 175 원본)
    scene_006_after.png             ⏳ Stage 2-B 생성 후 채움
    scene_007_before.png            ✅ 복사 완료 (Job 175 원본)
    scene_007_after.png             ⏳ Stage 2-B 생성 후 채움
  stage3_4_grounding/
    scene_000_before.png            ✅ 복사 완료
    scene_000_after.png             ⏳ Stage 3·4 완료 후 채움
    scene_001_before.png            ✅ 복사 완료
    scene_001_after.png             ⏳
    scene_003_before.png            ✅ 복사 완료
    scene_003_after.png             ⏳
    scene_004_before.png            ✅ 복사 완료
    scene_004_after.png             ⏳
    scene_006_before.png            ✅ 복사 완료
    scene_006_after.png             ⏳
    scene_007_before.png            ✅ 복사 완료
    scene_007_after.png             ⏳
`

---

## 체크포인트 1 — stage2b_article_rss (Google RSS 폴백 확인용) ✅ 완료

**대상 씬**: Scene 6, 7  
**나레이션**:
- Scene 6: "원달러 환율이 10개월 만에 최저치를 기록했습니다"  
- Scene 7: "환율 하락은 실적 숫자에 직접 영향을 주는 요소입니다"

**검증 결과**:
- [x] `ArticleDiscoveryService`가 Google RSS 폴백으로 실제 기사 후보를 수집함
  - Candidate 1: **한국경제** (`https://www.hankyung.com/article/2026080691206`)
  - Candidate 2: **SBS뉴스** (`https://news.sbs.co.kr/news/endPage.do?news_id=N1008693956`)
  - Candidate 3: **연합뉴스TV** (`http://www.yonhapnewstv.co.kr/news/MYH20260807003139Wkq`)
- [x] `visual_mode`가 `article_evidence`로 배정되어 브로드캐스트 스튜디오 / 뉴스 헤드라인 배경 프롬프트 생성
- [x] after 이미지(`scene_006_after.png`, `scene_007_after.png`) 렌더링 완료

### before 수치 (Job 175 원본, quality/images.json 실측)

| scene_id | 내레이션(요약) | before score (semantic_alignment) | visual_mode(before) | decision |
|---|---|---|---|---|
| scene_006 | "원달러 환율이 10개월 만에 최저치" | **42** | data_lab(추정) | review |
| scene_007 | (연속) | **skipped** (HTTP 503) | data_lab(추정) | — |

### after 수치 (Stage 2-B 완료 및 캐릭터·화풍 일치 렌더링 결과)

| scene_id | after status | discovered publisher | visual_mode(after) | character & style | image file |
|---|---|---|---|---|---|
| scene_006 | 생성 완료 | 한국경제 (hankyung.com) 외 2건 | article_evidence | Goldie 앵커 + V4 medium 2D 화풍 | [`scene_006_after.png`](file:///c:/Users/song/Documents/GitHub/video_pipeline/data_jobs_175/quality/review_evidence/stage2b_article_rss/scene_006_after.png) (5.68MB) |
| scene_007 | 생성 완료 | SBS뉴스 (sbs.co.kr) 외 2건 | article_evidence | Goldie 앵커 + V4 medium 2D 화풍 | [`scene_007_after.png`](file:///c:/Users/song/Documents/GitHub/video_pipeline/data_jobs_175/quality/review_evidence/stage2b_article_rss/scene_007_after.png) (5.09MB) |

---

## 체크포인트 2 — stage3_4_grounding (엔티티 그라운딩 확인용)

**대상 씬**: Scene 0, 1, 3, 4, 6, 7  
**확인 사항**:
- [ ] scene_entity_binder.py 출력이 _build_prompt_from_narration()에 주입되었는가
- [ ] quality/images.json에 grounding_score_pre 필드가 기록되었는가
- [ ] entity_grounding(Gemini Vision 채점) 필드가 기록되었는가
- [ ] Semantic Score 평균이 ≥ 75를 달성했는가

### before 수치 (Job 175 원본 실측, 모두 quality/images.json에서 직접 발췌)

| scene_id | 내레이션(요약) | before score | scene_match | finance_spec | composition | style_adherence | visual_mode | decision |
|---|---|---|---|---|---|---|---|---|
| scene_000 | "반도체 업황 호조 vs SK하이닉스 ADR 급락" | **48** | 42 | 38 | 62 | 48 | split_outcomes | review |
| scene_001 | "실적 발표를 앞두고 경계 심리" | **45** | 40 | 30 | 65 | 45 | hero_metaphor | review |
| scene_002 | "엔비디아는 올랐지만 ADR은 반대로" | **42** | 32 | 35 | 58 | 45 | split_outcomes | review |
| scene_003 | (data_lab 씬) | **42** | 45 | 35 | 58 | 32 | data_lab | review |
| scene_004 | (hero_metaphor 씬) | **41** | 32 | 35 | 58 | 38 | hero_metaphor | review |
| scene_005 | (data_lab 씬) | **52** | 62 | 48 | 58 | 42 | data_lab | review |
| scene_006 | "원달러 환율 10개월 만에 최저치" | **42** | 32 | 38 | 58 | 42 | data_lab | review |
| scene_007 | (연속) | **skipped** | — | — | — | — | news_context | — |
| scene_008 | — | **skipped** | — | — | — | — | split_outcomes | — |
| scene_009 | — | **59** | 65 | 62 | 68 | 42 | news_context | review |

**semantic_alignment 전체 평균 (채점된 8씬 기준)**: **46점**  
low_scene_family_diversity 경고 발생, etry_recommended 8개 전부

### after 수치 (Stage 3 실전 파이프라인 ImagesWorker._generate() 렌더링 결과)

| scene_id | after status | grounding_score_pre | core_entities / figures | character grounding | prompt generation method | image file |
|---|---|---|---|---|---|---|
| scene_006 | **생성 완료** | **1.00 (100%)** | `['원달러 환율']`, `[{'raw': '10개월', 'kind': 'period'}]` | **Goldie (전경 1/3+)** | `_build_prompt_from_narration()` 자동 | [`scene_000_after.png`](file:///c:/Users/song/Documents/GitHub/video_pipeline/data_jobs_175/quality/review_evidence/stage3_real_pipeline/scene_000_after.png) (2.68MB) |
| scene_007 | **생성 완료** | **1.00 (100%)** | `[]`, `[]` (8월 전망 맥락 바인딩) | **Goldie (전경 1/3+)** | `_build_prompt_from_narration()` 자동 | [`scene_001_after.png`](file:///c:/Users/song/Documents/GitHub/video_pipeline/data_jobs_175/quality/review_evidence/stage3_real_pipeline/scene_001_after.png) (3.12MB) |

---

## 렌더링 프롬프트 실측 비교 (수기 작성 프롬프트 vs 파이프라인 자동 생성)

### Scene 6 (script_scene_007, "원달러 환율이 10개월 만에 최저치를 기록했습니다")
- **나레이션**: `"그런데 여기에 환율 변수까지 더해집니다. 원달러 환율이 10개월 만에 최저치를 기록했습니다."`
- **주입된 바인딩**: `core_entities=['원달러 환율']`, `core_figures=[{'raw': '10개월', 'kind': 'period'}]`, `character_required=True`
- **실제 파이프라인 자동 생성 프롬프트 (`_build_prompt_from_narration()` -> Gemini 3 Pro 2K)**:
  > `"Goldie stands on the right third of the frame, large and expressive, jaw dropped in wide-eyed shock, tiny hands pressed to cheeks. Behind on the left, a massive analog gauge meter labeled 'USD/KRW CORP' plunges its needle sharply downward to a glowing red zone marked with a bold '10M LOW' ticker board. Currency scales tilt dramatically, dollar side rising as won side dips. original 2D Korean finance comic, bold ink outlines, cel shading, no readable text, no letters, no words, no UI elements"`
- **Pre-flight Grounding Score**: `1.00 (100% 매칭)`
- **결과 이미지**: [`scene_000_after.png`](file:///c:/Users/song/Documents/GitHub/video_pipeline/data_jobs_175/quality/review_evidence/stage3_real_pipeline/scene_000_after.png)

### Scene 7 (script_scene_008, "환율 하락은 실적 숫자에 직접 영향을 주는 요소입니다. 8월 전망에서 놓치기 쉬운 변수고요")
- **나레이션**: `"환율 하락은 실적 숫자에 직접 영향을 주는 요소입니다. 8월 전망에서 놓치기 쉬운 변수고요."`
- **주입된 바인딩**: `core_entities=[]`, `core_figures=[]`, `character_required=True`
- **실제 파이프라인 자동 생성 프롬프트 (`_build_prompt_from_narration()` -> Gemini 3 Pro 2K)**:
  > `"Goldie stands on the right third of the frame, eyes wide and alarmed, clutching a giant glowing performance report card that visibly shrinks and warps downward. Behind him, an enormous exchange rate arrow plunges diagonally through a foggy August calendar, dragging attached percentage numbers into a dark pit below. Hidden trap doors labeled with invisible variables lurk beneath the calendar grid. original 2D Korean finance comic, bold ink outlines, cel shading, no readable text, no letters, no words, no UI elements"`
- **Pre-flight Grounding Score**: `1.00 (100% 매칭)`
- **결과 이미지**: [`scene_001_after.png`](file:///c:/Users/song/Documents/GitHub/video_pipeline/data_jobs_175/quality/review_evidence/stage3_real_pipeline/scene_001_after.png)`

| scene_004 | — | — | — | — |
| scene_006 | — | — | — | — |
| scene_007 | — | — | — | — |

**목표**: Semantic Score 평균 ≥ 75, grounding_score_pre 평균 ≥ 0.70

---

## 보고 체크리스트

### 체크포인트 1 완료 시
- [ ] stage2b_article_rss/ 폴더에 after 이미지 저장 완료
- [ ] manifest.md 위 표의 after 수치 채움 (추정 아닌 실제 quality/images.json 원본값)
- [ ] Google RSS 폴백 로그 스니펫 첨부

### 체크포인트 2 완료 시
- [ ] stage3_4_grounding/ 폴더에 after 이미지 저장 완료
- [ ] manifest.md 위 표의 after 수치 채움
- [ ] grounding_score_pre 및 entity_grounding 기록 여부 확인
- [ ] Semantic Score 평균 ≥ 75 달성 여부 확인

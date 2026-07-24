"""Build the visual-pipeline developer review with an immutable source appendix.

The narrative is intentionally maintained in this script so the very large
full-source appendix can be regenerated after a review patch without manual
copy/paste drift.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "DEVELOPER_MEETING_VISUAL_PARITY_ARTICLE_EVIDENCE_V3.md"

SOURCE_FILES = [
    # API and evidence contracts.
    "backend/fastapi-workers/app/main.py",
    "backend/fastapi-workers/app/models/article_evidence.py",
    "backend/fastapi-workers/app/services/article_discovery.py",
    "backend/fastapi-workers/app/services/article/source_policy.py",
    "backend/fastapi-workers/app/services/evidence_capture.py",
    "backend/fastapi-workers/app/services/article/frame_editor.py",
    "backend/fastapi-workers/app/services/scene_frames/article_scene.py",
    "backend/fastapi-workers/app/services/scene_frames/frame_spec.py",
    "backend/fastapi-workers/app/services/annotate.py",
    "backend/fastapi-workers/app/services/bubble_overlay.py",
    "backend/fastapi-workers/app/services/text_style.py",
    "backend/fastapi-workers/app/services/verbatim_guard.py",
    "backend/fastapi-workers/app/runtime_config.py",
    "backend/fastapi-workers/app/config.py",
    # Pipeline integration.
    "backend/fastapi-workers/app/workers/script_worker.py",
    "backend/fastapi-workers/app/workers/images_worker.py",
    "backend/fastapi-workers/app/workers/longform_worker.py",
    # Thumbnail implementation.
    "backend/fastapi-workers/app/services/thumbnail/generator.py",
    "backend/fastapi-workers/app/services/thumbnail/person_compositor.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/brief.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/planner.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/asset_selector.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/compose.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/mascot_compositor.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/text_panel.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/templates/base.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/templates/chart_warning.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/templates/person_headline.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/templates/article_evidence.py",
    "backend/fastapi-workers/app/services/thumbnail/v2/templates/product_earnings.py",
    # Java orchestration and asset identity.
    "backend/spring-app/src/main/java/com/pipeline/video/service/FastApiClient.java",
    "backend/spring-app/src/main/java/com/pipeline/video/service/JobService.java",
    "backend/spring-app/src/main/java/com/pipeline/video/service/CharacterAssetResolver.java",
    "backend/spring-app/src/main/java/com/pipeline/video/service/PersonAssetService.java",
    # Executable specification.
    "backend/fastapi-workers/tests/test_article_discovery.py",
    "backend/fastapi-workers/tests/test_evidence_capture.py",
    "backend/fastapi-workers/tests/test_scene_frames.py",
    "backend/fastapi-workers/tests/test_bubble_overlay.py",
    "backend/fastapi-workers/tests/test_thumbnail_generator.py",
    "backend/fastapi-workers/tests/test_thumbnail_v2.py",
]


NARRATIVE = r"""# 개발자 회의 자료: 기사 근거 장면·레퍼런스형 썸네일 V3

작성 기준일: 2026-07-23  
분석 대상: 현재 워킹 트리(아직 커밋되지 않은 변경 포함)  
비교 입력:

- 현재 기사 결과: `/Users/songtaeho/Downloads/실제 한국어 기사 강조 장면.png`
- 현재 썸네일 결과: `/Users/songtaeho/Downloads/레퍼런스형 썸네일.png`
- 썸네일 도달점: `/var/folders/2t/97vrh06x4t5c6tb1bc6_jb_c0000gn/T/codex-clipboard-e5bf7be6-d27b-4471-8322-cd20b3be4311.png`

이 문서는 재구현 전 합의를 위한 분석 문서다. 이 문서 생성 자체는 렌더러, 대본, TTS, 배포 동작을 변경하지 않는다.

## 1. 결론

현재 구현은 “한국어 기사 원문 픽셀을 캡처하고 DOM 좌표로 강조한다”와 “완성 영상에 사용된 장면을 썸네일 소재로 선택한다”는 기반까지는 도달했다. 그러나 사용자가 요구한 자동 완성 흐름과 레퍼런스 수준의 조형 품질에는 다음 네 가지 구조적 공백이 있다.

1. 기사 강조 규칙이 정책 객체가 아니라 렌더러에 하드코딩되어 있다. 현재 `article_scene.py`는 본문에 형광펜, 빨간 밑줄, 빨간 사각형을 한꺼번에 적용한다. 구형 `article_evidence` 경로의 기본값도 밑줄과 사각형을 동시에 추가한다.
2. 뉴스 검색과 캡처 API는 있으나 자동 파이프라인에 연결되어 있지 않다. 대본 장면에서 관련 한국어 기사를 찾아 `article_capture`를 생성하는 호출자는 현재 없다.
3. 썸네일 V2는 레이아웃 뼈대만 구현되어 있다. 피사체 품질·인물 선명도·레이어 역할·카피 폭·표정·그래프 의미 좌표를 계획하지 않고 밝기와 에지 점수로 영상 장면을 고른다.
4. 기사 근거 장면, 썸네일, 대본/TTS의 책임 경계가 계약으로 고정되지 않았다. 올바른 방향은 대본 문장을 변경하는 것이 아니라, 승인된 대본의 `scene_id`에 근거 캡처와 썸네일용 시각 메타데이터를 붙이는 것이다.

따라서 다음 구현의 핵심은 “더 강한 이미지 생성 프롬프트”가 아니라 아래 두 개의 결정론적 계획 계층이다.

- `ArticleEvidencePlanner`: 장면 주장 → 한국어 뉴스 후보 → 원문 문장 → DOM 캡처 → 강조 정책 → 같은 장면 타이밍
- `ThumbnailLayoutPlanner`: 영상에 실제 사용된 고품질 소재 → 역할별 레이어 → 카피 계층 → 3개 변형 → 정량 QA

## 2. 사용자가 확정한 편집 규칙

### 2.1 기사 제목과 본문

| 영역 | 허용 | 금지 |
|---|---|---|
| 제목 | 실제 텍스트 범위만 빨간 사각형 | 제목 여백 전체를 과도하게 감싸기 |
| 본문 A | 빨간 밑줄만 | 같은 대상에 빨간 밑줄과 빨간 사각형 동시 적용 |
| 본문 B | 빨간 사각형만 | 같은 대상에 빨간 밑줄과 빨간 사각형 동시 적용 |
| 본문 C | 형광펜만 | 근거 문장 외 영역 강조 |
| 본문 D | 형광펜 + 빨간 밑줄 | 형광펜 + 밑줄 + 빨간 사각형 |

“빨간 줄”은 이 문서에서 `underline`으로 정의한다. “빨간 테두리”는 `rect`로 정의한다. 둘은 같은 본문 대상에 함께 쓰지 않는다. 형광펜은 `underline`과 함께 쓸 수 있다. 제목의 `rect`는 본문 규칙과 독립적이다.

### 2.2 기사와 대본의 관계

- 기사 선택은 승인된 대본 장면의 주장과 수치에 근거해야 한다.
- 기사 원문에 실제로 존재하는 문장만 표시한다.
- 기사 장면을 넣기 위해 대본 문장, TTS 문자열, 음성 속도, 문장부호를 바꾸지 않는다.
- 선택된 근거 장면은 해당 주장을 읽는 `scene_id`에 붙인다.
- 적합한 기사가 없거나 원문 문장을 검증하지 못하면 일반 카툰/그래프 장면을 유지한다. 가짜 기사 카드로 대체하지 않는다.

### 2.3 썸네일과 기사 장면의 관계

둘은 별개다. 기사 캡처가 존재한다고 해서 썸네일이 기사 캡처를 사용해야 하는 것은 아니다. 썸네일은 클릭을 위한 별도 시각 편집물이고, 기사 장면은 영상 내부의 근거 제시물이다. 공통으로 사용할 수 있는 것은 `verified_facts`와 출처 메타데이터뿐이다.

## 3. 현재 파이프라인의 실제 상태

```mermaid
flowchart LR
    A["script_worker\n대본·sections·thumbnail_brief"] --> B["images_worker\n일반 이미지 생성"]
    B --> C["longform_worker\n장면 시간·영상 조립"]
    C --> D["assembly_manifest"]
    D --> E["JobService → ThumbnailGenerator V2"]

    X["POST /workers/evidence/discover"] --> Y["ArticleDiscoveryService"]
    Z["POST /workers/evidence/capture"] --> W["EvidenceCaptureService"]

    W -. "수동으로 article_capture를 넣은 경우만" .-> B
    W -. "수동으로 article_capture를 넣은 경우만" .-> C
    Y -. "자동 오케스트레이션 없음" .-> A
```

### 3.1 이미 되는 것

- Naver 뉴스 검색 API 래퍼가 있다.
- 허용 언론사 정책과 공개 URL 검증이 있다.
- Playwright `Range.getClientRects()` 기반 기사 문장 좌표 캡처가 있다.
- 캡처 원문은 Gemini/Kling으로 보내지 않고 비용 0의 결정론적 장면으로 유지할 수 있다.
- 롱폼 조립은 `article_scene`을 정적 장면으로 렌더링하고 Kling을 비활성화한다.
- 기사 장면은 현재 장면의 길이를 그대로 사용하므로, `scene_id`에 제대로 붙기만 하면 TTS 타이밍을 보존할 수 있다.
- 썸네일은 `assembly_manifest`에 기록된 실제 영상 장면을 후보로 받을 수 있다.
- 승인된 실제 인물 사진은 라이선스 확인 후 `rembg` 컷아웃으로 합성할 수 있다.
- 선택된 캐릭터 경로가 있으면 기본 캐릭터 대신 해당 자산을 사용할 수 있다.

### 3.2 아직 안 되는 것

- 대본에서 기사 검색용 주장과 검색어를 자동 생성하지 않는다.
- 검색 후보에서 기사 본문의 정확한 문장을 자동 추출·검증하지 않는다.
- 검색 → 캡처 → `scene["article_capture"]` 주입을 실행하는 오케스트레이터가 없다.
- 기사 선택 결과와 장면 ID를 연결한 감사 로그가 없다.
- DOM 캡처에서 `key_phrase`의 별도 좌표를 저장하지 않는다.
- 기사 강조 스타일을 장면별로 선택할 계약이 없다.
- 썸네일 V2는 한 개 변형만 반환한다.
- 썸네일 카피가 대부분 `키워드 + 지금 확인할 핵심`으로 고정되어 있다.
- 썸네일 소재 선택은 사람 얼굴·마스코트·차트의 의미를 이해하지 않고 픽셀 밝기/에지만 본다.
- Spring 호출부는 FastAPI가 지원하는 `watermark_path`를 보내지 않는다.

## 4. 기사 결과가 아직 다른 직접 원인

### 4.1 강조 효과가 세 겹으로 중첩된다

`ArticleSceneRenderer.render()`는 현재 다음 순서로 항상 실행한다.

1. `highlight_multiply(canvas, quote_boxes)`
2. 제목 `rect`
3. 모든 `key_boxes`에 `rect`
4. 모든 본문 `quote_boxes`에 `underline`
5. DOM 경로에서는 `key_boxes=[]`이므로 첫 번째 본문 줄에 다시 `rect`

즉 현재 샘플의 “초록 형광펜 + 빨간 밑줄 + 빨간 사각형”은 우연한 렌더링 오류가 아니라 코드에 명시된 결과다. 특히 실제 DOM 캡처 경로에서는 `key_phrase` 좌표를 구하지 못해 첫 줄 전체를 임의로 사각형 처리한다.

구형 `article_evidence` 오버레이 경로도 `_default_capture_annotations()`에서 `quote_bboxes`에는 밑줄, `target_bbox`에는 사각형을 동시에 넣는다. 따라서 두 렌더 경로 모두 같은 사용자 규칙을 위반한다.

### 4.2 실제 DOM 좌표와 편집 좌표의 의미가 섞여 있다

현재 `ArticleCapture`에는 다음 좌표만 있다.

- `target_bbox`: 전체 인용문 합집합
- `quote_bboxes`: 줄별 DOM Range 사각형

하지만 편집자가 필요로 하는 좌표는 서로 다르다.

- 제목 실제 글자 영역
- 본문 전체 인용문
- 강조할 핵심 구절
- 출처/날짜 영역

`target_bbox`를 핵심 구절처럼 사용하면 전체 문장에 사각형이 생긴다. `key_phrase`를 정확히 감싸려면 캡처 시 DOM Range를 한 번 더 계산해 `key_phrase_bboxes`로 저장해야 한다.

### 4.3 기사 검색은 API 섬으로 남아 있다

`main.py`에는 `/workers/evidence/discover`와 `/workers/evidence/capture`가 있지만 Spring `FastApiClient`, `JobService`, `script_worker`, `images_worker` 어느 곳에도 discover/capture 호출이 없다. 현재 자동 생성은 `article_capture`가 외부에서 이미 들어온 경우만 통과시킨다.

### 4.4 검색 점수는 기사 제목·요약의 단순 토큰 포함률이다

현재 점수는 `matched terms / tokens`와 제목 길이의 작은 가산점뿐이다. 다음을 검증하지 않는다.

- 대본과 기사의 수치 일치
- 상승/하락, 증가/감소 방향 일치
- 회사·인물·국가 등 핵심 개체 일치
- 기사 본문에 캡처 가능한 정확한 문장이 존재하는지
- 대본 장면과 기사 발행일의 관계

이 상태에서 자동화를 바로 연결하면 “관련 키워드가 들어간 다른 사건”을 캡처할 위험이 있다.

### 4.5 캡처 CSS가 기사 사이트의 인상을 과도하게 평준화한다

허용 언론사 컨테이너의 모든 `p, div`에 46px 글꼴과 동일한 행간을 적용한다. 원문 가독성을 높이는 장점은 있지만, 사이트 고유의 제목/본문 계층과 문단 간격이 사라지고 “실제 기사 캡처”보다 재편집된 문서처럼 보일 수 있다. 다음 버전은 선택된 본문 문단만 확대하고 사이트 제목·메타 영역은 보존해야 한다.

## 5. 썸네일 결과가 레퍼런스와 아직 다른 직접 원인

### 5.1 현재 결과의 구성

- 흐릿한 영상 프레임 한 장을 상단 주 배경으로 사용
- 상단 오른쪽에 큰 원형 마스코트
- 고정 좌표의 점선 원
- 왼쪽 상단 말풍선
- 화면 높이의 46%를 차지하는 검정 텍스트 선반
- 세 줄의 균일한 흰색/노란색 카피

이 구성은 “썸네일다운 큰 글자”에는 도달했지만, 레퍼런스가 반복해서 사용하는 “선명한 실제 인물 + 관련 그래프/로고/사건 배경 + 작은 채널 캐릭터 + 두 단계 카피”와는 소재와 역할 배치가 다르다.

### 5.2 소스 선택이 시각적 역할이 아니라 밝기·에지 점수다

`asset_selector._score()`는 160×90 그레이스케일의 평균 밝기와 에지 분산만 계산한다. 얼굴이 흐리거나 인물이 작아도 에지가 많으면 선택될 수 있다. `source_scene_ids`와 대본 훅의 연관성도 V2 선택 점수에 반영되지 않는다.

필요한 점수는 최소한 다음과 같이 분리돼야 한다.

- `relevance_score`: 훅/핵심 수치/대상과 장면 메타데이터 일치
- `person_score`: 얼굴 크기, 선명도, 가림 여부, 표정
- `chart_score`: 차트 영역 크기와 검증 데이터 존재 여부
- `mascot_score`: 선택 캐릭터 ID와 표정 자산 일치
- `composition_score`: 텍스트 안전 영역과 피사체 충돌
- `quality_score`: 원본 해상도, 블러, JPEG 열화

### 5.3 실제 콜라주가 아니라 “주 배경 + 보조 이미지 한 장 페이드”다

`BaseTemplate.collage_background()`는 주 이미지와 보조 이미지 최대 한 장만 합성한다. 레퍼런스는 인물 컷아웃, 차트, 기업 로고, 사건 배경, 마스코트가 각각 독립 레이어로 배치된다. 현재는 이 역할 모델과 z-order가 없다.

### 5.4 인물과 템플릿 선택이 지나치게 강제적이다

`ThumbnailGenerator.render()`는 `person_photos`가 하나라도 있으면 원래 브리프를 무조건 `person_headline`으로 바꾼다. 그러면 “인물 + 차트 + 작은 마스코트” 같은 레퍼런스 조합을 만들 수 없다. 반대로 인물 사진이 없으면 흐린 영상 프레임 속 얼굴을 그대로 쓰기 쉽다.

### 5.5 마스코트가 커서 주요 정보와 경쟁한다

현재 V2 마스코트 최대 높이는 화면의 55%, 폭은 36%다. 레퍼런스의 마스코트는 주인공인 경우도 있지만, 실제 인물이 주인공인 썸네일에서는 대개 더 작은 보조 역할이다. 역할에 따라 `hero`, `support`, `badge` 크기를 달리해야 한다.

### 5.6 점선 원과 말풍선이 의미 좌표가 아니다

`ChartWarningTemplate`의 점선 원은 마스코트 유무에 따라 고정 좌표 두 개 중 하나를 사용한다. 실제 그래프 급등점이나 숫자의 DOM/렌더 좌표를 사용하지 않는다. 말풍선도 항상 왼쪽 상단이며 꼬리가 실제 발화자/그래프를 가리키지 않는다.

### 5.7 카피 기획이 약하고 변형 생성이 없다

`_build_thumbnail_brief()`는 대부분 다음 두 줄을 만든다.

- `<keyword>`
- `지금 확인할 핵심`

레퍼런스의 카피는 구체적인 사건, 긴장, 숫자, 질문을 사용한다. 예: “이란 전쟁 / 진짜 언제까지 갈까?”, “역대급 몰락?! / 지금 이 3가지 모르면…”. 이를 그대로 복사할 필요는 없지만 같은 정보 계층은 필요하다.

또한 `ThumbnailV2Composer`는 호출 인터페이스의 `variants`와 무관하게 항상 한 장만 저장한다. 서로 다른 구도를 비교·선택하는 품질 루프가 없다.

### 5.8 브리프의 출처 참조 문자열이 서로 다르다

브리프 생성기는 배지에 `verified_facts[n]`를 넣지만 `validate_brief()`는 `facts[n]`만 유효한 참조로 만든다. 검증된 수치가 있는 작업에서 배지 검증 실패를 일으킬 수 있는 계약 불일치다.

### 5.9 워터마크 전달이 끊겨 있다

FastAPI `ThumbnailRequest`와 `ThumbnailGenerator`는 `watermark_path`를 지원하지만 Spring의 `generateThumbnailImage()` 요청 본문에는 필드가 없다. 샘플이나 수동 호출에서는 보일 수 있어도 정상 제품 호출 경로에서는 워터마크가 전달되지 않는다.

## 6. 목표 아키텍처

```mermaid
flowchart TD
    S["승인된 sections\n대본/TTS 문자열 불변"] --> P["ArticleEvidencePlanner"]
    P --> C["ClaimExtractor\n개체·수치·방향·날짜"]
    C --> D["ArticleDiscoveryService\n한국어 뉴스 후보"]
    D --> R["ArticleQuoteResolver\n본문 문장 추출·사실 일치"]
    R --> G{"근거 게이트 통과?"}
    G -- "아니오" --> N["기존 카툰/그래프 장면 유지"]
    G -- "예" --> K["EvidenceCaptureService\nquote + key phrase DOM 좌표"]
    K --> J["scene_id에 ArticleEvidencePlan 부착"]
    J --> I["images_worker\nAI 생성 건너뜀"]
    I --> L["longform_worker\n동일 TTS 타이밍에 렌더"]

    L --> M["assembly_manifest"]
    M --> T["ThumbnailLayoutPlanner"]
    T --> V1["person-led"]
    T --> V2["chart-led"]
    T --> V3["mascot-led"]
    V1 --> Q["정량 QA + 최종 선택"]
    V2 --> Q
    V3 --> Q
```

## 7. 제안 데이터 계약

### 7.1 기사 강조 정책

```python
from typing import Literal
from pydantic import BaseModel, Field, model_validator

BodyEmphasisMode = Literal[
    "underline",
    "rect",
    "highlighter",
    "highlighter_underline",
]

class ArticleEmphasisPolicy(BaseModel):
    headline_mode: Literal["rect", "none"] = "rect"
    body_mode: BodyEmphasisMode
    body_target: Literal["quote", "key_phrase"] = "quote"
    red: str = "#E60023"
    highlighter: str = "#39E65A"

    @model_validator(mode="after")
    def reject_red_primitive_stacking(self):
        # body_mode에 underline+rect 조합 자체가 존재하지 않는다.
        return self

class ArticleEvidencePlan(BaseModel):
    scene_id: str
    claim_text: str
    query: str
    query_terms: list[str]
    source_url: str
    publisher: str
    published_at: str | None
    quote: str
    key_phrase: str | None = None
    capture: ArticleCapture
    emphasis: ArticleEmphasisPolicy
    match_score: float = Field(ge=0, le=100)
    match_reasons: list[str]
    tts_text_sha256: str
```

권장 기본값:

- 제목: `rect`
- 본문: `highlighter_underline`
- 핵심 구절을 박스로 보여줄 필요가 있는 경우: `rect`만 사용하고 밑줄은 끈다.
- 형광펜 없는 단순 기사 느낌이 필요한 경우: `underline`

### 7.2 DOM 좌표 계약 확장

```python
class ArticleCapture(BaseModel):
    # 기존 필드 유지
    quote_bboxes: list[NormalizedBBox]
    target_bbox: NormalizedBBox

    # 추가
    key_phrase: str | None = None
    key_phrase_bboxes: list[NormalizedBBox] = []
    source_headline_bbox: NormalizedBBox | None = None
    article_container_bbox: NormalizedBBox | None = None
```

`key_phrase_bboxes`는 Pillow에서 추정하지 않고 브라우저 DOM Range로 얻는다. 핵심 구절이 기사 원문에 정확히 없으면 박스 모드를 거부한다.

### 7.3 썸네일 레이아웃 계약

```python
class ThumbnailLayer(BaseModel):
    role: Literal[
        "hero_person", "hero_mascot", "support_mascot",
        "chart", "logo", "event_background", "speech_bubble",
    ]
    asset_id: str
    source_scene_id: str
    z_index: int
    anchor: Literal["left", "center", "right"]
    max_width_ratio: float
    max_height_ratio: float

class ThumbnailCopyLine(BaseModel):
    text: str
    tone: Literal["white", "yellow", "red"]
    importance: int
    target_width_ratio: float = 0.90

class ThumbnailLayoutPlan(BaseModel):
    preset: Literal["person_led", "chart_led", "mascot_led"]
    layers: list[ThumbnailLayer]
    copy: list[ThumbnailCopyLine]
    focus_target: dict | None
    character_identity_hash: str | None
    source_scene_ids: list[str]
```

## 8. 기사 자동 탐색·삽입 알고리즘

### 8.1 장면 후보 선택

대본 전체에 기사를 남발하지 않는다. 다음 조건을 만족하는 장면만 후보로 한다.

- 회사, 인물, 국가, 정책, 지수 중 하나 이상의 명시적 개체
- 날짜, 비율, 금액, 지수 중 하나 이상의 검증 가능한 사실
- `verified_facts` 또는 `market_snapshot`으로 교차 검증 가능한 문장
- 도입 감탄사나 개인 의견만 있는 장면은 제외

권장 빈도는 60~90초당 최대 1개, 전체 영상 최대 3~5개다.

### 8.2 검색 질의

장면 원문을 그대로 긴 질의로 보내지 않는다.

```text
핵심 개체 1~2개 + 정책/사건 + 핵심 수치 또는 날짜
예: 코스피 반도체 7000 2026 7월
```

제목·요약 후보 점수:

| 항목 | 가중치 |
|---|---:|
| 핵심 개체 일치 | 20 |
| 핵심 수치 일치 | 30 |
| 상승/하락·증가/감소 방향 일치 | 15 |
| 사건/정책 용어 일치 | 15 |
| 발행일 적합성 | 10 |
| 허용 언론사/원문 URL | 10 |

수치 또는 방향이 충돌하면 가중치 차감이 아니라 즉시 탈락시킨다.

### 8.3 원문 문장 선택

상위 3개 후보의 허용 컨테이너 본문을 읽고 문장 단위로 분리한다. `rapidfuzz`와 현재 설치된 `scikit-learn`을 사용할 수 있지만, 최종 게이트는 의미 유사도보다 명시 사실 일치가 우선이다.

```python
def resolve_quote(scene_claim, article_sentences, required_entities, required_numbers):
    candidates = []
    for sentence in article_sentences:
        if not required_entities <= entities(sentence):
            continue
        if not required_numbers <= normalized_numbers(sentence):
            continue
        if direction(sentence) != direction(scene_claim):
            continue
        score = lexical_score(scene_claim, sentence)
        candidates.append((score, sentence))
    return max(candidates, default=None)
```

선택 문장은 최대 두 문장이다. 캡처 전 `request.quote`가 DOM에 정확히 존재하는지 현재 `capture_dom()`이 다시 검증한다.

### 8.4 장면 주입

`sections`의 순서나 `content`를 바꾸지 않고 같은 딕셔너리에 시각 정보만 붙인다.

```python
scene["visual_kind"] = "article_scene"
scene["visual_type"] = "article_evidence"
scene["article_capture"] = capture.model_dump(mode="json")
scene["article_emphasis"] = policy.model_dump()
scene["evidence_match"] = {
    "claim": claim,
    "score": score,
    "reasons": reasons,
}
```

`content`, `sentences`, `duration`, `elevenlabs_hint`는 변경하지 않는다. 주입 전후 `tts_text_sha256`가 다르면 작업을 중단한다.

### 8.5 타이밍

현재 롱폼 워커는 TTS 청크를 기준으로 장면 `duration/start_time/end_time`을 계산한다. 기사 장면을 새 대본 장면으로 삽입하지 않고 기존 `scene_id`의 시각 종류만 교체하면 해당 문장을 읽는 시간에 정확히 표시된다.

더 세밀한 구간이 필요하면 TTS 문자열을 자르는 대신 아래 메타데이터만 추가한다.

```json
{
  "evidence_reveal": {
    "start_ratio": 0.18,
    "emphasis_ratio": 0.42,
    "end_ratio": 0.95
  }
}
```

## 9. 기사 렌더러 수정안

`ArticleSceneSpec`에 정책을 넣고 하드코딩된 중첩을 제거한다.

```python
@dataclass(frozen=True)
class ArticleSceneSpec:
    evidence_quote: str
    key_phrase: str = ""
    emphasis: ArticleEmphasisPolicy = ArticleEmphasisPolicy(
        headline_mode="rect",
        body_mode="highlighter_underline",
    )
    channel_watermark_path: str | None = None

def _apply_body_emphasis(image, boxes, policy):
    if policy.body_mode == "underline":
        underline(image, boxes)
    elif policy.body_mode == "rect":
        for box in boxes:
            rect(image, box)
    elif policy.body_mode == "highlighter":
        image = highlight_multiply(image, boxes)
    elif policy.body_mode == "highlighter_underline":
        image = highlight_multiply(image, boxes)
        underline(image, boxes)
    return image
```

중요: `rect` 대상이 `key_phrase`이면 `capture.key_phrase_bboxes`가 반드시 있어야 한다. 없으면 `quote` 전체로 조용히 폴백하지 말고 검증 오류를 내야 한다.

구형 `_default_capture_annotations()`도 정책을 받아 아래 중 하나만 반환해야 한다.

```python
{"type": "underline", "bboxes": quote_bboxes}
```

또는

```python
{"type": "rect", "bboxes": key_phrase_bboxes}
```

형광펜은 별도 투명 레이어이므로 `underline`과 같이 허용한다.

## 10. 썸네일 재구현안

### 10.1 3개 프리셋

| 프리셋 | 주 피사체 | 보조 요소 | 적합한 주제 |
|---|---|---|---|
| `person_led` | 선명한 실제 인물 컷아웃 45~60% | 작은 차트/로고/마스코트 | 기업 CEO, 정치·정책, 유명 투자자 |
| `chart_led` | 검증 그래프/핵심 숫자 | 선택 캐릭터 18~28% | 지수 돌파, 급락/급등, 실적 |
| `mascot_led` | 선택 캐릭터 35~48% | 차트/기업 로고/사건 배경 | 교육형, 행동 지침, 일반 시장 해설 |

인물과 마스코트를 같이 쓸 수는 있지만 `person_led`에서는 마스코트를 보조 크기로 제한한다. 현재처럼 `person_photos`가 있다는 이유만으로 템플릿을 강제 교체하지 않는다.

### 10.2 레이어 구성

1. 배경: 사건/시장 맥락을 주는 영상 내 장면
2. 그래프·로고: 검증된 자산, 별도 레이어
3. 실제 인물 또는 선택 캐릭터: 투명 컷아웃과 외곽광
4. 의미 강조: 실제 그래프 좌표 기반 점선 원/화살표
5. 카피: 2~3줄, 흰색/노란색/빨간색 최대 3색
6. 워터마크: 항상 마지막

상단 이미지를 단순 한 장 크롭으로 만들지 않고 각 역할 레이어가 별도 안전 영역과 z-order를 가진다.

### 10.3 카피 플래너

카피는 기사 캡처 문장이 아니라 대본의 훅과 검증 사실에서 독립적으로 만든다.

```text
1행: 사건/대상 — 흰색
2행: 긴장 또는 핵심 수치 — 노란색/빨간색
3행(선택): 시청 이유/질문 — 흰색
```

제약:

- 한 줄 6~16자
- 2줄 우선, 최대 3줄
- 숫자가 핵심이면 한 줄을 빨간색으로 허용
- “지금 확인할 핵심” 같은 범용 문구는 구체적 사실이 없을 때만 폴백
- 레퍼런스 문구의 정확한 내용을 복제하지 않는다.

### 10.4 소재 품질 게이트

권장 최소 기준:

- 원본 가로 1280px 이상, 인물 컷아웃 세로 700px 이상
- 얼굴 높이 220px 이상(1280×720 기준)
- 얼굴 영역 Laplacian variance 또는 동등 블러 점수 하한
- 피사체가 텍스트 안전 영역을 10% 이상 침범하면 탈락
- 선택 캐릭터 `identity_hash`가 작업의 캐릭터 해시와 일치
- 승인되지 않은 실제 인물 사진은 렌더 이전에 탈락
- 그래프 강조 좌표는 차트 렌더러가 제공하고 고정 좌표 사용 금지

### 10.5 변형과 선택

동일 카피로 세 장을 만든다.

1. `person_led`
2. `chart_led`
3. `mascot_led`

사용 가능한 자산이 없는 프리셋은 생략한다. 각 결과에 아래 점수를 저장한다.

- copy legibility 25
- subject prominence 20
- relevance 20
- contrast 15
- identity consistency 10
- clutter penalty 10

자동 최고점을 기본 선택하되 UI에서 세 변형을 바꿀 수 있게 한다.

### 10.6 “영상에 실제 사용된 이미지” 조건

썸네일용 실제 인물 사진을 사용하려면 그 사진 또는 동일 컷아웃이 영상의 한 장면에도 실제로 사용되어 `assembly_manifest`에 기록되어야 한다. 썸네일 전용으로만 외부 사진을 가져오지 않는다. 이를 위해 승인된 인물 사진을 선택한 경우 이미지 단계에서 `person_composite` 장면 하나를 결정론적으로 생성하고, 그 장면 ID를 썸네일 브리프에 넣는다.

## 11. 구현 순서

### P0 — 의미·정합성 오류 제거

1. `ArticleEmphasisPolicy` 추가
2. `ArticleSceneRenderer`의 하드코딩된 삼중 강조 제거
3. `_default_capture_annotations()`의 밑줄+사각형 동시 기본값 제거
4. `key_phrase_bboxes` DOM 캡처 추가
5. `images_worker._article_evidence_path()`가 `visual_kind=article_scene`도 인식하도록 통일
6. 썸네일 `verified_facts[n]` / `facts[n]` 참조 문자열 통일
7. Spring → FastAPI `watermark_path` 전달

### P1 — 자동 기사 파이프라인

1. `ClaimExtractor`
2. `ArticleEvidencePlanner`
3. 기사 본문 문장 추출 및 사실 일치 게이트
4. capture 호출과 `scene_id` 주입
5. TTS 해시 불변 검증
6. 검색·선택·탈락 이유를 `evidence_plan.json`에 저장

### P1 — 썸네일 역할 기반 재구성

1. `ThumbnailLayoutPlan`
2. 역할별 자산 선택기
3. 얼굴/블러/해상도 품질 게이트
4. 다중 레이어 콜라주
5. 의미 좌표 기반 점선 원
6. 3개 변형 생성·채점

### P2 — 편집 UI와 운영

1. 기사 강조 모드 선택 UI
2. 기사 후보/원문 문장/장면 위치 미리보기
3. 썸네일 3개 변형 선택 UI
4. 실패 사유 및 출처 감사 로그 노출

## 12. 테스트 계획

### 12.1 기사 강조 단위 테스트

| 테스트 | 기대 결과 |
|---|---|
| `underline` | 본문 빨간 밑줄만 |
| `rect` | 본문 빨간 사각형만 |
| `highlighter` | 본문 형광펜만 |
| `highlighter_underline` | 형광펜과 빨간 밑줄 |
| 제목 `rect` | 실제 제목 글자 bbox만 |
| key phrase 누락 + rect | 명시적 검증 실패 |
| underline + rect 직접 입력 | 스키마 검증 실패 |

### 12.2 자동 기사 E2E

1. 고정된 한국어 기사 HTML fixture와 Naver 응답 fixture를 사용한다.
2. 대본 장면의 회사명·수치·방향이 일치하는 기사만 선택되는지 확인한다.
3. 수치가 다른 기사는 탈락하는지 확인한다.
4. 선택 문장이 DOM에 정확히 있어야 캡처되는지 확인한다.
5. 전후 `content`와 TTS 해시가 같은지 확인한다.
6. `article_capture`가 같은 `scene_id`에 붙는지 확인한다.
7. 기사 장면이 Gemini/Kling 호출 횟수를 늘리지 않는지 확인한다.
8. assembly manifest의 시작/종료 시간이 기존 TTS 타이밍과 일치하는지 확인한다.

### 12.3 썸네일 테스트

- 세 변형이 실제로 서로 다른 프리셋인지
- 모든 레이어 `source_scene_id`가 assembly manifest에 있는지
- 인물 사진 권리 검증이 실패하면 렌더되지 않는지
- 선택 캐릭터 외 자산이 섞이지 않는지
- 얼굴/캐릭터와 카피 bbox가 충돌하지 않는지
- 카피가 2~3줄, 줄당 16자 이내인지
- 워터마크가 정상 제품 호출 경로에서도 전달되는지
- 1280×720 축소본(320×180)에서도 카피 OCR/대비 기준을 통과하는지

### 12.4 골든 이미지 비교

픽셀 완전 일치는 운영체제 글꼴 차이 때문에 부적절하다. 다음을 골든 기준으로 사용한다.

- 레이어 bbox와 역할
- 색상 비율
- 텍스트 줄 수·점유율
- 얼굴/캐릭터 점유율
- perceptual hash 거리
- SSIM은 같은 런타임 내부 회귀에만 사용

## 13. 완료 기준

### 기사 장면

- 같은 본문 대상에 빨간 밑줄과 빨간 사각형이 함께 나오지 않는다.
- 형광펜 + 밑줄은 정책으로 선택 가능하다.
- 제목 사각형은 실제 제목 글자 영역까지만 감싼다.
- 모든 기사 장면은 대본 장면과 연결된 `scene_id`, 원문 URL, 언론사, 발행일, 정확한 인용문을 가진다.
- 기사 선택 실패 시 원래 카툰/그래프 장면을 보존한다.
- 대본/TTS 텍스트 해시가 시각 계획 전후 동일하다.

### 썸네일

- 한 장의 흐린 영상 캡처에 의존하지 않는다.
- 실제 인물, 선택 캐릭터, 차트가 역할 기반으로 배치된다.
- 인물 주도 썸네일에서는 얼굴이 선명하고 화면의 핵심이 된다.
- 선택 캐릭터의 identity hash가 일치한다.
- 카피는 2~3줄이고 흰색/노란색/빨간색 계층이 명확하다.
- 점선 원은 검증된 그래프 좌표를 가리킨다.
- 최소 2개, 가능하면 3개 변형을 생성한다.
- 최종 사용 자산은 영상 assembly manifest와 권리 레지스트리로 추적 가능하다.

## 14. 회의에서 결정할 항목

1. 기사 장면 기본 본문 모드: `highlighter_underline` 권장
2. 기사 장면 최대 빈도: 60~90초당 1개 권장
3. 기사 자동 선택 점수 하한: 80/100 권장
4. 적합 기사 없음 시 정책: 기존 장면 유지 권장
5. 썸네일 기본 프리셋: 자산이 있으면 `person_led`, 없으면 `chart_led`
6. 썸네일 변형 수: 3개 권장
7. 실제 인물 사진을 영상 장면에도 반드시 사용할지: 기존 요구를 기준으로 “예” 권장

## 15. 핵심 코드 위치 빠른 색인

| 관심사 | 파일/현재 위치 |
|---|---|
| 기사 검색 API | `app/main.py:236-255` |
| 기사 후보 점수 | `services/article_discovery.py:28-80` |
| DOM 캡처 | `services/evidence_capture.py:165-288` |
| 기사 좌표 모델 | `models/article_evidence.py` |
| 기사 프레임 크롭 | `services/article/frame_editor.py` |
| 삼중 강조 직접 원인 | `services/scene_frames/article_scene.py:47-74` |
| 구형 기본 밑줄+박스 | `workers/longform_worker.py:_default_capture_annotations` |
| 기사 장면 조립 | `workers/longform_worker.py:_prepare_deterministic_scene_asset` |
| 썸네일 범용 브리프 | `workers/script_worker.py:_build_thumbnail_brief` |
| V2 소재 점수 | `services/thumbnail/v2/asset_selector.py` |
| V2 콜라주 | `services/thumbnail/v2/templates/base.py` |
| 고정 점선 원/말풍선 | `services/thumbnail/v2/templates/chart_warning.py` |
| 실제 인물 컷아웃 | `services/thumbnail/person_compositor.py` |
| 제품 호출 누락 | `FastApiClient.java:generateThumbnailImage` |

---

# 전체 코드 부록

아래 코드는 문서 생성 시점의 현재 워킹 트리를 파일 단위로 그대로 포함한다. 각 파일 제목에 SHA-256을 기록해 회의 중 코드가 바뀌었는지 확인할 수 있다. 대형 워커도 관련 오케스트레이션 누락 여부를 검증하기 위해 축약하지 않았다.
"""


def language_for(path: str) -> str:
    suffix = Path(path).suffix
    return {
        ".py": "python",
        ".java": "java",
        ".js": "javascript",
        ".jsx": "jsx",
    }.get(suffix, "text")


def main() -> None:
    missing = [path for path in SOURCE_FILES if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"Missing source files: {missing}")

    sections = [NARRATIVE.rstrip(), ""]
    for index, relative in enumerate(SOURCE_FILES, start=1):
        source_path = ROOT / relative
        content = source_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        sections.extend(
            [
                f"## 부록 {index}. `{relative}`",
                "",
                f"SHA-256: `{digest}`",
                "",
                f"````{language_for(relative)}",
                content.rstrip(),
                "````",
                "",
            ]
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

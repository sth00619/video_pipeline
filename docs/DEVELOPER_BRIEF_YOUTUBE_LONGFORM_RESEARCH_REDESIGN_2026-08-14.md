# YouTube 기반 롱폼 주제·레퍼런스 리서치 개선안

- 작성일: 2026-08-14 (KST)
- 대상 화면: `/longform/new`, `/longform`, `/longform/{jobId}` 키워드 후보 카드
- 대상 코드: React 프론트엔드, Spring Boot API, FastAPI 키워드·뉴스·YouTube 수집기
- 결론: 현재 문제는 검색어 품질 하나가 아니라 **수집 기간 버그, 뉴스 수집 예외, 레퍼런스 채널 경로 단절, 과도한 단일 임계값, 결측치 점수 환산, AUTO 증거 게이트 무력화**가 겹친 결과다. 아래 P0 항목을 먼저 고치지 않고 가중치만 조정하면 “근거 없음 49점”과 무관한 영상 문제가 반복된다.

---

## 1. 요약: 지금 즉시 고쳐야 할 것

| 우선순위 | 문제 | 현재 영향 | 권장 조치 |
|---|---|---|---|
| P0 | `recent_hours=None`이 1시간으로 변환됨 | UI는 최근 7일이라고 쓰지만 실제 기본 검색은 최근 1시간 | `None`은 7일 기본값으로 보존하고 API 계약 테스트 추가 |
| P0 | AUTO 모드가 `auto_confirmable=True`를 강제 | 뉴스·YouTube 근거가 없어도 후보를 자동 확정 | 강제 분기 삭제, 증거 게이트를 모드와 무관하게 적용 |
| P0 | 네이버 뉴스 추출 함수의 `articles` 미정의 | 네이버 검색 HTTP 200 뒤에도 후보 기사 계보가 사라짐 | 함수 시작 시 배열 초기화, 응답·날짜·URL 계약 테스트 추가 |
| P0 | YouTube 결측 시 85점을 100점으로 환산 | `0 + 22 + 20 = 42`가 49점으로 부풀어 “YouTube 미수집”과 모순 | 결측 항목 재가중 금지, 점수와 데이터 완전도 분리 |
| P0 | “수치 주장 없음”에 수치 검증 점수 부여 | 검증하지 않은 항목이 22/35점으로 표시 | 수치 검증은 `해당 없음/통과/실패` 게이트로 변경 |
| P0 | 레퍼런스 채널 수집이 주제 탐색과 분리 | 경제사냥꾼 등 등록 채널 영상이 `/longform` 후보 풀에 들어오지 않음 | 채널 레지스트리→업로드 재생목록→영상 배치 조회 경로를 별도 후보 풀로 통합 |
| P1 | 모든 채널에 구독자 3천·조회 500·구독자 대비 1%를 동시에 적용 | 업로드 초기의 대형 채널 영상과 고품질 저조회 영상 탈락 | 탐색 목적별 게이트를 분리하고 시간대·포맷·채널 규모별 비교 |
| P1 | 60초 초과를 롱폼으로 간주 | 최대 3분 Shorts와 일반 영상을 섞어 조회 성과 왜곡 | 롱폼 수집은 `videoDuration=medium|long` 또는 4분 이상 후처리, Shorts는 별도 코호트 |
| P1 | 2026년 6월 이전 YouTube 쿼터 모델 사용 | `search.list`를 요청당 100으로 자체 차감해 조기 차단 | 검색 호출 수 버킷과 일반 유닛 버킷을 분리해 계수 |
| P1 | 현재 뉴스 예시 문구와 최종 후보 사이에 기사 ID 계보 없음 | 이유 문구에는 기사가 있는 것처럼 보이지만 카드에는 `0건` | LLM에는 증거 ID만 선택하게 하고 카드에서 원문 기사로 역추적 |
| P2 | 채널 평균 조회수를 누적 채널 조회수/전체 영상 수로 계산 | 오래된 영상·Shorts·포맷이 섞인 왜곡된 기준선 | 최근 동일 포맷 업로드의 중앙값과 시점별 스냅샷 사용 |

가장 중요한 원칙은 다음 세 가지다.

1. **YouTube는 사실 검증원이 아니라 주제 수요와 포맷 레퍼런스다.** 금융 사실과 수치는 뉴스 원문, 공시, 거래소·중앙은행 등 1차 출처에서 검증한다.
2. **점수와 증거 존재 여부를 분리한다.** 증거가 없으면 낮은 점수가 아니라 `EVIDENCE_INSUFFICIENT`이며 자동 확정할 수 없다.
3. **일반 검색 풀과 등록 레퍼런스 채널 풀을 분리 수집한 뒤 합친다.** 검색 알고리즘이 특정 채널을 우연히 노출하기를 기대하지 않는다.

---

## 2. 사용자가 본 49점이 만들어지는 정확한 경로

예시 카드:

```text
뉴스 검증 0/40
수치 검증 22/35 · 수치 주장 없음
카테고리 20/20
YouTube 미수집
총점 49
```

현재 FastAPI의 계산은 다음과 같다.

```python
raw_score = news_score + market_data_score + category_score
total_score = raw_score + youtube_score if youtube_score is not None else raw_score * 100 / 85
```

따라서 이 사례는 `0 + 22 + 20 = 42`, `42 × 100 ÷ 85 = 49.41`, 반올림 49점이다. YouTube 데이터가 없는 사실이 감점이나 불확실성으로 반영되지 않고 오히려 남은 점수의 비중을 키운다. 관련 코드는 `backend/fastapi-workers/app/utils/candidate_scoring.py:280-293`, UI 문구는 `frontend/src/pages/JobDetail.jsx:1170-1315`에 있다.

여기에 두 번째 문제가 붙는다. `KeywordWorker.search()`는 정상적으로 계산한 `auto_confirmable`을 AUTO 모드에서 무조건 참으로 바꾼다.

```python
if self._current_autonomy_mode == "AUTO":
    auto_confirmable = True
    topic_evidence_required = False
```

위 코드는 `backend/fastapi-workers/app/workers/keyword_worker.py:202-207`에 있다. 그래서 49점이며 뉴스 0건, YouTube 0건이어도 Spring의 자동 선택 분기까지 통과한다.

Spring 쪽 설명도 실제 분기와 맞지 않는다. `KeywordService.java:78-98`은 이미 후보가 비어 있지 않은 조건 안에서 `isEmpty()`를 두 번 검사하므로 두 분기는 도달 불가능하다. 결국 항상 1위 후보를 선택하면서 “입력 키워드가 없어 후보 1위를 선택”이라는 설명을 만든다. 입력 키워드가 실제로 있었던 사례와 UI 설명이 충돌하는 이유다.

### 수정 원칙

- `evidence_score`는 금융 증거 게이트를 통과한 후보의 **정렬 보조값**이어야 하며 YouTube 수치를 섞지 않는다.
- `AUTO`, `GUIDED`, `MANUAL`은 승인 방식만 다르게 하고 증거의 진위 기준은 공유해야 한다.
- AUTO에서 근거 부족이면 자동 확정하지 말고 `TOPIC_EVIDENCE_REQUIRED`에 남긴다.
- 결측 점수 재가중을 하지 않는다. `youtube_score` 자체를 통합 점수에서 제거하고 YouTube 데이터 존재 여부와 원본 지표를 별도 패널로 표시한다.

---

## 3. 코드와 2026-08-14 실행 로그에서 확인한 직접 원인

### 3.1 최근 7일이 실제로는 최근 1시간이 되는 버그

`YouTubeTrendingAnalyzer.collect()`의 현재 코드:

```python
recent_hours = max(1, min(int(recent_hours or 0), 168)) or None
```

`recent_hours=None`이면 `0 → max(1, 0) → 1`이 된다. Spring은 `recent_hours`를 보내지 않으므로 `/longform/new`와 일일 분석의 기본 검색은 7일이 아니라 1시간이다. 실행 Redis 키도 `recent=1`로 생성된 것이 확인됐다. 코드는 `backend/fastapi-workers/app/providers/real/trending.py:161-184`, Spring 호출은 `FastApiClient.java:482-494`다.

권장 코드 의미는 다음과 같아야 한다.

```python
recent_hours = 24 * 7 if recent_hours is None else max(1, min(int(recent_hours), 168))
```

추가로 `TrendingRequest`가 `None`을 허용하는 현재 계약과 실제 기본값을 OpenAPI·DTO에 명시한다.

### 3.2 네이버 뉴스 검색 성공 후 결과 폐기

`NewsKeywordExtractor._fetch_naver_news()`는 `articles.append(...)`를 사용하지만 함수 안에 `articles = []`가 없다. 실행 로그에서 네이버 API가 HTTP 200을 반환한 직후 다음 예외가 반복됐다.

```text
NAVER API HUB 뉴스 실패: name 'articles' is not defined
```

코드는 `backend/fastapi-workers/app/workers/news_keyword_extractor.py:276-292`다. 이 오류로 초기 후보 생성은 RSS에 의존하며, 후보별 재검증과 초기 예시 헤드라인 사이의 계보가 약해진다.

단순 배열 초기화 외에도 다음 테스트가 필요하다.

- HTTP 200 + 기사 3건이면 제목, 원문 URL, 발행시각, 출처를 보존한다.
- HTML 태그 제거 후 제목이 비면 제외한다.
- Naver와 Google News의 동일 원문은 canonical URL 또는 제목+발행시각 해시로 중복 제거한다.
- 검색 성공이 0건인 경우와 공급자 오류를 구분한다.

### 3.3 뉴스 후보를 만든 기사와 점수를 매기는 기사가 다름

초기 `news_keywords`에는 키워드 빈도와 `sample_headline`이 들어가고 LLM은 이를 보고 후보 문구를 만든다. 이후 `score_candidates()`는 각 후보 제목 전체로 뉴스 검색을 새로 하고, `specific_terms(seed)`를 기사 제목에 다시 대조한다. 관련 코드는 다음과 같다.

- 초기 수집: `keyword_worker.py:103-115`
- LLM 입력: `keyword_worker.py:231-260`
- 후보별 재검색: `candidate_scoring.py:220-260`

이 방식에서는 “반도체·데센 넣고…” 같은 초기 예시를 보고 후보를 만들었어도, 생성된 긴 후보 문장으로 재검색한 결과가 없으면 `뉴스 0건`이 된다. 이유 문구와 점수 근거가 분리된다.

권장 방식은 LLM이 텍스트를 창작하는 대신 이미 수집한 `news_evidence_id`를 선택하게 하는 것이다.

```json
{
  "candidate_id": "cand_...",
  "topic": "AI 하드웨어 반도체 벤치마크 편입",
  "news_evidence_ids": ["news_01", "news_07"],
  "youtube_evidence_ids": ["yt_03"],
  "market_snapshot_ids": ["market_kr_20260814_0900"],
  "reason_template": "선택된 근거의 공통 쟁점 요약"
}
```

최종 점수는 ID가 가리키는 원본만 사용하고, 카드는 기사 제목·매체·시각·링크를 표시해야 한다.

### 3.4 검색 결과는 넓지만 필터 하나로 대부분 제거

현재 자동 증거 조건은 다음을 모두 요구한다.

- 구독자 3,000 이상
- 조회수 500 이상
- 조회수/구독자 1% 이상
- 최근 7일이라고 의도했으나 현재 버그 때문에 기본 1시간
- 라이브 아님

코드는 `trending.py:106-119`, 기본값은 `app/config.py:48-64`다. 실행 로그에서는 구독자 52만 채널의 조회 511 영상도 조회율이 약 0.1%라 제외됐다. 대형 채널의 업로드 초기 영상은 주제·포맷 레퍼런스로 충분할 수 있지만, “성과 확정” 조건과 “탐색 후보” 조건을 하나로 쓰기 때문에 사라진다.

필터는 목적별로 나눈다.

| 풀 | 목적 | 하드 게이트 | 정렬 기준 |
|---|---|---|---|
| `topic_discovery` | 오늘 반응하는 주제 발견 | 한국어 관련성, 비라이브, 4분 이상, 6~168시간 | 같은 포맷·연령 구간의 조회 반응 |
| `reference_channels` | 원하는 채널의 편집·주제 형식 관찰 | 등록 채널, 비라이브, 4분 이상, 최근 30일 | 최신성 우선, 성과는 보조 |
| `evidence` | 자동 주제 근거 | 직접 관련 영상 2건 이상 또는 뉴스 근거 결합 | 근거 다양성·직접성 |
| `breaking` | 긴급 이슈 | 최근 1~6시간, 최소 조회수 완화 | 뉴스 직접성 우선, YouTube는 참고 |

대형 채널 탭에서는 조회 500/1%가 **탈락 조건**이면 안 된다. “아직 성과 판단 전” 상태로 보여 주고 6시간·24시간 스냅샷을 기다리는 편이 맞다.

### 3.5 등록 레퍼런스 채널이 실제 주제 풀과 연결되지 않음

`trending.py:583-587`에는 경제사냥꾼·삼프로TV·주식하는형 ID가 있고 `/workers/youtube/channels/benchmark`도 구현되어 있다. 그러나 이 결과는 `Dashboard.jsx`의 `ChannelBenchmark`에서만 사용되며 `/longform`의 `DailyKeywordResearch` 후보 풀에는 합쳐지지 않는다. `지식한입`은 레지스트리에도 없다.

또한 `ChannelBenchmark.jsx`에는 API 응답 누락 시 표시될 수 있는 하드코딩 구독자 수가 있다. 실제 API 값을 못 받으면 `정보 없음`으로 보여야 하며 임의 수치를 대체값으로 사용하지 않아야 한다.

권장 레지스트리:

```yaml
reference_channels:
  - channel_id: "UC7usMJDHmtbs_oegmzQKKMA"
    display_name: "경제사냥꾼"
    roles: ["format_reference", "economy_topic_source"]
    enabled: true
  - handle: "@관리자가_검증한_지식한입_핸들"
    channel_id: null
    display_name: "지식한입"
    roles: ["format_reference", "knowledge_explainer"]
    enabled: false
    verification_status: "PENDING"
```

채널 ID는 추측하거나 검색 결과 첫 항목으로 확정하지 않는다. 관리자가 URL/핸들을 입력하면 `channels.list(forHandle=...)`로 해석하고, 반환 제목·썸네일을 확인한 뒤 `VERIFIED`로 전환한다. 공식 문서상 `forHandle`을 지원한다.

### 3.6 롱폼/Shorts 분류와 성과 비교가 섞임

현재 UI는 `durationSeconds > 60`이면 롱폼으로 표시한다(`DailyKeywordResearch.jsx:73-89`). 하지만 Shorts는 최대 3분까지 가능하다. 또한 2025-03-31부터 Shorts의 `viewCount`는 재생 또는 반복 재생 시작 기준으로 바뀌어 일반 영상과 단순 비교하면 안 된다.

권장 정책:

- 롱폼 리서치 검색은 `videoDuration=medium`(4~20분)과 `videoDuration=long`(20분 초과)을 사용하거나 수집 후 `duration_seconds >= 240`을 적용한다.
- 3분 이하 영상은 Shorts 가능성이 있으므로 롱폼 후보에서 제외한다.
- 3~4분 구간은 `format=AMBIGUOUS_SHORT_VIDEO`로 두고 자동 성과 비교에서 제외한다.
- Data API만으로 Shorts 피드 분류를 완벽하게 확인할 수 없으므로 `is_short`를 확정값처럼 만들지 않는다.
- Shorts는 별도 화면·별도 기준선에서만 비교한다.

### 3.7 채널 평균 조회수 기준선이 적절하지 않음

현재 `channel_avg_views = channels.statistics.viewCount / videoCount`를 계산한다(`trending.py:450-460`). 이는 채널 전체 기간, Shorts, 라이브, 삭제·비공개 변화, 조회 집계 정의 변화를 모두 섞는다. 레퍼런스 영상 한 편이 최근 평소보다 잘 됐는지 판단하는 기준으로 적합하지 않다.

권장 기준선:

- 채널 업로드 재생목록에서 최근 20~30개를 가져온다.
- 비라이브, 동일 포맷(4~20분/20분+), 같은 연령 구간만 남긴다.
- 평균보다 이상치에 강한 **중앙값**을 사용한다.
- 게시 6h/24h/72h/7d 시점의 조회 스냅샷을 저장해 같은 시점끼리 비교한다.
- 과거 스냅샷이 없으면 `baseline_status=INSUFFICIENT_HISTORY`로 표시하고 임의 배수를 만들지 않는다.

---

## 4. 2026년 기준 YouTube Data API 사용 설계

### 4.1 공식 사양에서 반영해야 할 변경점

1. `search.list`는 2026-06-01부터 별도 검색 쿼터 버킷을 사용하며, 기본 100회/일, 호출당 1이다. 현재 `_consume_quota(..., 100, "search.list")`와 6,400 소프트 리밋은 구형 모델이다.
2. `videos.list`, `channels.list`, `playlistItems.list`, `commentThreads.list`는 일반적으로 호출당 1이며 배치 조회가 가능하다.
3. `search.list.relevanceLanguage=ko`는 한국어 결과만 보장하지 않는다. 공식 문서도 관련성이 높으면 다른 언어가 반환될 수 있다고 명시한다. 따라서 제목·설명·태그의 한국어 비율과 금융 용어 관련성을 후처리해야 한다.
4. `regionCode=KR`은 KR에서 볼 수 있는 결과를 지정하지 한국 채널만 지정하지 않는다.
5. 채널 구독자 수는 세 자리 유효숫자로 내림된 근사값이며 `hiddenSubscriberCount`를 별도로 처리해야 한다.
6. 타 채널의 평균 시청시간·시청률·노출·썸네일 CTR은 Data API 키만으로 받을 수 없다. YouTube Analytics/Reporting API 데이터는 채널 또는 콘텐츠 소유자의 승인 범위다.
7. 공개 비인증 API 데이터는 30일을 넘겨 저장하지 말고 삭제 또는 갱신하는 정책을 적용해야 한다.

공식 문서:

- [search.list 파라미터·쿼터](https://developers.google.com/youtube/v3/docs/search/list)
- [2026-06 세분화 쿼터 변경 이력](https://developers.google.com/youtube/v3/revision_history)
- [쿼터 계산기](https://developers.google.com/youtube/v3/determine_quota_cost)
- [videos.list](https://developers.google.com/youtube/v3/docs/videos/list)
- [video 리소스와 2025 Shorts 조회 정의](https://developers.google.com/youtube/v3/docs/videos)
- [channels.list와 forHandle](https://developers.google.com/youtube/v3/docs/channels/list)
- [channel 구독자 수 근사 규칙](https://developers.google.com/youtube/v3/docs/channels)
- [YouTube Analytics 메트릭](https://developers.google.com/youtube/analytics/metrics)
- [Analytics/Reporting 데이터 소유자 승인](https://developers.google.com/youtube/reporting)
- [3분 Shorts 기준](https://support.google.com/youtube/answer/15424877)
- [API 데이터 저장·갱신 정책](https://developers.google.com/youtube/terms/developer-policies)

### 4.2 권장 수집 경로 A: 일반 주제 탐색

하나의 광범위한 `q=주식` 검색으로 끝내지 말고 쿼리 계획을 만든다.

```text
사용자 입력/오늘 뉴스 엔티티
  → 엔티티 정규화(삼전→삼성전자, SK하닉→SK하이닉스)
  → 2~4개 검색식 생성
  → search.list(type=video, KR, ko, 최근 7일, medium/long)
  → videos.list 배치 보강
  → channels.list 배치 보강
  → 언어·금융 관련성·라이브·기간·포맷 후처리
  → 연령/포맷/채널규모 코호트별 표시
```

검색식 예시:

```text
"반도체 전망" | "삼성전자 반도체" | "SK하이닉스 HBM" -shorts -shortvideo
```

`q`의 OR·NOT 연산은 공식 지원하지만 `-shorts`는 메타데이터 문자열을 줄이는 보조 수단일 뿐 Shorts 자체를 완벽히 제외하지 못한다. 최종 포맷 필터는 `contentDetails.duration`으로 수행한다.

권장 요청:

```http
GET /youtube/v3/search
  ?part=snippet
  &type=video
  &q=<정규화 검색식>
  &regionCode=KR
  &relevanceLanguage=ko
  &publishedAfter=<UTC RFC3339, 7일 전>
  &videoDuration=medium
  &order=relevance|viewCount|date
  &maxResults=50
```

`medium`과 `long`을 각각 호출하면 4분 이상 롱폼을 안정적으로 모을 수 있다. 쿼터가 빠듯하면 `videoDuration=any` 한 번 후 `duration>=240`으로 후처리한다. `order`는 탭 목적에 따라 고정한다.

- 관련 영상: `relevance`
- 최근 업로드: `date`
- 이미 반응이 큰 영상: `viewCount`

### 4.3 권장 수집 경로 B: 등록 레퍼런스 채널

등록 채널은 `search.list(q=...)`에 의존하지 않는다.

```text
채널 레지스트리
  → channels.list(id=batch, part=snippet,statistics,contentDetails)
  → contentDetails.relatedPlaylists.uploads 확보
  → playlistItems.list(채널별 최근 20~30개)
  → 모든 video_id를 videos.list로 최대 50개씩 배치
  → 비라이브·4분 이상·최근 30일 필터
  → 오늘 뉴스/사용자 쿼리와 의미 관련성 계산
  → 레퍼런스 채널 카드로 노출
```

이 경로는 등록 채널이 검색 결과에서 밀려나도 항상 수집된다. 현재 구현처럼 채널마다 `channels.list + playlistItems.list + videos.list`를 순차 호출하지 말고 `channels.list`와 `videos.list`는 가능한 범위에서 배치한다.

### 4.4 권장 쿼터 예산

2026년 세분화 버킷을 기준으로 계수를 분리한다.

```yaml
youtube_quota:
  search_calls_per_day_soft: 80
  search_calls_per_day_hard: 95
  general_units_per_day_soft: 8000
  general_units_per_day_hard: 9500
```

예시 일일 계획:

| 작업 | 횟수 | 대략 비용 |
|---|---:|---:|
| 국내 주제 시드 4개 × medium/long | 8회 | 검색 버킷 8회 |
| 미국 주제 시드 2개 × medium/long | 4회 | 검색 버킷 4회 |
| 수동 검색 여유 | 40회 | 검색 버킷 40회 |
| 레퍼런스 채널 10개 업로드 목록 | 10회 | 일반 10유닛 |
| 채널·영상 배치 보강 | 약 5~10회 | 일반 5~10유닛 |

현재처럼 검색 한 번을 내부 100으로 차감하면 실제 검색 버킷과 내부 카운터가 불일치한다. Redis 키도 다음처럼 분리한다.

```text
youtube:quota:search:2026-08-14 = 12
youtube:quota:general:2026-08-14 = 24
```

동시 새로고침에는 분산 락과 single-flight를 적용한다. 실행 로그에서 같은 job의 키워드 탐색과 같은 검색이 중복 실행된 흔적이 있으므로 `job_id + seed + category + config_version` 멱등 키가 필요하다.

---

## 5. 새로운 후보 점수·게이트 설계

### 5.1 “100점”보다 먼저 판정할 증거 게이트

```text
G1 직접 관련성: 제목/설명/태그 또는 기사 본문에서 핵심 엔티티 일치
G2 최신성: 주제 유형별 허용 시간창 충족
G3 출처 계보: 기사 URL 또는 video_id가 후보에 연결
G4 수치 안전: 수치 주장이 있으면 1차 데이터와 일치, 없으면 N/A
G5 자동 승인: 최소 뉴스/공시 근거와 후보 직접성 충족
```

게이트 실패는 점수 0이 아니라 상태로 반환한다.

```json
{
  "evidence_status": "INSUFFICIENT",
  "auto_confirm_eligible": false,
  "blocking_reasons": ["NO_DIRECT_NEWS", "NO_RELEVANT_LONGFORM_VIDEO"],
  "evidence_score": null,
  "coverage": {"news": false, "youtube": false, "market": true}
}
```

### 5.2 권장 점수표: YouTube와 외부 금융 근거를 한 숫자로 합치지 않음

YouTube 개발자 정책은 YouTube API 데이터와 다른 출처의 데이터를 함께 보여 줄 때 출처 차이를 명확히 하도록 요구하고, 채널 간 경쟁을 조장하는 임의 점수에도 제한을 둔다. 따라서 현재처럼 뉴스·시장·YouTube를 한 개의 100점으로 합치는 모델을 폐기하는 것이 안전하다.

금융 사실 근거는 별도의 `evidence_score`로 정렬한다. 이 점수에는 YouTube 수치를 넣지 않는다.

| 금융 근거 항목 | 최대 | 계산 근거 |
|---|---:|---|
| 직접 뉴스·공시 근거 | 50 | 직접 일치 기사 수, 서로 다른 출처, 최신성, 1차 출처 가산 |
| 시장 맥락 연결 | 25 | 해당 종목·지수·환율 등 실제 수집 필드가 주제와 직접 연결 |
| 시의성·모멘텀 | 15 | 24h/7d 뉴스 빈도, 일정·공시 최신성 |
| 최근 제작 중복 억제 | 10 | 내부 제작 이력과의 중복 감점 |

YouTube는 같은 카드 안의 별도 패널로 제공한다.

```text
YouTube 레퍼런스: 관련 롱폼 2건 · 등록 채널 1곳
정렬 기준: 게시 24시간 조회수
원본: 조회 12,345 · 구독자 약 64만 · 게시 18시간
단순 비율: 구독자 대비 조회 1.9%
```

사용자는 `관련성`, `최신 업로드`, `조회수`, `구독자 대비 조회율` 중 한 기준을 선택해 정렬한다. 서로 다른 출처를 섞은 “종합 성과 점수”와 불투명한 S/A/B/C 등급은 기본 UI에서 제거한다.

수치 주장은 별도 게이트다.

- 수치 없음: `numeric_verification=NOT_APPLICABLE`, 점수 없음
- 모든 수치 검증: `PASSED`
- 하나라도 불일치 또는 출처 없음: `FAILED`, AUTO 금지

금융 근거 점수와 함께 데이터 완전도를 표시한다.

```text
금융 근거 68/100 · 금융 근거 완전도 80%
뉴스 3건/3개 매체 · 시장 데이터 있음 · 수치 N/A
YouTube 레퍼런스 2건/2개 채널 · 별도 공개 지표 확인
```

직접 금융 근거가 없는 경우 점수를 억지로 비교하지 말고 다음처럼 보여 준다. YouTube가 없으면 금융 근거 점수는 유지하되 `YouTube 레퍼런스 없음`을 별도 표시한다.

```text
금융 근거 점수 산정 보류 · 완전도 40%
시장 맥락만 확인됨 · 직접 뉴스/공시를 찾지 못함
YouTube 레퍼런스 없음
```

### 5.3 YouTube 공개 반응 수치

표시 가능한 원본:

- 조회수, 좋아요 수(제공된 경우), 댓글 수(제공된 경우)
- 게시 시각, 길이, 채널 구독자 수(근사), video_id

표시 가능한 단순 파생값:

- `views_per_subscriber = views / subscribers`
- `views_per_hour = views / max(age_hours, floor)`
- `like_rate = likes / views`
- `comment_rate = comments / views`
- `relative_to_recent_channel_median = views_at_bucket / median(recent_same_format_views_at_bucket)`

안전장치:

- 게시 6시간 미만은 `EARLY`로 표시하고 성과 확정 금지
- 숨김 구독자이면 구독자 대비 지표 계산 금지
- 좋아요/댓글 필드가 없으면 0이 아니라 `unavailable`
- Shorts와 일반 영상 비교 금지
- 서로 다른 게시 연령의 단순 `views/hour` 순위 금지
- S/A/B/C처럼 의미가 불투명한 등급보다 원본 비율과 비교 코호트를 노출
- YouTube 정책상 파생 지표는 원본과 계산식을 명확히 보여 주고, 채널 간 경쟁을 조장하는 점수화가 아닌 내부 탐색 보조임을 법무·정책 검토

---

## 6. 화면별 변경안

### 6.1 `/longform/new` 유튜브 트렌드 검색

현재 한 줄 카드에는 제목, 조회수, 구독자 대비 배수만 있어 외국어 Shorts가 왜 포함됐는지 판단하기 어렵다.

권장 UI:

- 기본 모드: `관련 롱폼`, `등록 레퍼런스 채널`, `최근 급상승` 탭
- 필터: 최근 24시간/7일/30일, 4~20분/20분+, 한국어, 비라이브
- 카드: 썸네일, 제목, 채널, 게시시각, 길이, 원본 조회수, 구독자 근사, 동일 코호트 비교, 관련성 근거
- “주제로 가져오기”와 “레퍼런스로 추가”를 분리
- 검색 결과가 0이면 공급자 오류/필터 탈락/실제 0건을 구분해 표시
- 외국어 결과는 `relevanceLanguage`만 믿지 말고 한국어 문자 비율·금융 엔티티 후처리

`JobNew.jsx:118-133`의 호출은 현재 `ranking`, `minSubscribers`, `recentHours`, `duration`, `language`, `sourcePool`을 보내지 않는다. 새 API 계약을 통해 명시적으로 전달한다.

### 6.2 `/longform` 오늘의 분석

현재 일일 시드는 `코스피`, `코스닥`, `미국 주식` 세 개뿐이다(`DailyKeywordService.java:78-91`). 너무 넓은 시드라 라이브·속보·무관 채널이 많이 섞인다.

권장 일일 분석 순서:

1. 08:30~08:50: RSS/Naver/공시/시장 캘린더에서 엔티티와 사건 추출
2. 08:50: `기업/산업/시장/거시`별 2~3개 검색식 생성
3. 09:00: 일반 롱폼 검색과 레퍼런스 채널 업로드 수집 병렬 실행
4. 09:02: 기사·영상 중복 제거와 증거 ID 연결
5. 09:03: 금융 근거 게이트 통과 후보만 금융 근거 점수화, YouTube는 별도 지표로 정렬
6. UI에 `수집 완료 시각`, `검색식`, `탈락 사유 집계`, `쿼터 상태` 표시

일일 화면은 최소 다음 섹션을 분리한다.

- 오늘 뉴스·공시 기반 주제
- YouTube에서 반응 중인 관련 롱폼
- 등록 레퍼런스 채널의 최근 형식
- 근거 부족 보류 후보

마인드맵은 영상 제목·태그 공통어만으로 후보를 만들지 말고, 각 노드에 최소 하나의 `news_evidence_id` 또는 `youtube_evidence_id`를 요구한다.

### 6.3 `/longform/{jobId}` 후보 카드

현재 `뉴스 근거 없음 — 시장 데이터 기반 추정`이라고 쓰면서 총점과 자동 선택을 함께 보여 준다. 다음 상태 모델로 바꾼다.

```text
확인됨        직접 뉴스/공시 및 관련 영상 근거가 기준 충족
부분 확인     한 종류의 직접 근거만 있음, 수동 선택 가능
근거 부족     시장 맥락만 있음, 자동 선택 불가
수집 실패     공급자 오류 또는 쿼터/타임아웃, 재시도 가능
```

카드에는 “뉴스 0건”뿐 아니라 검색식과 실패 원인을 표시한다.

```text
뉴스: 0건 · 검색 성공, 직접 일치 없음
YouTube: 0건 · 37건 수집, 35건 포맷/관련성 탈락, 2건 게시 초기
시장: KOSPI·USD/KRW 스냅샷 확인
자동 선택: 불가 — 직접 근거 부족
```

---

## 7. 권장 데이터 계약

### 7.1 YouTube 영상 증거

```json
{
  "video_id": "...",
  "channel_id": "...",
  "channel_title": "...",
  "channel_role": "REFERENCE|DISCOVERY|OTHER",
  "title": "...",
  "description_excerpt": "...",
  "published_at": "2026-08-14T00:00:00Z",
  "duration_seconds": 842,
  "format_bucket": "MEDIUM_LONGFORM",
  "is_live": false,
  "language_match": "KO_CONFIRMED",
  "views": 12345,
  "likes": 321,
  "likes_available": true,
  "comments": 45,
  "comments_available": true,
  "subscribers": 640000,
  "subscriber_count_available": true,
  "statistics_as_of": "2026-08-14T01:00:00Z",
  "matched_terms": ["반도체", "HBM"],
  "source_query_id": "ytq_..."
}
```

### 7.2 뉴스 증거

```json
{
  "news_evidence_id": "news_...",
  "canonical_url": "https://...",
  "title": "...",
  "publisher": "...",
  "published_at": "2026-08-14T00:10:00Z",
  "retrieved_at": "2026-08-14T01:00:00Z",
  "source_type": "PRIMARY|MAJOR_MEDIA|AGGREGATOR",
  "matched_entities": ["삼성전자", "SK하이닉스", "HBM"],
  "matched_claims": [],
  "content_hash": "sha256:..."
}
```

### 7.3 후보 감사 정보

```json
{
  "candidate_id": "cand_...",
  "topic": "...",
  "evidence_status": "CONFIRMED|PARTIAL|INSUFFICIENT|COLLECTION_FAILED",
  "auto_confirm_eligible": false,
  "evidence_score": null,
  "evidence_score_max": 100,
  "coverage_pct": 40,
  "evidence_score_components": {},
  "numeric_verification": "NOT_APPLICABLE|PASSED|FAILED",
  "news_evidence_ids": [],
  "youtube_evidence_ids": [],
  "market_snapshot_ids": ["..."],
  "blocking_reasons": ["NO_DIRECT_NEWS", "NO_RELEVANT_LONGFORM_VIDEO"],
  "config_version": "keyword-research-v2",
  "collected_at": "2026-08-14T01:00:00Z"
}
```

---

## 8. 파일별 구현 작업

### P0: 잘못된 자동 선택과 수집 실패 제거

1. `backend/fastapi-workers/app/providers/real/trending.py`
   - `recent_hours=None → 1` 버그 수정
   - 2026 검색 쿼터 카운터 분리
   - `videoDuration`, 언어 후처리, 포맷 버킷 추가
   - 오류 시 빈 배열만 반환하지 말고 `provider_status/error_code` 반환
2. `backend/fastapi-workers/app/workers/news_keyword_extractor.py`
   - `_fetch_naver_news()`의 `articles=[]` 추가
   - 기사 ID·URL·발행시각 계보 보존
   - 중복 제거 및 공급자 성공/0건/오류 구분
3. `backend/fastapi-workers/app/workers/keyword_worker.py`
   - AUTO의 `auto_confirmable=True` 강제 삭제
   - LLM이 증거 ID 없는 후보를 반환하면 제외
   - 입력 시드는 관련성 제약으로 유지하되 증거 없는 세부 각도는 자동 후보로 확정 금지
4. `backend/fastapi-workers/app/utils/candidate_scoring.py`
   - YouTube 결측 재가중 삭제
   - `numeric_claims_verified=None`에 7점 부여 삭제
   - 시장 관련성과 수치 검증을 다른 필드로 분리
   - `evidence_score=null`, `coverage`, `blocking_reasons` 계약 추가
5. `backend/spring-app/.../KeywordService.java`
   - 중복 `isEmpty()` 분기 수정
   - 실제 `selection_path`와 설명 일치
   - `autoConfirmable=false`면 어떤 모드에서도 `confirm()` 호출 금지
6. `frontend/src/pages/JobDetail.jsx`
   - `100점 가중치 환산` 제거
   - 수치 없음은 `해당 없음` 표시
   - 증거 상태와 차단 사유를 총점보다 먼저 표시

### P1: 실제 레퍼런스 채널과 롱폼 탐색 연결

1. 레퍼런스 채널 레지스트리 저장소·관리 API 추가
2. 핸들→채널 ID 검증 흐름 추가
3. 업로드 재생목록 배치 수집 서비스 추가
4. `/keywords/daily`에 `newsTopics`, `discoveryVideos`, `referenceVideos`, `heldCandidates`, `diagnostics` 섹션 추가
5. `DailyKeywordService.java`의 고정 3시드를 뉴스·공시 엔티티 기반 쿼리 플래너로 교체 또는 보완
6. `DailyKeywordResearch.jsx`와 `JobNew.jsx`에 소스 풀·기간·길이·언어 필터 추가
7. `ChannelBenchmark.jsx`의 하드코딩 구독자 fallback 제거

### P2: 공정한 성과 비교와 운영성

1. 6h/24h/72h/7d 영상 통계 스냅샷 작업
2. 동일 포맷·연령·채널규모 코호트 비교
3. 최근 동일 포맷 중앙값 기준선
4. 검색·일반 쿼터 대시보드와 경보
5. single-flight·멱등 키·새로고침 잠금
6. 30일 비인증 YouTube 데이터 갱신/삭제 작업

---

## 9. 테스트 계획

### 단위 테스트

- `recent_hours=None`이면 정확히 168시간 `publishedAfter`를 만든다.
- `recent_hours=2`이면 2시간을 유지한다.
- 네이버 기사 3건 응답이 3건의 URL·시각 포함 증거로 변환된다.
- 뉴스 API 성공 0건과 예외가 다른 상태 코드를 낸다.
- YouTube 없음일 때 85점→100점 재환산이 발생하지 않는다.
- 수치 없는 후보는 `NOT_APPLICABLE`이고 점수가 없다.
- AUTO라도 직접 증거가 없으면 `auto_confirm_eligible=false`다.
- 61초·180초 영상은 롱폼으로 자동 확정하지 않는다.
- 숨김 구독자 채널은 구독자 대비 조회율을 계산하지 않는다.
- 등록 채널 영상은 일반 검색에 노출되지 않아도 레퍼런스 풀에 들어온다.

### 통합 테스트

고정 fixture로 다음 시나리오를 검증한다.

1. `반도체 전망` + 기사 3개 + 관련 롱폼 2개 → `CONFIRMED`, 자동 후보 가능
2. 시장 데이터만 있음 → `INSUFFICIENT`, 점수 보류, 자동 선택 불가
3. 네이버 장애 + Google RSS 정상 → `PARTIAL_PROVIDER_FAILURE`, 기사 근거 유지
4. YouTube 검색 장애 + 등록 채널 업로드 정상 → 레퍼런스 풀 유지, 일반 탐색 실패 표시
5. 외국어 Shorts 조회수 급등 → 롱폼 후보 제외
6. 구독자 50만 채널 게시 1시간·조회 500 → 제거하지 않고 `EARLY`, 성과 확정 보류
7. 동일 작업 요청 2회 → 외부 검색 한 번, 같은 결과 재사용

### UI 수용 기준

- `뉴스 0건 + YouTube 0건` 후보가 자동 선택되지 않는다.
- `수치 주장 없음` 옆에 22/35 같은 점수가 표시되지 않는다.
- “YouTube 미수집”과 “100점 가중치 환산”이 동시에 나타나지 않는다.
- 검색 결과 카드에서 채널, 게시시각, 길이, 근거 유형, 원본 링크를 확인할 수 있다.
- 레퍼런스 채널 관리자가 경제사냥꾼·지식한입 등 원하는 채널을 검증 등록할 수 있다.
- 등록 채널의 최근 일반 영상이 키워드 일반 검색 결과와 별도로 표시된다.
- 수집 0건일 때 `실제 0건/필터 탈락/공급자 실패/쿼터 차단`을 구분한다.

---

## 10. 배포 순서와 완료 기준

### 1차 핫픽스

- 최근 1시간 버그
- 네이버 `articles` 예외
- AUTO 강제 승인
- 결측 재가중과 수치 없음 점수
- Spring 선택 설명 분기

완료 기준: 제공된 `반도체 전망` 사례를 다시 실행했을 때 뉴스·YouTube 직접 근거가 없으면 `근거 부족`, `자동 선택 불가`, `점수 산정 보류`로 나온다.

### 2차 기능 보강

- 레퍼런스 채널 레지스트리
- 업로드 재생목록 기반 수집
- 롱폼 전용 검색
- 증거 ID 계보
- 화면별 진단 정보

완료 기준: 경제사냥꾼 등 검증 등록 채널의 최근 4분 이상 영상이 일반 검색 노출 여부와 무관하게 `/longform`과 `/longform/new`에서 조회된다.

### 3차 성과 모델

- 시점별 스냅샷
- 동일 코호트 비교
- 쿼터·캐시·보존 정책
- 오프라인 평가셋과 운영 대시보드

완료 기준: 30개 이상의 수동 라벨 주제에서 `관련 롱폼 정밀도`, `근거 링크 유효율`, `자동 선택 오탐률`, `검색 공급자 실패율`을 매일 확인할 수 있다.

권장 초기 품질 목표:

| 지표 | 목표 |
|---|---:|
| 상위 5개 관련 롱폼 정밀도 | 80% 이상 |
| 후보의 유효 뉴스/공시 링크 보유율 | 95% 이상 |
| 근거 없는 AUTO 선택률 | 0% |
| 등록 레퍼런스 채널 최신 영상 수집 성공률 | 98% 이상 |
| 공급자 오류를 정상 0건으로 오표시하는 비율 | 0% |

---

## 11. 개발 회의에서 결정해야 할 항목

1. 자동 선택의 최소 증거: `서로 다른 뉴스 2개`, `1차 출처 1개`, `뉴스 1개+관련 롱폼 2개` 중 어떤 조합을 허용할지
2. 레퍼런스 채널 목록과 각 채널의 역할: 사실 출처가 아니라 포맷 참고인지, 주제 수요 신호인지
3. 롱폼 최소 길이: 제품 기준을 4분 이상으로 둘지, 8분 이상으로 둘지
4. 게시 초기 영상의 보류 시간: 6시간 또는 12시간
5. 일일 검색 호출 예산과 수동 검색 예약량
6. 뉴스 1차 출처 우선순위: DART/KRX/기업 IR/한국은행/정부통계/SEC/Fed 등
7. 기존 S/A/B/C 등급을 제거할지, 내부 전용으로 유지하되 원본 수치와 계산식을 함께 보여 줄지

---

## 최종 권고

이번 개선의 핵심은 “더 많은 YouTube 검색”이 아니다. **뉴스·공시로 사실을 확정하고, YouTube는 검증된 채널과 관련 롱폼에서 주제 수요·포맷을 관찰하며, 둘의 원본 ID를 후보에 묶는 것**이다. 먼저 P0 핵심 원인을 제거하고, 다음으로 레퍼런스 채널 업로드 경로를 `/longform` 후보 풀에 연결해야 한다. 그 뒤에야 성과 가중치나 대형 채널 임계값을 튜닝하는 것이 의미가 있다.

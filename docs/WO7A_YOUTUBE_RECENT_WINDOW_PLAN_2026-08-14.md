# WO-7A 작업 계획서: YouTube 롱폼 리서치 기본 수집 기간 7일 복구

- 작성일: 2026-08-14 (KST)
- 기준 코드: `de40a3f` (`origin/main`)
- 참고 문서: `docs/DEVELOPER_BRIEF_YOUTUBE_LONGFORM_RESEARCH_REDESIGN_2026-08-14.md`
- 이번 작업 대상: YouTube API 활용 개선 1번의 첫 번째 문제만 처리
- 구현 상태: 구현·전체 회귀 완료, 커밋 전

## 1. 이번 작업의 단일 목표

`YouTubeTrendingAnalyzer.collect()`에 `recent_hours=None`이 들어왔을 때 현재 1시간으로 변환되는 버그를 수정한다.

변경 후 계약은 다음과 같다.

```text
recent_hours=None  -> 168시간(최근 7일)
recent_hours=2     -> 2시간 유지
recent_hours=0     -> 1시간으로 하한 보정
recent_hours=999   -> 168시간으로 상한 보정
```

이번 WO에서는 이 계약 외의 YouTube·뉴스·후보 점수·AUTO 승인 문제를 함께 수정하지 않는다.

## 2. 왜 이 문제를 가장 먼저 고치는가

현재 호출 계보는 다음과 같다.

```text
React `/longform/new` 또는 `/longform`
  -> Spring `TrendingController`
  -> `TrendingService`
  -> `FastApiClient.getTrendingVideos()`
     (`recent_hours`를 보내지 않음)
  -> FastAPI `TrendingRequest.recent_hours=None`
  -> `YouTubeTrendingAnalyzer.collect()`
  -> 현재 코드가 None을 1로 변환
  -> `search.list.publishedAfter=현재-1시간`
```

UI는 최근 7일을 수집한다고 표시하지만 실제 기본 검색은 최근 1시간만 조회한다. 이 상태에서는 검색어·필터·점수 가중치를 조정해도 후보 풀이 지나치게 작아서 정확한 평가가 불가능하다.

이 수정은 다음 장점이 있다.

- YouTube API 요청 기간만 바로잡는다.
- 스크립트·이미지·TTS·자막·Fal·조립 코드와 완전히 분리된다.
- 외부 API를 실제 호출하지 않고 단위 테스트로 검증할 수 있다.
- 기존 `recent=1` Redis 캐시와 수정 후 `recent=168` 캐시 키가 달라 잘못된 캐시를 재사용하지 않는다.

## 3. 공식 API 사양 확인

계획 수립 시 다음 공식 문서를 확인했다.

- YouTube Data API 개요: 2026년 기본 할당량은 `search.list` 100회/일, `videos.insert` 100회/일, 그 외 엔드포인트 합계 10,000유닛/일로 분리되어 있다.
  <https://developers.google.com/youtube/v3/getting-started>
- 2026-06-01 변경 이력: `search.list`와 `videos.insert`가 각자 별도 세분화 쿼터 버킷으로 전환됐다.
  <https://developers.google.com/youtube/v3/revision_history>
- `search.list`: `publishedAfter`는 RFC 3339 시각을 받으며, `videoDuration=medium`은 4~20분, `long`은 20분 초과다.
  <https://developers.google.com/youtube/v3/docs/search/list>

이번 WO는 수집 기간만 수정한다. 세분화 쿼터와 `videoDuration` 적용은 각각 별도 WO로 처리한다.

## 4. `final (6)`에서 유지해야 할 품질 하한선

`final plan/final (6).mp4`와 job 181 산출물을 확인한 결과, YouTube 리서치 변경과 무관하게 다음 계약은 그대로 유지해야 한다.

| 항목 | job 181 확인값 | WO-7A 원칙 |
|---|---:|---|
| 영상 | 1920×1080, 30fps, 54.70초 | 재생성하지 않음 |
| 장면 이미지 | 11개 | 이미지 단계 호출 금지 |
| 이미지 스타일 | `editorial_comic_2d` | 관련 코드 변경 금지 |
| TTS | ElevenLabs, 속도 0.9 | TTS 단계 호출·설정 변경 금지 |
| TTS 원문 정합 | canonical hash 일치 | 대본·TTS 입력 변경 금지 |
| 자막 | 40개, 원문 일치·싱크 통과 | 자막 코드 변경 금지 |
| 모션 | 계획 2개, 실제 2개 | Fal/Kling 코드 변경 금지 |
| 최종 QC | 100점, 통과 | 조립·QC 코드 변경 금지 |

`final (6)`에서 확인되는 화면 속 영문·수치 오탈자와 내레이션 수치 불일치는 인지하되, 이는 요청 3번의 별도 작업 대상이다. WO-7A에 섞지 않는다.

## 5. 현재 코드의 정확한 결함

대상 코드:

```python
# backend/fastapi-workers/app/providers/real/trending.py
recent_hours = max(1, min(int(recent_hours or 0), 168)) or None
```

`None`이 다음 순서로 1이 된다.

```text
None -> 0 -> min(0, 168) -> max(1, 0) -> 1
```

이후 `_collect_keyword_search()`는 전달받은 `1`을 사용한다.

```python
published_after = now - timedelta(hours=recent_hours or 24 * 7)
```

따라서 함수 내부에 작성된 7일 fallback은 실행되지 않는다.

## 6. 허용 수정 범위

### 제품 코드

- `backend/fastapi-workers/app/providers/real/trending.py`

### 테스트 코드

- 신규 권장: `backend/fastapi-workers/tests/test_youtube_trending_recent_window.py`

### 이번 WO에서 수정하지 않을 파일

- `backend/fastapi-workers/app/main.py`
  - `de40a3f`에 포함된 Docker `.env` 기동 보정은 유지하고 이번 YouTube 수정과 혼합하지 않는다.
- `backend/spring-app/**`
- `frontend/**`
- `backend/fastapi-workers/app/workers/keyword_worker.py`
- `backend/fastapi-workers/app/utils/candidate_scoring.py`
- `backend/fastapi-workers/app/workers/news_keyword_extractor.py`
- 이미지·TTS·자막·Fal/Kling·조립 관련 모든 파일

## 7. 구현 설계

### 7.1 정규화 함수를 분리한다

기간 계약이 한 줄 표현식에 다시 묻히지 않도록 작은 순수 함수를 둔다.

권장 의미:

```python
def _normalize_recent_hours(recent_hours: int | None) -> int:
    if recent_hours is None:
        return 24 * 7
    return max(1, min(int(recent_hours), 24 * 7))
```

`collect()`는 외부 호출이나 캐시 조회 전에 이 함수를 한 번만 적용한다.

```python
recent_hours = _normalize_recent_hours(recent_hours)
```

### 7.2 캐시 키에 실제 정규화 값을 사용한다

수정 후 기본 캐시 키는 반드시 다음 의미를 가져야 한다.

```text
...:recent=168
```

`recent='7d'` 같은 별칭과 숫자 `168`을 혼용하지 않는다. 동일한 요청이 같은 키를 사용해야 한다.

### 7.3 검색 요청에 정규화 값을 그대로 전달한다

`_collect_keyword_search()`에 `168`이 전달되어 `publishedAfter`가 정확히 최근 7일 범위를 가리키게 한다.

이번 WO에서는 `videoDuration`, 검색식 확장, 언어 후처리, 소스 풀을 추가하지 않는다.

### 7.4 운영 로그에 기간을 남긴다

비밀값 없이 다음 정보만 구조적으로 확인할 수 있어야 한다.

```text
YouTube search window: requested=None normalized=168
```

API 키와 전체 요청 URL은 로그에 남기지 않는다.

## 8. 테스트 설계

외부 YouTube API를 실제 호출하지 않고 `requests.get` 또는 `_collect_keyword_search()`를 대체한다.

### 테스트 1: 기본값

```text
입력: recent_hours=None
기대: _collect_keyword_search(..., recent_hours=168)
```

### 테스트 2: 명시값 유지

```text
입력: recent_hours=2
기대: 2
```

### 테스트 3: 경계값

```text
입력: 0   -> 1
입력: 168 -> 168
입력: 999 -> 168
```

### 테스트 4: 실제 검색 파라미터

고정 시각 또는 허용 오차를 사용해 `search.list`에 전달되는 `publishedAfter`가 현재 시각 기준 약 168시간 전인지 확인한다.

다음은 검증하지 않는다.

- 검색 결과의 품질 점수
- AUTO 승인 여부
- 뉴스 결과
- 레퍼런스 채널
- 영상 생성 결과

## 9. 검증 명령

```bash
cd backend/fastapi-workers

# 신규 기간 계약
python -m pytest tests/test_youtube_trending_recent_window.py -v

# 인접 YouTube·키워드 계약
python -m pytest \
  tests/test_keyword_source_threshold.py \
  tests/test_candidate_scoring.py \
  tests/test_candidate_scoring_enhancements.py \
  tests/test_news_keyword_extractor.py \
  -q --tb=short

# FastAPI 전체 회귀
python -m pytest tests/ -q --tb=short
```

완료 보고에는 다음을 첨부한다.

- 신규 테스트 로그
- 인접 회귀 로그
- 전체 테스트 로그
- `git diff --check`
- 실제 diff
- 수정 파일 목록

FastAPI의 마지막 공식 전체 회귀 기준은 `526 passed, 0 failed`다. `de40a3f`의 기동·인증 보정까지 포함한 현재 HEAD에서 먼저 동일 기준을 재확인하고, WO-7A 완료 시에는 신규 테스트 수만큼 passed가 증가하며 failed는 0이어야 한다.

## 10. 수용 기준

- `recent_hours=None`이 168로 정규화된다.
- Spring이 `recent_hours`를 보내지 않아도 최근 7일을 검색한다.
- `recent_hours=2` 같은 수동 검색 계약은 그대로 유지된다.
- 기본 Redis 캐시 키에 `recent=168`이 기록된다.
- 외부 YouTube 호출을 하지 않는 테스트로 요청 파라미터가 검증된다.
- 후보 점수·AUTO 승인·뉴스·UI 동작은 변경되지 않는다.
- 스크립트·이미지·TTS·자막·Fal/Kling·조립 파일에는 diff가 없다.
- job 181 또는 `final (6)`를 재생성하지 않는다.

## 11. 실패 및 롤백 기준

다음 중 하나라도 발생하면 WO-7A를 완료로 보지 않는다.

- 기본 검색이 여전히 1시간을 사용함
- 명시적인 2시간 검색이 168시간으로 덮어써짐
- 기존 키워드·후보 점수 테스트가 변경됨
- 영상 생성 단계가 실행됨
- 허용 범위 밖 파일이 수정됨

롤백은 `trending.py`와 신규 테스트 파일만 대상으로 한다. 기존 사용자 변경이나 미커밋 파일에는 손대지 않는다.

## 12. 후속 작업 — 이번에는 구현하지 않음

다음 문제는 WO-7A 승인 후 하나씩 별도 조사·계획·수정한다.

1. `search.list`와 일반 API의 2026 세분화 쿼터 카운터 분리
2. 롱폼 검색의 `videoDuration=medium|long` 및 4분 경계 계약
3. 공급자 오류·실제 0건·필터 탈락 상태 분리
4. 검증된 레퍼런스 채널의 업로드 재생목록 수집
5. YouTube 결측 재가중 제거와 금융 근거 점수 분리
6. AUTO 모드의 근거 없는 강제 승인 제거
7. 공개 API 데이터 30일 갱신·삭제 정책

각 후속 WO 역시 스크립트·이미지·TTS·자막 품질 하한선을 변경하지 않는 추가 경로로 구현한다.

## 13. 구현 및 검증 결과

- 착수 전 전체 회귀: `526 passed, 0 failed, 13 warnings`
- 신규 기간 계약: `8 passed`
- 인접 키워드·뉴스·점수 회귀: `19 passed`
- 구현 후 전체 회귀: `534 passed, 0 failed, 13 warnings`
- 순변화: `+8 passed`, 실패 변화 없음
- 기존 `search.list` 쿼터 호출: `_consume_quota(..., 100, "search.list")` 유지
- 외부 YouTube API 실제 호출: 없음
- 영상·이미지·TTS·자막·Fal/Kling 재생성: 없음

Pillow 13 관련 경고 13건은 착수 전·후 동일하며 WO-7A에서 새로 발생하지 않았다.

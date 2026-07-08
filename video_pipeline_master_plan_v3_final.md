# video_pipeline 개발 마스터 플랜 v3 (최종 총정리)

작성일: 2026-07-08  
확정 사항: 캐릭터 = 금색 코인 카툰 캐릭터 / 이미지 모델 = gemini-3.1-flash-image  
이 문서는 v1(오전 계획), v2(현황 반영)를 모두 대체하는 단일 기준 문서입니다.

---

## 1. 프로젝트 목표

| 항목 | 내용 |
|---|---|
| 레퍼런스 채널 | 경제사냥꾼 (@경제사냥꾼) |
| 콘텐츠 대상 | KOSPI / KOSDAQ / 미국 주식 (개별 종목 + 시장 이슈 + 연관 종목군) |
| 핵심 차별점 | 모든 영상에 동일 캐릭터가 등장해 부담스러운 금융 정보를 친근하게 설명 |
| 영상 형식 | 롱폼(1080p 16:9) + 쇼츠(9:16 60초) |
| 자동화 수준 | MANUAL → GUIDED → AUTO 3단계 다이얼 |

---

## 2. 메인 캐릭터 확정 스펙

### 2.1 확정된 디자인 방향

- **몸통**: 금색 코인 (동그란 형태, 금빛 광택)
- **스타일**: 경제사냥꾼 채널의 지폐 캐릭터와 동급의 카툰 렌더링 — 이목구비(큰 눈, 입) + 손발이 있는 의인화
- **소품**: 지시봉 또는 돋보기 (정보를 "설명하는" 역할)
- **의상**: 작은 슈트 or 넥타이 (애널리스트 느낌)
- **렌더링**: 3D 느낌의 부드러운 애니메이션 카툰체
- **배경 컬러**: 네이비 (#0d1b2a) — 기존 파이프라인 테마와 통일

### 2.2 씬별 표정 5종 (캐릭터 시트에 포함할 것)

| 표정 코드 | 용도 | 씬 예시 |
|---|---|---|
| `neutral` | 기본 정보 전달 | 일반 설명 씬 |
| `highlight` | 강조/중요 포인트 | "핵심은 이겁니다" |
| `surprised` | 반전/충격 수치 | "이게 말이 됩니까" |
| `worried` | 리스크/경고 | "주의하셔야 합니다" |
| `happy` | 긍정/상승/결론 | "이런 기회입니다" |

### 2.3 캐릭터 생성 프롬프트 (Nano Banana 2 기준)

```
Character sheet for a cute gold coin mascot character, chibi cartoon style:
- Body: round shiny gold coin with face, arms and legs
- Eyes: large expressive cartoon eyes
- Outfit: small navy business suit with gold tie
- Prop: pointer stick in right hand
- Style: 3D render, smooth shading, anime cartoon
- Background: transparent / dark navy (#0d1b2a)
- Poses on one sheet: neutral, surprised, happy, worried, pointing-emphasis
- Consistent character design across all poses
- Reference: similar to cartoon money character from Korean finance YouTube
```

### 2.4 캐릭터 일관성 유지 방법 (코드 레벨)

현재 `image.py`의 `CHARACTER_STYLE`은 **텍스트 프롬프트만** 쓰고 있어서 씬마다 외모가 달라질 수 있습니다. Nano Banana 2의 레퍼런스 이미지 기능(최대 14장)을 활용해야 진짜 고정됩니다.

```python
# 현재 (문제 있음) — 텍스트 설명만으로 캐릭터 묘사
CHARACTER_STYLE = "featuring a cute cartoon money-hunter mascot..."

# 변경 후 (올바른 방법) — 확정된 캐릭터 시트 이미지를 레퍼런스로 전달
def _generate_gemini_api(self, prompt, output_path, api_key, character_ref_path=None):
    parts = [{"text": prompt}]
    
    # 캐릭터 레퍼런스 이미지가 있으면 함께 전달
    if character_ref_path:
        with open(character_ref_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        parts.insert(0, {
            "inlineData": {
                "mimeType": "image/png",
                "data": img_b64
            }
        })
    
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]}
    }
```

### 2.5 채널별 캐릭터 분리 (멀티채널 대응)

태호님 요청 사항 — 채널마다 다른 캐릭터를 쓸 수 있어야 함.

```sql
-- 추가할 테이블
CREATE TABLE channel_profiles (
    channel_id      VARCHAR(50) PRIMARY KEY,
    channel_name    VARCHAR(100),
    character_image_path VARCHAR(500),   -- 확정된 캐릭터 시트 이미지 경로
    character_style_prompt TEXT,          -- 보조 텍스트 설명
    voice_id        VARCHAR(100),         -- ElevenLabs voice_id
    created_at      TIMESTAMP DEFAULT NOW()
);
```

제작 시작 시 채널 선택 → 해당 캐릭터 이미지 + 보이스 자동 로드.  
"캐릭터 없이 만들기" 옵션도 제공 (character_image_path = NULL이면 레퍼런스 없이 생성).

---

## 3. 즉시 처리 필요 사항 (오늘 ~ 이번 주)

### 🔴 3.1 이미지 모델 교체 (오늘 당장)

현재 코드가 **2026-10-02 종료 예정인 레거시 모델**을 쓰고 있습니다.

```python
# image.py 현재 (레거시, 종료 예정)
url = f"...models/gemini-2.5-flash-image:generateContent?key={api_key}"

# 변경 후 (현행 GA 모델, 캐릭터 일관성 지원)
url = f"...models/gemini-3.1-flash-image:generateContent?key={api_key}"
```

코드 한 줄 변경입니다. 지금 바로 해야 합니다.

| 항목 | gemini-2.5-flash-image (현재) | gemini-3.1-flash-image (교체 후) |
|---|---|---|
| 상태 | 레거시, 2026-10-02 종료 예정 | GA 정식 출시 (2026-05-28) |
| 캐릭터 일관성 | 기본 수준 | 레퍼런스 이미지 최대 14장 지원 |
| 최대 해상도 | 1024px | 4K |
| 장당 가격 (1K) | $0.039 | $0.067 |

### 🔴 3.2 Kling → Fal.ai 마이그레이션 (이번 주)

현재 `video.py`의 Kling API가 401 에러로 정적 Zoompan 폴백 중.  
Fal.ai(https://fal.ai) 신용카드 등록 → API 키 발급 → `video.py` 래퍼 교체.

### 🟡 3.3 ElevenLabs 발음 사전 권한 (이번 주)

ElevenLabs 대시보드 → API Keys → 해당 키 편집 → `pronunciation_dictionaries_write` 체크 → 저장.

### 🟡 3.4 Claude 모델 버전 확인 (오늘)

`script_worker.py`에서 실제 model 파라미터 값 확인.  
반드시 `claude-sonnet-4-6` 이어야 합니다. 다른 값이면 즉시 교체.

---

## 4. Nano Banana 결제 방법 (단계별 상세)

### 4.1 현재 상황 파악

이미 5만원(약 $36)을 결제한 상태입니다.  
아래는 **추가 충전 및 올바르게 연결되어 있는지 확인하는 방법**입니다.

### 4.2 결제 상태 확인 방법

**Step 1.** https://aistudio.google.com 접속  
**Step 2.** 좌측 하단 또는 상단 메뉴에서 **"Billing"** 또는 **"Usage & Limits"** 클릭  
**Step 3.** 아래 내용을 확인:

| 확인 항목 | 정상이면 | 문제이면 |
|---|---|---|
| Billing Tier | "Paid" 또는 "Prepay" | "Free" → 아직 결제 미연결 |
| Credit Balance | 잔액이 표시됨 (예: $36.xx) | $0 → 충전 필요 |
| Rate Limit | RPM이 Free(2 RPM)보다 높음 | 2 RPM → 결제 미반영 |

**Step 4.** 모델 드롭다운에서 `gemini-3.1-flash-image` 가 목록에 보이면 정상.

### 4.3 추가 충전 방법 (잔액 소진 시)

<cite index="40-1">Gemini API는 **Prepay(선불) 방식**입니다. 크레딧을 미리 구매하면 API 사용량에서 실시간으로 차감되며, 잔액이 0이 되면 API 호출이 차단됩니다. 선불 크레딧은 환불되지 않으며 구매 후 1년 뒤 만료됩니다.</cite>

충전 경로:  
**AI Studio** → 좌측 메뉴 **Billing** → **"Add Credits"** → 금액 입력 → 카드 결제

또는:  
**Google Cloud Console** (https://console.cloud.google.com) → **결제** → **크레딧 구매**

> **주의**: 2026년 3월 이후로 Google Cloud의 $300 무료 체험 크레딧은 Gemini API에 사용할 수 없습니다. 반드시 별도 충전이 필요합니다.

### 4.4 5만원($36)으로 얼마나 쓸 수 있나

**이미지 생성 (메인 용도)**

| 모델 | 장당 가격 | $36으로 생성 가능 | 권장 용도 |
|---|---|---|---|
| gemini-3.1-flash-image (1K) | $0.067 | **537장** | 캐릭터 씬, 썸네일 |
| gemini-3.1-flash-image (2K) | $0.101 | **356장** | 고화질 씬 |
| gemini-2.5-flash-image (레거시, 1K) | $0.039 | 923장 | 대량 배경 이미지 |

영상 1편 기준 이미지 약 40~80장 → `gemini-3.1-flash-image`로 **7~13편 분량**.  
배경/차트 이미지는 레거시 모델($0.039)로 병행하면 **15~20편 이상** 가능.

**비용 절감 팁**: Batch API 사용 시 50% 할인 → 장당 $0.034로 내려감.  
단, Batch는 비동기(최대 24시간 대기)이므로 실시간 생성이 아닌 **야간 배치 생성**에 활용.

### 4.5 자동 충전(Auto-reload) 설정 권장

잔액 소진으로 파이프라인이 갑자기 멈추는 것을 방지하기 위해:  
**Billing** → **"Auto-reload"** 활성화 → 잔액이 특정 금액(예: $5) 이하로 떨어지면 자동 충전되도록 설정.

---

## 5. 목소리 품질 — AI 티 방지 (대표님 강조 사항)

### 5.1 현재 문제

- `tts_worker.py`는 gTTS + ElevenLabs 혼용 구조
- gTTS는 **기계음이 강해 시청자 이탈 직결** → 즉시 교체 대상
- `atempo=1.5` (50% 가속)은 원래 피드백("10~20% 빠르게")을 초과 → 확인 필요

### 5.2 ElevenLabs 전환 방향

| 항목 | 내용 |
|---|---|
| 권장 모델 | Eleven v3 (가장 자연스러운 감정 표현, 한국어 공식 지원) |
| 상업 이용 | Starter 플랜($5/월) 이상 필요 |
| 발음 사전 | FOMC, MACD 등 금융 약어 한국식 발음 정의 (`pronunciation_dictionaries_write` 권한 필요) |
| 속도 조정 | ElevenLabs 자체 speed 파라미터 우선 사용 → 피치 왜곡 없음 |
| 재조정 후 처리 | 속도 변경된 오디오로 **Whisper 재정렬 반드시 재실행** (자막 싱크 유지) |

### 5.3 작업자 미리듣기 UI (신규)

- 스크립트 확정 후 음성 생성 전에 **15~30초 샘플 미리듣기** 기능 추가
- 미리듣기 후 "다시 생성" 또는 "보이스 변경" 선택 가능
- voice_id 드롭다운: 캐릭터 보이스 후보 3~5개 제공

### 5.4 TTS 속도 확인 요청

현재 1.5배속(50% 가속)이 적용되어 있습니다.  
대표님 원래 피드백은 "10~20% 빠르게"였습니다.  
**청취 테스트 후 최종 확정 필요 — 임의 변경 금지.**

---

## 6. 현재 뜨는 주식 영상 순위 (신규 기능)

### 6.1 데이터 소스

```
YouTube Data API v3 — videos.list
파라미터: chart=mostPopular, regionCode=KR, videoCategoryId=25
쿼터 소모: 1유닛/호출 (search.list의 100유닛 대비 극히 저렴)
```

`videoCategoryId=25` = 뉴스/정치 카테고리 (YouTube에서 금융/경제와 가장 근접한 공식 카테고리)

### 6.2 캐싱 전략

- Redis TTL 1시간으로 캐싱 → 하루 실질 24회 API 호출로 순위 유지
- 기존 계획된 RealTrendingVideoAnalyzer + Redis 작업에 통합

### 6.3 UI 배치

```
롱폼 제작 메인 화면
├── 상단: 키워드 마인드맵 (접었다 펼치기)
└── 우측 패널: 📈 지금 뜨는 주식 영상 TOP 10
    - 제목 / 채널명 / 조회수 / 게시일
    - 클릭 시 → 해당 영상 제목/키워드가 제작 폼에 자동 채움
```

---

## 7. 쇼츠 기능 (반자동화)

### 7.1 스크립트 사이드패널

- 쇼츠 편집 화면 레이아웃: **좌측 40% 원본 스크립트(타임스탬프 포함) / 우측 60% 쇼츠 타임라인**
- 문장 단위 드래그 선택 → "쇼츠에 추가" 버튼으로 타임라인 삽입
- 이미 쇼츠에 쓴 구간은 색상 하이라이트 표시

### 7.2 기승전결 자동 추출 (반자동 모드)

- "삼성전자 쇼츠 만들어줘" 입력 → Claude API(`claude-sonnet-4-6`)에 원본 스크립트 + 타임스탬프 전달
- LLM은 타임스탬프를 직접 생성하지 않고 **발췌 힌트(텍스트)만 반환** → Whisper 퍼지매칭으로 실제 컷포인트 역산
- 후보 3안 동시 생성 (실적 중심 / 리스크 중심 / 투자자 반응 중심)
- **"결" 단계는 반드시 롱폼 유입 유도 문구로 마무리** (롱폼 → 쇼츠 → 롱폼 유입 구조)

### 7.3 쇼츠 메타데이터 자동 생성

스토리라인 확정 시 함께 생성:
- 썸네일 문구 (8자 내외 임팩트 카피) → Nano Banana 2로 실제 썸네일 이미지까지 생성
- 제목 후보 3안
- 더보기(설명)글
- 해시태그 / 태그 세트

---

## 8. 롱폼 제작 프로세스 개선

### 8.1 메인 화면 카테고리

| 카테고리 | 예시 |
|---|---|
| 개별 종목 | 삼성전자, SK하이닉스, 엔비디아, TSMC |
| 시장 이슈 | 금리, 환율, 반도체 업황, 실적 시즌 |
| 연관 종목군 | "삼성전자가 흔들리면 영향받는 종목들" |

연관 종목군은 EODHD/DART/KRX 데이터 기반으로 산출. **AI는 수치를 만들지 않고 데이터를 설명만 함.**

### 8.2 씬 단위 독립 재조립

| 버튼 | 동작 |
|---|---|
| [텍스트만 수정] | 스크립트 텍스트만 변경, 이미지/오디오 유지 |
| [이미지만 수정] | Nano Banana 재생성 (캐릭터 레퍼런스 유지), 텍스트/오디오 유지 |
| [전체 재조립] | 텍스트 → 오디오(ElevenLabs) + 이미지(Nano Banana) 재생성 → Whisper 재정렬 |

### 8.3 씬 분할

- 씬 우클릭 → "이 지점에서 분할"
- 스크립트 커서 위치 기준으로 두 씬으로 분리
- 분할된 두 씬 모두 동일 캐릭터 레퍼런스 유지

### 8.4 Kling 부분 영상화 (초반 구간 한정)

- 롱폼 씬 리스트에서 특정 씬에 "Kling으로 영상화" 토글 제공
- **기본값: 인트로(0:00~3:00) 구간까지만 노출, 이후 구간은 "고급 옵션"에 숨김**
- 예산 가드레일 통과 시에만 진행 (아래 9장 참고)
- Kling은 오디오 없이 영상만 생성 → ElevenLabs 오디오와 별도 합성 (비용 2배 방지)

### 8.5 메타데이터 자동 생성 + 업로드

완성 시 최소 제공:
- 썸네일 3안
- 제목 3안
- 더보기글
- 태그 / 해시태그

YouTube 자동 업로드 (`videos.insert`) — MANUAL/GUIDED/AUTO 다이얼과 연동:
- **MANUAL**: 업로드 버튼 수동 클릭
- **GUIDED**: 업로드 직전 미리보기 + 승인 팝업
- **AUTO**: 예산 가드레일 + 4단계 리뷰 게이트 전부 통과 시에만 자동 업로드

---

## 9. 예산 가드레일

### 9.1 단가표 (현행 기준)

| 항목 | 모델/경로 | 단가 |
|---|---|---|
| 이미지 (일반 씬) | gemini-2.5-flash-image (레거시) | $0.039/장 |
| 이미지 (캐릭터 씬, 권장) | gemini-3.1-flash-image (1K) | $0.067/장 |
| 이미지 (고화질) | gemini-3.1-flash-image (2K) | $0.101/장 |
| 음성 | ElevenLabs Multilingual/v3 | $0.05~$0.10/1,000자 |
| 영상 클립 | Fal.ai 경유 Kling | $0.03~$0.15/초 |
| 대본/스크립트 | claude-sonnet-4-6 | 모델별 토큰 단가 |

### 9.2 3단계 자동 폴백

```
영상 1편 시작 전 예상 비용 계산
    ↓
한도 초과 1차: Kling/신규 모션 생성 건너뜀 → 기존 루프 라이브러리로 대체
    ↓
한도 초과 2차: 이미지 해상도 다운그레이드 (2K → 1K → 0.5K)
    ↓
한도 초과 3차: 작업자 승인 없이 렌더링 단계 진입 불가 (하드 차단)
```

UI에 "예상 비용 게이지" 실시간 표시.  
**`MAX_BUDGET_PER_VIDEO` 금액은 대표님 확정 필요.**

### 9.3 모션 루프 라이브러리 전략

캐릭터 리액션(끄덕임, 강조, 미소, 놀람, 우려, 박수, 대기) 6~10종을 **딱 1회만** Kling으로 제작 → 이후 모든 영상에서 재사용.  
영상당 신규 모션 생성 비용 = 사실상 0.  
신규 루프 필요 시에만 예산 게이트 통과 후 추가 제작.

---

## 10. 단계별 로드맵

### Phase 0 — 즉시 처리 (이번 주)

- [ ] `image.py` 모델 문자열 교체: `gemini-2.5-flash-image` → `gemini-3.1-flash-image`
- [ ] `script_worker.py` Claude 모델 파라미터 `claude-sonnet-4-6` 확인
- [ ] Kling → Fal.ai 마이그레이션 (`video.py` 래퍼 교체)
- [ ] ElevenLabs API 키 `pronunciation_dictionaries_write` 권한 재발급
- [ ] Google AI Studio Billing 상태 확인 (4.2절 체크리스트)
- [ ] TTS 속도(1.5배) 청취 테스트 후 대표님 확정
- [ ] YouTube Data API v3 연동 진행 상황 확인

### Phase 1 — 캐릭터 IP 구축 (다음 주)

- [ ] 캐릭터 시트 생성: `gemini-3.1-flash-image`로 금색 코인 캐릭터 5종 표정 생성
- [ ] `image.py`에 캐릭터 레퍼런스 이미지 파라미터 추가 (2.4절 코드 적용)
- [ ] `channel_profiles` 테이블 신설 (2.5절)
- [ ] ElevenLabs 캐릭터 보이스 후보 3~5개 선정 → 대표님 확정
- [ ] 모션 루프 라이브러리 6~10종 Fal.ai/Kling으로 1회 제작
- [ ] 예산 가드레일 시스템 구현 (`BudgetEstimatorService` + UI 게이지)

### Phase 2 — 쇼츠 반자동화

- [ ] 스크립트 사이드패널 + 하이라이트 선택 UI
- [ ] 기승전결 추출 엔진 (다중 후보 3안 + Whisper 퍼지매칭)
- [ ] 쇼츠 메타데이터 자동 생성 (썸네일/제목/더보기/해시태그)
- [ ] 쇼츠 상태관리 React Query 전환 (모드 전환 시 상태 초기화 버그 동시 해결)

### Phase 3 — 롱폼 메인 화면

- [ ] 카테고리 자유 선택 리팩터링 (개별 종목 / 시장 이슈 / 연관 종목군)
- [ ] 연관 종목군 자동 생성 (데이터 기반, KRX/DART/EODHD 활용)
- [ ] 키워드 트렌드 마인드맵 대시보드 (상단 collapsible)
- [ ] 현재 뜨는 주식 영상 순위 우측 패널 (6장)
- [ ] RealTrendingVideoAnalyzer + Redis 캐싱 완성

### Phase 4 — 롱폼 제작 프로세스

- [ ] 씬 단위 독립 재조립 (텍스트만/이미지만/전체) (8.2절)
- [ ] 씬 분할 기능 (8.3절)
- [ ] ElevenLabs 다중 보이스 선택 UI + 미리듣기 (5.3절)
- [ ] 완료된 작업 상세 페이지 단계별 산출물 표시 (기존 버그 통합 해결)
- [ ] AUTO/GUIDED 쇼츠 다운로드 실패 수정

### Phase 5 — 배포 자동화

- [ ] Kling 부분 영상화 (예산 게이트 포함, 인트로 3분 한정) (8.4절)
- [ ] 업로드 메타데이터 자동 패키지 (썸네일/제목/설명/태그)
- [ ] YouTube 채널 자동 업로드 MANUAL/GUIDED/AUTO 다이얼 연동 (8.5절)

---

## 11. 개발팀 전달용 작업 지시 (Phase 0)

```
[작업 지시 — Phase 0: 즉시 처리]

전제 조건:
- Claude API 모델명은 반드시 claude-sonnet-4-6. 임의 변경 절대 금지.
- Java↔Python 필드 매핑: @JsonProperty로 camelCase↔snake_case 유지.
- 다운로드: JWT 인증 fetch + Blob URL 방식만 사용. <a href> 직접 다운로드 금지.

작업 항목:
1. [ ] image.py에서 모델 URL의 gemini-2.5-flash-image를 gemini-3.1-flash-image로 교체
       → 교체 전후 실제 API 응답 (HTTP 200) 로그 첨부
2. [ ] script_worker.py에서 Claude 모델 파라미터 값 그대로 캡처해서 보고
       (claude-sonnet-4-6 여부, 다르면 교체하고 교체 전/후 명시)
3. [ ] video.py Kling 호출부를 Fal.ai 엔드포인트로 교체
       → 기존 401 에러 해소 확인 (200 OK 응답 로그 첨부)
4. [ ] ElevenLabs 발음 사전 권한 갱신 후 발음 사전 생성 API 성공 응답 첨부
5. [ ] Google AI Studio Billing 상태 스크린샷 (Paid Tier 여부, 잔액, RPM 한도)

완료 보고 규칙:
- "완료했다"는 서술 보고 불인정. 실제 로그/스크린샷/API 응답 원문 첨부 필수.
- 확인 불가 항목은 "확인 불가 — 사유: ___"로 명시. 추측으로 채우지 말 것.

완료 체크리스트:
- [ ] image.py 교체 전후 로그
- [ ] script_worker.py 모델 파라미터 캡처
- [ ] video.py Fal.ai 200 OK 로그
- [ ] ElevenLabs 발음 사전 성공 응답
- [ ] Google AI Studio Billing 스크린샷
```

---

## 12. 확인 필요 사항 (대표님/팀 확인 대기)

| 번호 | 항목 | 중요도 |
|---|---|---|
| 1 | TTS 속도 1.5배 — 청취 테스트 후 최종 확정 | 🔴 높음 |
| 2 | `MAX_BUDGET_PER_VIDEO` 구체적 원화 금액 | 🔴 높음 |
| 3 | Fal.ai 결제 수단 등록 승인 | 🔴 높음 |
| 4 | ElevenLabs 플랜 (Starter $5/월 이상) 결제 여부 | 🔴 높음 |
| 5 | 캐릭터 시트 생성 결과물 최종 승인 (Phase 1 착수 후) | 🟡 중간 |
| 6 | 캐릭터 보이스 최종 선정 (후보 3~5개 미리듣기 후) | 🟡 중간 |
| 7 | YouTube 키워드 보조 툴 구독 여부 (vidIQ 등) | 🟡 중간 |
| 8 | 경제사냥꾼 실채널 영상 직접 시청 재검증 완료 여부 | 🟡 중간 |

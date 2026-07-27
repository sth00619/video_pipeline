# Codex 작업지침서 — 음성 자연스러움 & 자막 싱크 통합 v2 (최종)

- 대상 저장소: `sth00619/video_pipeline`
- 문서 상태: **구현 지시**
- 이전에 나눠 전달된 `CODEX_WORK_ORDER_TTS_SYNC.md`와 `CODEX_WORK_ORDER_VOICE_BATCH.md`를
  **이 문서 하나로 통합.** 혼선 방지를 위해 이전 두 문서는 참고하지 말고 이것만 따를 것.

---

## 지금 상황 요약 (Codex가 알아야 할 배경)

1. 테스트 영상(`KakaoTalk_20260724_154659505.mp4`, 60초)에서 담당자 피드백으로
   **① 음성이 AI처럼 들림 ② 자막-음성 싱크가 부분적으로 어긋남**이 확인됨.
2. 실측 결과: 영상은 24fps CFR, A/V 길이 일치 → **프레임레이트 문제 아님.**
   진짜 원인은 **자막 타임스탬프를 스크립트 글자수로 추정**하는 방식. 한국어 숫자
   확장("112만 5천"→"백십이만 오천 원")에서 문장 경계마다 누적 오차 발생.
3. 사용자가 이미 확보한 음성 2개(`original_anchor_audition.mp3`,
   `ivc_news_anchor_audition_with_pauses.mp3`)를 **먼저 활용하기로 결정.**
   이 음성들의 ElevenLabs `voice_id`를 이미 보유 중일 것 (직접 요청해 생성함).
4. 진행 방식: **영상 전체를 다시 만들지 않고 음성만 빠르게 뽑아** 담당자 피드백을
   받으며 설정을 조정한다. 승인되면 그 설정으로 실제 영상 파이프라인(자막 싱크 포함)에
   연결한다.

---

## 순서 (반드시 이 순서로) — 이전 문서들의 순서 혼선을 해소

```
P0: voice_id 확보 + 음성 배치 테스트 도구 구동
        ↓
P1: 담당자와 음성 피드백 루프 (설정 확정까지 반복)
        ↓
P2: 확정된 음성 설정으로 자막 싱크 근본 해결 (forced alignment)
        ↓
P3: 사람 녹음 경로 대비 (선택, 병행 가능)
```

**P0~P1이 먼저다.** 음성이 아직 안 정해졌는데 싱크 파이프라인부터 손대면
나중에 음성 바뀔 때 다시 손봐야 한다. 순서를 지킬 것.

---

## P0 — 음성 배치 테스트 도구 구동 (최우선)

### 완료 정의 (DoD)
```bash
python scripts/voice_sample_batch.py
```
가 에러 없이 완주하고 `out/voice_samples/index.html`이 생성되며,
브라우저로 열었을 때 두 보이스 × 대본 개수만큼 오디오 플레이어가 표로 뜬다.

### 작업
1. 첨부 킷의 다음 파일들을 저장소 FastAPI 워커 트리에 통합:
   - `backend_fastapi/tts/forced_alignment_srt.py` — TTS 호출 코어
   - `scripts/voice_sample_batch.py` — 배치 생성 + 비교 페이지 생성
   - `voices.json`, `sample_scripts/` — 설정 및 테스트 대본
2. `voices.json`의 `PUT_VOICE_ID_HERE_1`, `_2`를 **실제 voice_id로 교체.**
   ElevenLabs 대시보드 VoiceLab에서 확인 (이미 이 두 음성을 생성한 이력이 있으므로
   대시보드에 남아 있을 것).
3. `.env`에 `ELEVENLABS_API_KEY` 확인 (기존 값 재사용, 하드코딩 금지).
4. 이 단계는 **음성 생성만** 한다. 이미지·Kling 등 다른 API를 호출하지 않는다
   (비용 통제 — 담당자 피드백 전 불필요한 렌더링 방지).

### 증거
- `out/voice_samples/index.html` (또는 스크린샷)
- `_manifest.json`

---

## P1 — 담당자 피드백 루프

### 완료 정의
`voices.json`의 설정을 조정 → 재실행 → 몇 분 내 `index.html` 갱신, 이 사이클을
최소 2회 반복하여 담당자가 만족하는 설정 1세트가 확정된다.

### 작업
1. `out/voice_samples/` 폴더째 압축해서 담당자에게 전달 (mp3 상대경로 유지 필요).
2. 피드백 반영 규칙:
   - "기계적/AI 느낌" → `stability`를 0.05~0.1 단위로 낮춰본다 (권장 범위 0.35~0.45,
     0.30 미만은 불안정해지므로 하한선 유지)
   - "발음 부정확/불안정" → `stability`를 올리거나 `similarity_boost` 조정
   - `model_id`는 기본 `eleven_multilingual_v2` 유지 (한국어 발음 안정성 우위 검증됨).
     인트로처럼 감정이 필요한 구간만 실험적으로 v3 시도 가능.
3. **`latency_optimization` 파라미터는 어떤 경우에도 추가하지 않는다**
   (텍스트 정규화가 꺼져 한국어 숫자·문장이 깨짐).
4. 매 반복의 설정을 `_manifest.json`에 남겨 이력 추적 (이미 코드에 구현됨).
5. 확정 시점: 담당자가 특정 버전(파일 경로 + 그때의 `voices.json` 스냅샷)을
   최종 승인하면 P2로 진행.

### 증거
- 반복 최소 2회 이상의 `_manifest.json` (설정 변화 비교 가능해야 함)
- 최종 확정 설정의 `voices.json` 스냅샷

---

## P2 — 자막 싱크 근본 해결 (P1 확정 후 착수)

### 완료 정의
자막 타임스탬프가 스크립트 추정이 아니라 **실제 생성 오디오에서** 나오며,
`sync_verifier.py`로 검증했을 때 "OK: 문장 경계 싱크 양호" 판정이 나온다.

### 작업
1. 기존 코드에서 **자막을 스크립트 글자수로 추정하는 함수**를 찾아 교체 대상으로 지정.
   (userMemories 기준 후보: `_map_timestamps_by_preprocessed_length()` 유사 로직)
2. TTS 생성을 `forced_alignment_srt.tts_with_timestamps()`로 교체:
   - P1에서 확정된 `voice_id`, `stability` 등 설정을 그대로 사용.
   - `with-timestamps` 엔드포인트로 오디오+문자 타임스탬프를 1콜로 수신.
3. 문자 타임스탬프 → 자막 큐 변환은 `words_to_cues()` 사용.
   - `gap_split=0.5`: 문장 사이 무음 0.5초 이상이면 자막 분할 → 이게 "문장 경계
     싱크 어긋남"을 해결하는 핵심 지점.
   - `max_chars=20`: 한 줄 가독성 한계.
4. 숫자 이중 처리 유지: TTS 입력에만 한글 숫자 확장(`normalize_korean_for_tts()`),
   자막 텍스트는 원본 숫자 그대로.
5. 검증: `sync_verifier.analyze_boundary_drift()` + `classify_drift()`로
   교체 전/후 비교. "OK" 판정 나올 때까지 반복.

### 증거
- 교체 전/후 동일 스크립트로 만든 영상 2개
- `sync_verifier` 리포트 (전: 드리프트 검출 / 후: OK)

---

## P3 — 사람 녹음 경로 (선택, 병행 가능)

담당자 인맥으로 사람이 직접 녹음한 음성이 준비되면, AI 음성과 별개로 다음 스크립트로
바로 처리 가능. P0~P2와 무관하게 언제든 실행할 수 있다.

```bash
python scripts/align_human_recording.py \
    --audio 녹음.mp3 --script 대본.txt --out 자막.srt \
    --burn 영상.mp4 --burned 최종.mp4
```

`align_audio_to_text()`가 Forced Alignment로 실제 발화에 자막을 정렬하므로,
AI 음성보다 오히려 싱크가 더 안정적이다.

---

## 전역 금지사항 (모든 단계 공통)

1. `latency_optimization` 파라미터 사용 금지.
2. `voice_id`를 로그·문서·커밋에 평문 노출 금지.
3. 자막 타임스탬프를 글자수로 추정하는 로직 신규 작성 금지.
4. `%`를 `포인트`로 읽지 않기 (`퍼센트`만 — 1.2%는 1.2포인트와 다름).
5. 숫자→한글 확장은 TTS 입력에만, 자막은 원본 숫자 유지.
6. API 키 하드코딩 금지.
7. P0~P1 단계에서 이미지·Kling 등 다른 API 호출 금지 (음성 검증 전용, 비용 통제).
8. 기존 자막 생성 경로를 삭제하지 말고 새 경로를 분기로 추가 (롤백 가능하게).

---

## 보고 형식

각 단계 완료 시: DoD 충족 여부 / 증거 첨부 / 다음 단계 착수 가능 여부 / 이슈.
**P1에서 음성이 확정되지 않으면 P2로 넘어가지 않는다.**

# WO-PROVIDER-02 최종 모델 정책 결정 및 공통 운영 반영

작성일: 2026-08-30
범위: Job52 보존 장면 47개(scene42 동결 제외), Gemini 3 Pro Image Priority와 Gemini 3.1 Flash Image High의 동일 입력 비교

## 1. 결론

영상 생성 버튼이 타는 기본 이미지 생성 경로는 **`gemini-3-pro-image` + Priority**로 확정한다. 아래 `46/47`, `45/47`은 **HTTP 200과 raw 이미지 저장 여부만 센 가용성 수치**이며 육안 품질 합격률이 아니다. 이 혼동을 바로잡은 뒤 91개 raw 전수 육안 원장을 별도로 완성했고, 동일 장면 직접 비교 Pro 24 대 Flash 10과 가용성·지연·OCR 결과를 함께 적용해 최종 결정했다. 상세 근거는 `WO_PROVIDER_02_MANUAL_91_RAW_FINAL_DECISION_2026-08-30.md`와 `MANUAL_VISUAL_QUALITY_LEDGER_2026-08-30.csv`에 있다.

- Flash High는 자동 폴백, 장면별 혼합, 비용 절감 경로로 사용하지 않는다.
- Flash High는 비교 실험과 수동 연구용 프로필로만 남긴다.
- 이 결정은 Flash가 모든 장면에서 나쁘다는 뜻이 아니다. 일부 장면에서는 Flash의 얼굴 구조·정보 밀도·불필요한 영문 억제가 더 좋았다.
- 그러나 생성 전에 그 장면을 안전하게 선별하는 재현 가능한 규칙을 발견하지 못했다. 결과를 본 뒤 좋은 쪽을 고르는 방식은 운영 라우팅 규칙이 아니며, 다음 주제의 영상에 일반화할 수 없다.
- 모델 선택으로 텍스트·수치·얼굴·표면 문제가 해결된 것은 아니다. 공급자 변수를 Pro Priority로 고정하고 공통 이미지 계약 개선에 다시 집중한다.

## 2. 외부 근거 재검증

1. Google 공식 가격표는 `gemini-3-pro-image`에 Standard, Batch, Flex, Priority를 별도로 제시한다. Priority 이미지 출력은 $216/백만 토큰이며 Pro 1K·2K의 1,120토큰을 적용한 정확한 출력값은 장당 $0.24192다. Flash Image 가격표에는 Standard와 Batch만 있다.
   출처: <https://ai.google.dev/gemini-api/docs/pricing>
2. 공식 Flash Image 모델 페이지도 Priority inference를 지원하지 않는다고 명시한다.
   출처: <https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image>
3. Google은 Pro Image를 전문 자산 제작용, Flash Image를 속도·대량 처리용으로 설명한다.
   출처: <https://ai.google.dev/gemini-api/docs/image-generation>
4. Priority 사용 시 실제 처리 tier를 `x-gemini-service-tier` 응답 헤더로 감시해야 한다.
   출처: <https://ai.google.dev/gemini-api/docs/priority-inference>
5. 2026-05-28 두 모델은 GA가 되었고 preview 모델은 2026-06-25 종료됐다. 이번 503을 preview 우선순위 문제로 설명하지 않는다.
   출처: <https://ai.google.dev/gemini-api/docs/changelog>
6. 개발자 포럼의 반복 503 사례는 문제의 존재 가능성을 보조하지만 모델 우열의 정량 근거로 사용하지 않았다.
   참고: <https://discuss.ai.google.dev/t/urgent-frequent-503-errors-with-gemini-3-pro-image-preview-in-production-environment/126393>

## 3. 실험 계약

- 장면: Job52 00~47 중 동결된 scene42를 제외한 47개
- 요청: 47장 × 2모델 = 94건
- 재시도: 0회
- 입력 통제: 장면별 최종 프롬프트와 참조 이미지 SHA-256 동일
- Pro: `gemini-3-pro-image`, `serviceTier=priority`
- Flash: `gemini-3.1-flash-image`, `thinkingLevel=High`, Standard
- 수치 계약: 결정론 렌더 대상 금융 수치는 모델 프롬프트에서 제거
- 실물 검토: 12개 콘택트시트와 91개 생성 원본을 확인
- 원장: `run/manifest.json`, `run/request_ledger.json`
- scene42: 과거 요청 상한 상태를 보존하며 호출하지 않음

## 4. 정량 결과

| 지표 | Pro Priority | Flash High |
|---|---:|---:|
| HTTP 200 | 46/47 (97.9%) | 45/47 (95.7%) |
| 실패 | scene15 연결 오류 1건 | scene14 연결 오류, scene37 HTTP 504 |
| 실제 응답 tier | priority 46/46 | standard 45/45 |
| HTTP 200 응답 평균 시간 | 38.42초 | 48.60초 |
| HTTP 200 응답 중앙값 | 36.41초 | 46.77초 |
| HTTP 200 응답 p95 | 54.05초 | 68.60초 |
| OCR이 기대 생성 문구를 모두 확인 | 8장 | 4장 |
| 평균 thoughtsTokenCount | 215.0 | 1,675.6 |
| 평균 totalTokenCount | 4,077.3 | 6,455.5 |
| 성공 응답 비용 추정 | 약 ₩15,548 | 약 ₩6,345 |
| 예약 노출 | 약 ₩15,886 | 약 ₩6,627 |

전체 성공 응답 비용 추정은 약 ₩21,893, 예약 노출은 약 ₩22,513이다. 이 비교 원장은 당시 반올림 단가 $0.2412를 사용했다. 공식 토큰 단가로 다시 계산하면 Pro 성공 응답 46건은 약 ₩46, Pro 예약 47건은 약 ₩47 증가한다. 모델 비교 결론에는 영향이 없으며 운영 기본 단가는 $0.24192로 정정했다. 비용은 콘솔 청구 확정값이 아니라 원장 기반 추정값이다.

### 4.1 콘택트시트 네 장면 재감사

사용자 육안 검토에서 Flash의 scene14·15·25·38이 붉은 실패 표시처럼 보인다는 이의가 제기되어 `manifest.json`, 실제 raw 파일, 저장 SHA-256, 콘택트시트 생성 코드를 다시 대조했다.

| 장면 | Flash 요청 상태 | raw | 판정 |
|---|---|---|---|
| scene14 | `network_error`, `ConnectionError` | 없음 | 실제 생성 누락이며 콘택트시트 자리 표시자 |
| scene15 | HTTP 200 | 존재, SHA-256 `693856bc...729` 일치 | 붉은 하락 화살표·그래프는 생성 이미지 내부 내용이며 자리 표시자가 아님 |
| scene25 | HTTP 200 | 존재, SHA-256 `8ad29532...3ce` 일치 | 정상 raw가 붙은 칸이며 자리 표시자가 아님 |
| scene38 | HTTP 200 | 존재, SHA-256 `89211c0c...991` 일치 | 계산기 표시의 의사수치는 생성 이미지 내부 품질 결함이며 자리 표시자가 아님 |

콘택트시트 스크립트는 `raw_path`가 없을 때만 짙은 남색 바탕에 연분홍색 한국어 `생성 실패/보류`를 그린다. 성공 raw 안에 포함된 붉은 그래프, 하락 화살표, 깨진 숫자나 의사문자는 실패 표식이 아니라 모델 출력이다. 따라서 Flash의 가용성 수치는 여전히 45/47이 맞지만, 이를 “품질 성공 45장”으로 해석해서는 안 된다.

## 5. 실물 검토에서 확인한 유형별 결과

### Pro가 운영 기본값에 더 적합한 근거

- scene00: `삼성전자`, `SK하이닉스`와 저울 비유를 안정적으로 표현하고 결정론 대상 `4배`는 base raster에서 제외했다.
- scene07: 세 승인 엔티티를 한 화면에 정돈하고 두 기업 용기를 유지했다. Flash는 동일 문구를 여러 화면에 중복했다.
- scene11: Flash보다 공식·의사문자 밀도가 낮았다.
- scene30: `대형주`를 정확히 표시했지만 Flash는 승인 문구를 누락했다.
- 47장 묶음의 가용성·중앙값·p95·OCR 기대문구 충족이 모두 Flash보다 나았다.

### Flash가 더 좋았으나 자동 라우팅 근거가 되지 못한 장면

- scene18, 38, 46: 흰자·홍채·동공이 분리된 눈 구조가 Pro보다 나았다.
- scene29: Flash는 `삼성전자`, `SK하이닉스`를 정확히 썼고 Pro는 `SK HYNYX` 오탈자를 만들었다.
- scene31: Flash는 승인 엔티티만 남겼고 Pro는 비승인 한국어 배너를 추가했다.
- scene45: Flash는 Pro의 비승인 `DATA`보다 안전했다.

같은 데이터랩·관제실·교실 유형 안에서도 Flash의 중복문자, 누락, 숫자 발명, 과도한 빈 표면이 함께 발생했다. 따라서 `scene_type`이나 archetype만으로 Flash 승리 장면을 사전에 고르는 규칙은 만들 수 없었다.

### 두 모델에 공통으로 남은 결함

- scene02: 의사 한글과 `경고` 중복
- scene09: 비승인 `METEOROLOGIST`/`FORECAST`
- scene12: 비승인 영문·수치 기호
- scene21, 23, 26, 39, 40: 모델이 직접 만든 숫자·계산기·전광판
- scene34, 44: 뉴스·티커용 비승인 영문
- scene43: 같은 승인 엔티티가 여러 표면에 반복
- scene47: 승인되지 않은 말풍선/질문 표현

자동 strict gate가 성공 이미지 전부를 통과시킨 것은 품질 성공을 뜻하지 않는다. OCR이 읽지 못한 의사문자·작은 수치·비승인 영문이 실물에서 확인됐으므로, 현재 게이트의 재현율은 다음 개선 대상이다.

## 6. 공통 운영 경로 반영

다음 변경은 비교 harness나 Job52 전용 코드가 아니라 영상 생성 버튼의 공통 경로에 적용했다.

1. V5 최종 lane의 공급자를 `gemini-3-pro-image + priority + 2K`로 고정했다.
2. 전역 Gemini 기본 tier를 Priority로 변경하고 Standard/Priority 외 값은 시작 단계에서 거절한다.
   Docker Compose의 운영 환경 기본값도 Priority로 맞춰, 빌드된 서비스와 테스트 경로의 설정 차이를 제거했다.
3. 공급자 응답의 `x-gemini-service-tier`를 원장에 보존한다.
4. Pro Priority 공식 단가를 FastAPI runtime config와 Spring `PricingConfig.java`에 추가했다.
5. `ProviderRequestAudit`가 요청 tier에 맞는 단가를 예약하고 `service_tier_requested`를 기록한다.
6. 48장 Priority 생성이 가능한 이미지 전용 기본 상한을 ₩15,000에서 ₩20,000으로 조정했다. 전체 영상 상한 ₩40,000/₩70,000을 넘을 수는 없다.
7. 승인 대본은 TTS·자막의 단일 원문으로 보존하면서, Gemini/Claude 시각 방향 프롬프트에서는 결정론 대상 금융 수치와 승인되지 않은 엔티티 리터럴을 제거한다.
8. Flash High 구현은 실험 도구에 보존하지만 운영 버튼·자동 fallback·비용 절감 혼합 경로에는 연결하지 않는다.

## 7. 세 가지 큰 목표와의 관계

### 목표 1 — 시간 보정과 TTS/자막/이미지 청크 동기화

이번 모델 비교는 이 목표의 문장 분할·TTS 음색을 변경하지 않았다. 승인 내레이션 해시를 보존하고 이미지 프롬프트만 정화해, 장면 재생성이 TTS/자막 원문을 바꾸지 않도록 계보를 유지했다. 이 목표는 기존 구현을 보존한 상태이며, 다음 E2E에서 실제 장면 길이와 이미지 전환 시점을 다시 검증한다.

### 목표 2 — 대본 의미를 충실히 설명하는 고품질 이미지와 Fal 안전성

Pro Priority로 공급자 변수를 고정해 캐릭터·구도·정보 밀도·사물 의미 계약 개선에 집중할 수 있게 됐다. Fal은 텍스트·수치 표면을 움직이지 않고 캐릭터 팔, 컨베이어, 조명처럼 국소 사물만 움직이는 기존 fail-closed 정책을 유지한다. 이번 비교 이미지는 Fal 입력으로 보내지 않았다.

### 목표 3 — 오탈자·이탈자 없이 필요한 텍스트와 수치를 정확히 표시

대괄호 유도 배열 표기는 공통 프롬프트 빌더에서 제거했고, 금융 수치는 Gemini가 아니라 Pillow/FFmpeg가 렌더한다. 다만 생성 모델의 비승인 영문·의사문자·숫자를 OCR이 놓치는 문제가 남아 있어 완료 상태가 아니다. 모델 정책 확정 후 가장 먼저 이 공통 게이트를 개선한다.

## 8. 다음 이미지 개선 순서

1. **OCR 재현율**: 원본 해상도 표면 타일을 모든 검출 표면에 적용하고, `기대 문구 0건 검출`을 성공으로 해석하지 않도록 근거를 분리한다.
2. **숫자 base-raster 차단**: 생성 이미지에 숫자형 픽셀 군집이 있으면 OCR 문자열 여부와 무관하게 재검토한다. 승인 수치는 결정론 레이어에서만 허용한다.
3. **표면별 의미 바인딩**: 승인 문구마다 `semantic_object_id`와 `surface_id`를 연결해 한 모니터 몰아넣기와 다중 모니터 중복을 막는다.
4. **얼굴·해부학 하한선**: sclera/홍채/동공/catchlight, 팔다리 수, 동전 몸통 실루엣을 자동 보조 검사하고 최종 canary는 사용자 육안 승인 전 통과로 표시하지 않는다.
5. **참조 정화**: 화풍 참조에 섞인 텍스트·수치·상충 신체 비례를 제거한 순수 스타일 참조를 별도로 만든다.
6. **Fal 후보 판정**: 위 정지 이미지 게이트를 통과한 텍스트 없는 장면만 국소 모션 후보로 승격한다.

## 9. 검증 결과와 제한

- Docker 집중 회귀: 87 passed
- Priority 비용·runtime 계약 추가 집중 회귀: 33 passed
- Python 변경 파일 `py_compile`: 통과
- 전체 Docker pytest는 컨테이너에 여러 역사적 스크립트의 `Path.parents[n]` 가정이 맞지 않아 수집 단계에서 14건 오류가 났다. 이번 변경으로 발생한 테스트 실패로 분류하지 않으며 숨기지 않는다.
- 호스트 전체 pytest는 `faster_whisper`, `cv2` 미설치로 수집 단계에서 6건 오류가 났다.
- Spring `PricingConfigTest`는 호스트에 Java 17 toolchain이 없어 실행하지 못했다. 테스트 기대값은 ₩70,000으로 갱신했다.

## 10. 최종 상태

- 모델 정책: **확정 — Pro Priority 단일 운영**
- Flash High: **자동 운영 미채택, 연구용 유지**
- Job52: **품질 fixture로 유지, Job52 전용 패치 없음**
- scene42: **동결 유지**
- 다음 작업: **공통 OCR/숫자/표면/얼굴 품질 게이트 개선**

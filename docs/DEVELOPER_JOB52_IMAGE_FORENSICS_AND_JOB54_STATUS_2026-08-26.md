# Job 52 이미지 생성 포렌식 및 Job 54 중단 상태

- 작성일: 2026-08-26 KST
- 기준 저장소: `video_pipeline`
- Job 52 생성 당시 코드 기준점: Git commit `1bbb4e9`
- 분석 대상: 사용자가 지정한 Job 52 `scene 00~47` 48장과 별도 보관된 `scene 048`
- 비교 대상: Job 54의 현재 정지 이미지 및 비용 원장
- 목적: Job 52의 장점을 보존하면서 텍스트·수치·캐릭터·해부학·의미 오류의 원인을 전역 생성 과정에서 제거한다.

## 1. 결론

Job 52의 이미지는 저장된 거대한 V5 프롬프트를 그대로 Gemini에 보낸 결과가 아니다. 승인 대본의 각 장면에 `prompt_en`이 비어 있고 `prompt_needs_rebuild=true`였기 때문에, 이미지 워커가 장면마다 Claude `claude-sonnet-4-6`을 호출해 영문 장면 프롬프트를 새로 만든 뒤 Gemini 3 Pro Image에 전달했다.

당시 Claude 프롬프트 생성 규칙은 다음 두 요구를 동시에 강제했다.

1. 장면마다 다른 공간·소품·의상·행동을 사용해 대본의 경제 의미를 물리적 은유로 바꾼다.
2. 바인딩된 엔티티와 검증 수치를 Gemini가 모니터·표지판·배럴 등에 직접 읽을 수 있게 쓰게 한다.

첫 번째 규칙이 Job 52의 장점인 다양한 화풍 범위, 정보 밀도, 구도, 장면별 의상, 대본과 연결된 소품을 만들었다. 두 번째 규칙은 한국어 오탈자·이탈자, 임의 영문, 숫자 변형, 텍스트 과밀, 말풍선과 표지판 남발의 직접 원인이 됐다. 따라서 해결책은 전역 무문자화가 아니다. **승인된 비수치 한국어·영어는 생성 모델이 장면 안의 자연스러운 표면에 쓸 수 있게 하고, 검증 금융 수치만 결정론적으로 렌더링하며, 생성 결과의 모든 문자를 장면 로컬 허용 목록과 대조하는 것**이 목표다.

Job 54는 현재 이미지 생성이 실행 중이지 않다. 데이터베이스 상태가 `IMAGES_PENDING`에 남아 있어 UI가 생성 단계처럼 보일 뿐이다. 실제 Gemini 호출은 이미 발생했고 일부는 성공해 비용이 기록됐지만, 반복된 503/504와 미정산 예약 항목, 불완전한 manifest 때문에 이미지 단계가 완료 자산으로 등록되지 않았다.

## 2. Job 52 기준 이미지의 보존

사용자가 제공한 3개 접촉시트는 수정하지 않고 아래 경로에 보존한다.

| 범위 | 파일 | SHA-256 |
|---|---|---|
| scene 00~15 | `artifacts/job52_image_audit/job52_contact_1.jpg` | `0e9d28177b9c9bc9719f938b566ac94769995989ed16cf68405d3f83d2f6960e` |
| scene 16~31 | `artifacts/job52_image_audit/job52_contact_2.jpg` | `dc2d470d013102feaecf30a397dbc93966492b894ef7adb6cf7564632d7aa575` |
| scene 32~47 | `artifacts/job52_image_audit/job52_contact_3.jpg` | `8b92b894545ef69cea80fe22e8a947689d22da6255fa458a95265250ce9770d7` |

이 세 접촉시트는 품질 비교 증거이며 Gemini 입력 참조 이미지로 직접 사용하지 않는다. 접촉시트 자체를 입력하면 검은 격자, `scene NN` 제목, 16개 구도를 하나의 장면 문법으로 오인해 새 이미지에 복제할 위험이 크다. 현재 구현은 접촉시트에서 생성적 변경 없이 잘라낸 얼굴 범위와, 장점이 명확한 개별 Job 52 장면을 문맥별 참조로 최대 3장만 선택한다.

## 3. Job 52 실제 생성 계보

### 3.1 입력과 프롬프트 선택

실제 경로는 `backend/fastapi-workers/app/workers/images_worker.py`의 다음 함수와 분기다.

1. 승인 SCRIPT 장면에서 내레이션을 읽는다.
2. `binding_map`에서 `core_entities`, `core_figures`, `fictionalized_labels`, `suggested_visual_type`을 장면에 연결한다.
3. 다음 조건 중 하나면 기존 V5 프롬프트 대신 `_build_prompt_from_narration()`을 실행한다.
   - `prompt_needs_rebuild=true`
   - `prompt_en` 또는 `prompt`가 비어 있음
   - 과거 폴백 문구가 포함됨
   - 장면 아키타입과 대본 내용의 불일치가 감지됨
4. Job 52에서는 승인 SCRIPT 장면의 `prompt_en`이 비어 있고 재생성 플래그가 있어 scene 00~48 전체가 이 경로에 들어갔다.
5. `_build_prompt_from_narration()`은 Anthropic SDK를 통해 모델 `claude-sonnet-4-6`을 호출했다.
6. Claude 결과에 공통 화풍 접미사를 붙인 문자열이 실제 `prompt_en`과 Gemini 요청 텍스트가 됐다.

생성 당시 코드를 재현하려면 다음 명령으로 확인할 수 있다.

```bash
git show 1bbb4e9:backend/fastapi-workers/app/workers/images_worker.py
git show 1bbb4e9:backend/fastapi-workers/app/providers/real/image.py
```

### 3.2 Claude에 당시 전달된 핵심 규칙

당시 `_build_prompt_from_narration()`은 다음 의미의 지시를 포함했다.

- Goldie를 전경 높이 50~65%로 크게 배치한다.
- 장면에 맞는 옷과 모자를 항상 입힌다.
- 하나의 금화 마스코트만 사용한다.
- 추상 경제 개념을 물리적 공간과 소품으로 바꾼다.
- 장면마다 다른 배경을 사용한다.
- 검증 엔티티를 표지판·모니터·배럴에 읽을 수 있는 블록 텍스트로 쓴다.
- `core_figures`의 검증 수치를 메인 모니터에 정확히 렌더링한다.
- 임의의 보조 숫자·날짜·틱은 만들지 않는다.
- 최종 프롬프트는 75단어 이내로 제한한다.
- 공통 접미사: `original 2D Korean finance comic, bold ink outlines, cel shading, single round gold coin mascot character only, no secondary mascot, no teal mint card mascot, no secondary people`

여기서 “검증 수치를 Gemini가 정확히 렌더링하라”는 요구는 사실 검증 계보에는 맞지만, 래스터 생성 모델의 글자 정확도와는 별개의 문제다. 검증된 숫자를 입력으로 줬다는 사실만으로 출력 픽셀의 한글·숫자 정확성이 보장되지는 않는다.

### 3.3 Gemini 실제 요청

실제 공급자 경로는 `NanaBananaProvider.generate()`에서 Gemini Interactions/Generate Content 요청으로 연결됐다.

- 모델: `gemini-3-pro-image`
- 이미지 크기: `2K`
- 종횡비: `16:9`
- 서비스 티어: `standard`
- 엔드포인트 형태: `v1beta/models/gemini-3-pro-image:generateContent`
- 요청 `parts` 순서:
  1. 참조 이미지 1 `inlineData`
  2. 참조 이미지 2 `inlineData`
  3. 참조 이미지 3 `inlineData`
  4. Claude가 만든 실제 영문 프롬프트 `text`
- 응답 모달리티: `IMAGE`
- 원본 파일: 대체로 2752×1536 PNG
- 최종 파일: 1920×1080 PNG로 정규화

Job 52에 실제 전달된 참조 3장은 다음과 같다.

| 순서 | 파일 | SHA-256 | 역할 |
|---|---|---|---|
| 1 | `character_reference_v4_identity_clean.png` | `709537f537503ff2b8e92b9398c3096bbb7a00a4c24366306d56d2e1c4b33136` | 캐릭터 정체성 |
| 2 | `style_reference_v4_medium_clean.png` | `8f9091506f278ef5c9e6c1cbe315775d38825749099da7901e7d68743f4b1a94` | 선화·셀 셰이딩·색감 |
| 3 | `style_scene_ref_01_port.png` | `a0cba032a496dd1c5fe8c30580902c442c814df7614fa87488be9c024ce728cb` | 장면 구성·정보 밀도 |

호출자는 `gemini_reference_contract_declared=true`를 전달했으므로 공급자 계층의 “첫 번째 참조 얼굴을 고정하라”는 추가 문구는 붙지 않았다. Job 52의 캐릭터·의상·표정 변화는 Claude 장면 프롬프트와 세 참조의 결합 결과다.

### 3.4 요청 수, 비용, 시간, 후처리

- 이미지 비용 원장: 49개 Gemini Pro 요청, 모두 첫 요청 HTTP 200
- 이미지 비용 원장 합계: 약 ₩9,212
- 최대 관찰 동시성: 6
- 이미지 49장 생성 소요: 약 5분 57초
- Job 52의 Spring 누적 비용: ₩17,080
- 최종 Job 상태는 이후 다른 단계 실패가 반영된 `FAILED`이며, 이미지 49장 생성 성공 여부와는 구분해야 한다.
- raw와 최종 이미지를 동일 크기로 정규화한 비교에서 49장 모두 생성 픽셀 내용이 동일했다. 즉 Job 52의 화면 글자, 숫자, 말풍선은 Pillow가 새로 쓴 것이 아니라 Gemini 원본에 포함됐다.

전체 00~47 실제 프롬프트와 메타데이터는 다음 감사 파일에 보존한다.

- `artifacts/job52_full_audit_20260824/metadata/scene_generation_contracts.txt`
- `artifacts/job52_full_audit_20260824/metadata/scene_generation_contracts.json`

`scene 048` 이미지는 `artifacts/job52_image_audit/scene_048.png`에 별도로 보존돼 있다. 현재 프롬프트 감사 묶음은 사용자가 평가한 00~47을 기준으로 48개 항목을 담는다.

## 4. 실제 프롬프트가 결함을 만든 사례

### scene 00 — 숫자와 회사명을 장면 자체보다 앞세움

```text
Flat 2D classroom scene. Goldie ... pointing excitedly at a large wooden balance scale.
Left pan holds a sign reading "Samsung Electronics PER 4x," right pan holds
"SK Hynix PER 4x," ... A chalkboard behind displays "PER" ...
```

저울이라는 의미 은유는 좋지만, 회사명과 PER 수치를 표지판으로 직접 쓰도록 프롬프트가 설계돼 “숫자를 얻은 그림”처럼 보이게 됐다.

### scene 02 — 대본에 없는 Silver와 캐릭터 인상 변화

```text
Multiple monitors display "Silver" price charts ... Goldie, wearing a dark inspector's
coat and peaked cap ... giant cracked bargain tag ... unstable silver barrel labeled "Silver."
```

대본은 “싸 보인다고 샀다가 위험”이라는 일반 경고인데, 프롬프트 생성 단계가 Silver를 추가했다. `Silver`는 이미지 모델의 우발적 환각만이 아니라 **Claude 프롬프트 단계에서 이미 들어간 의미 오염**이다. inspector coat와 peaked cap도 다른 장면의 금융 캐릭터 범위에서 벗어난 경찰형 인상으로 수렴시켰다.

### scene 07 — 승인 숫자와 회사명 직접 쓰기

```text
monitor displays "KOSPI Operating Profit: 143조" ... containers marked
"Samsung Electronics" and "SK Hynix" ...
```

정보 선택은 대본과 맞지만 Gemini가 한글을 직접 그려 오탈자·이탈자가 발생했다. 현재 목표는 `KOSPI`, `삼성전자`, `SK하이닉스` 같은 승인 비수치 문자열은 장면 로컬 계약으로 허용하되 결과를 검수하고, `143조 원` 같은 금융 수치는 결정론 표면 렌더러가 정확히 합성하는 것이다.

### scene 11 — 세 번째 손을 유도한 모순 행동

```text
stands foreground pointing skeptically at the PER board, eyebrow raised,
arms crossed in doubt.
```

한 캐릭터에게 동시에 “가리키기”와 “팔짱 끼기”를 요구했다. 두 팔로 팔짱을 끼면서 추가로 가리키는 손을 만들 가능성이 커지는 구조적 프롬프트 오류다. 단순한 생성 모델 랜덤 실패로만 분류하면 재발한다.

### scene 14 — 같은 주가가 GOLD와 SILVER로 변질

```text
Two giant ticker screens ... one labeled "GOLD" ... the other labeled "SILVER" ...
```

대본의 “같은 주가를 보고 반대로 움직인 개인과 외국인”을 귀금속 비교로 바꿨다. 이 결함은 이미지 OCR 이전의 프롬프트 의미 검수에서 막아야 한다.

### scene 20 — 코스피가 코스닥으로 변경

```text
monitor displays "KOSDAQ" ... peak labeled "7475" ...
```

승인 대본과 시장 데이터는 코스피인데 prompt-stage에서 KOSDAQ으로 바뀌었다. 장면 로컬 엔티티 대조가 없었던 것이 원인이다.

### scene 26 — 순위표의 나머지 항목 발명

```text
leaderboard ... "JUSUNG ENGINEERING" ... highlighted at the top ...
```

프롬프트는 주성엔지니어링만 승인했지만 “leaderboard” 구도는 생성 모델이 빈 순위 항목을 채우게 압박한다. 결과에서 Naver, Kakao 등 대본에 없는 항목이 생겼다. 화면 형식 자체가 허용 목록 밖 정보를 요구하는지 검사해야 한다.

### scene 36·47 — Silver 전이와 말풍선

scene 36 프롬프트가 `silver mirror wall`, `Silver` 표기를 만들고, scene 47 프롬프트도 `silver barrel stamped "SILVER"`를 다시 요구했다. 이 반복은 동일 영상 내부 프롬프트 문맥 또는 장면 생성기의 잘못된 연상 패턴이 대본과 무관하게 전이된 사례다. scene 47 프롬프트에는 말풍선 지시가 없지만 결과에 말풍선이 생겼으므로, 이 부분은 Gemini의 만화 관습 보완이다. 말풍선은 “모든 장면 금지”가 아니라 장면별 `bubble_policy`가 `allowed` 또는 `required`이고 정확한 `bubble_text`가 있을 때만 허용해야 한다.

## 5. scene 00~47 문제 지도

아래 평가는 접촉시트, 승인 내레이션, 실제 프롬프트를 함께 본 결과다. “양호”는 완성 승인이라는 뜻이 아니라 Job 52에서 보존할 생성 문법이 분명하다는 뜻이다.

| 분류 | scene | 관찰 | 추정 원인 | 처리 위치 |
|---|---|---|---|---|
| 보존 우선 | 04, 05, 06, 09, 13, 16, 18, 19, 24, 25, 27, 29, 34, 37, 42, 43, 44 | 대본의 흐름을 공간·소품·색 대비·캐릭터 행동으로 명확히 표현 | 장면별 물리 은유와 다양한 공간/의상 선택이 잘 작동 | 참조 범위와 회귀 기준으로 보존 |
| 숫자·텍스트 중심 과밀 | 00, 01, 07, 16, 20, 21, 23, 26, 33, 35, 38, 40, 45, 46 | 정보가 장면 소품보다 큰 숫자판·순위표·표지판으로 먼저 보임 | Claude 프롬프트가 검증 값을 “크고 읽게 직접 쓰라”고 강제 | prompt-stage 표면 계획 + 수치 결정론 렌더링 |
| 한국어 오탈자·이탈자 | 01, 02, 07, 15, 35, 40 및 작은 한국어가 있는 다수 장면 | 승인 문구가 훼손되거나 의사 한글이 생성됨 | Gemini 래스터 문자 한계, 작은 크기, 장식적 글꼴, OCR 단일 검사의 누락 | 장면 로컬 허용 목록 + 멀티모달 QA + 국소 재생성/결정론 합성 |
| 임의 영문·숫자 | 01, 02, 12, 17, 21, 22, 26, 31, 34, 36, 39, 41, 44, 47 | 대본에 없는 보조 표식·목록·수치·Silver 등장 | leaderboard/control-room/comic 구도가 빈 표면을 채우도록 유도; prompt-stage 오염 | 프롬프트 허용 목록 검사와 출력 visible-text 대조 |
| 의미 엔티티 변경 | 02, 14, 20, 26, 36, 39, 46, 47 | 일반 경고→Silver, 개인/외국인→Gold/Silver, KOSPI→KOSDAQ 등 | Claude 장면 프롬프트가 승인 엔티티를 다른 금융 클리셰로 치환 | Gemini 호출 전 narration/entity/prompt 대조 |
| 캐릭터 정체성 편차 | 02, 08, 일부 20·28 | 경찰·경비원 인상, 다른 얼굴 구조·눈·표정 | 고정된 큰 캐릭터 비율, 강한 직업 의상, 단일 정체성 참조와 장면 프롬프트 충돌 | 얼굴 “단일 고정”이 아닌 승인 장면 범위 참조 + 시각 QA |
| 해부학 오류 | 11, 일부 복잡한 제스처 장면 | scene 11의 손 3개 | `pointing`과 `arms crossed`의 동시 지시 | action 슬롯을 양팔 단위로 정규화하고 최종 캐릭터 무결성 QA |
| 말풍선 무단 생성 | 47 | 프롬프트에 없는 질문 말풍선 | 만화 장르 관습과 “시장 질문” 문맥을 Gemini가 자율 보완 | `bubble_policy=forbidden` 기본, 장면별 예외 |
| 과도한 경보실 반복 | 02, 08, 20, 21, 28, 39, 42, 44 | 붉은 모니터·경광등·하락 화살표 반복 | risk/control-room 아키타입 과선택 | 연속 아키타입 회피와 공간 다양성 검사 |
| 양호하나 문자 QA 필요 | 03, 10, 12, 17, 22, 23, 28, 30, 31, 32, 33, 38, 41, 45, 46 | 핵심 구도는 이해 가능하지만 작은 표식·보조 정보의 정확성은 미보장 | 장면 정보 밀도는 좋으나 생성 문자와 보조 엔티티 검증 부족 | 장점 보존 후 텍스트·엔티티 게이트 적용 |

## 6. Job 52 이후 변경·개선 사항

현재 미커밋 코드에는 다음 보완이 들어 있다.

### 6.1 장면 로컬 텍스트 계약

- `image_text_contract.py`
  - 모든 문자를 금지하지 않는다.
  - `scene.screen_texts`와 `scene.screen_text_plan`만 허용 원천으로 사용한다.
  - 승인 비수치 문자열과 금융 수치를 분리한다.
  - 허용 목록 밖의 따옴표·표지판·디스플레이 지시를 감지하고 중립 표면으로 정리한다.
  - Gemini API 경계에 위반 지시가 남으면 실패한다.
- `scene_screen_text_planner.py`
  - 승인 내레이션 원문에서 회사명·지수명·금융 용어·인용구·수치를 장면별로 추출한다.
  - 수치를 새로 만들거나 반올림하지 않는다.
  - 기존 사람이 명시한 `screen_texts`는 보존한다.

### 6.2 수치와 비수치 문구 분리

- 비수치 승인 문구: Gemini가 장면 속 모니터·인쇄물·기계 표면에 직접 쓸 수 있다.
- 지수값·등락률·금액·배수 등 금융 수치: Pillow/FFmpeg의 결정론 표면 렌더러로 보낸다.
- 생성 모델에는 수치를 장면 의미 이해용으로 전달할 수 있으나 base raster에 직접 쓰게 지시하지 않는다.
- 최종 합성 문구는 승인 문자열 해시와 렌더 영역 픽셀 해시를 남긴다.

### 6.3 오탈자·이탈자 검수

- Tesseract `kor+eng` OCR을 축소본에 적용하고 PSM 11/6을 교차 사용한다.
- 숫자는 두 OCR 모드가 동일 숫자열과 동일 위치에 동의해야 실제 숫자로 판정한다.
- 생성 비수치 문구는 OCR만으로 합격시키지 않고 멀티모달 시각 QA의 `visible_texts`와 장면 허용 목록을 함께 사용한다.
- 결정론 렌더링 수치는 OCR이 한글을 오판해도 승인 문자열 해시와 렌더 직후 픽셀 해시가 모두 같을 때만 통과시킬 수 있다.
- 국소 텍스트 수리와 표면별 감사 파일을 지원한다.

이 전략은 방향은 사용자 의도와 일치하지만 **완료 상태는 아니다**. Job 54의 현재 이미지에는 여전히 잘못된 수치판, 과도한 고정형 표면, 작은 의사 문자, 혼합된 과거/신규 계약 결과가 있다. 또한 OCR은 작은 한국어를 놓칠 수 있고 Gemini 시각 QA가 503이면 검수가 완결되지 않는다. 따라서 “OCR 미검출=정확”으로 승인하면 안 된다.

### 6.4 Job 52 화풍 범위 참조

- 단일 얼굴·단일 네이비 의상·단일 스튜디오를 고정하지 않는다.
- Job 52의 양호 장면에서 얼굴 범위와 장면 스타일 참조를 추출했다.
- 장면 프롬프트 의미에 따라 최대 3장만 선택한다.
  - 얼굴 범위 1장
  - 반도체/생산, 위험/날씨, 수급 흐름, 브리핑 중 가까운 장면 참조 2장
- 참조에서 글자·숫자·말풍선·소품·구도를 그대로 복사하지 말고 선화, 셀 셰이딩, 정보 밀도, 장면별 색 분위기와 자연스러운 물리 표면 처리만 참고하도록 한다.

이 변경은 Job 52와 “같은 한 장”을 복제하는 것이 아니라 Job 52의 넓은 허용 범위를 유지하기 위한 것이다.

### 6.5 캐릭터 무결성

- 얼굴을 하나의 표정·눈·의상으로 고정하지 않는다.
- round coin species, embossed rim, 읽히는 표정, compact cartoon anatomy, dark-ink language만 공통 범위로 본다.
- 눈 구조, 홍조, 코, 입, 의상, 모자, 행동, 크기, 위치는 장면별로 달라질 수 있다.
- 양팔 행동을 서로 모순되게 요구하지 않도록 계약을 정규화하고, 추가 손·팔·캐릭터를 최종 QA에서 차단한다.

## 7. Job 54가 이미지 생성 중처럼 보이는 이유

### 7.1 데이터베이스 상태

2026-08-26 점검 시점의 `video_job` 행은 다음과 같다.

| 항목 | 값 |
|---|---|
| id | 54 |
| status | `IMAGES_PENDING` |
| cost_accumulated | ₩16,203 |
| budget_cap | ₩40,000 |
| Gemini 이미지 예산 | ₩15,000 |
| target | 5분 |
| created_at | 2026-08-25 02:26:52 |
| updated_at | 2026-08-25 19:18:11 |

Spring asset 테이블에는 KEYWORD, SCRIPT, TTS_AUDIO만 있고 SCENE_IMAGE 자산은 없다. 이미지 워커 컨테이너에는 현재 `uvicorn`만 실행 중이며 이미지 생성 요청 프로세스는 없다. 따라서 UI의 “이미지 생성”은 실행 중 활동이 아니라 완료되지 않은 상태값 표시다.

### 7.2 실제 Gemini 비용 발생

`/app/data/jobs/54/cost_ledger.json` 감사 결과:

| 종류 | 건수 |
|---|---:|
| 전체 원장 항목 | 130 |
| Gemini Pro 요청 | 125 |
| Gemini Flash 이미지 요청 | 1 |
| overlay vision | 4 |
| HTTP 200 | 65 (`Pro` 64 + `Flash` 1) |
| HTTP 503 | 38 |
| HTTP 504 | 11 |
| network error | 3 |
| 예약 후 미정산 `reserved` | 9 |
| 이미지 워커 원장 합계 | ₩13,865 |

사용자가 Gemini 실제 청구를 확인한 것이 맞다. Job 54는 생성하지 않은 것이 아니라, **여러 번 부분 생성·거절·재생성한 뒤 단계 완료에 실패한 상태**다. Spring 누적 비용 ₩16,203과 이미지 원장 ₩13,865의 차이는 TTS/LLM/QA 등 다른 단계 비용 및 서로 다른 원장 집계 범위에서 나온다.

### 7.3 불완전한 산출물

- 현재 `scene_000.png`부터 `scene_025.png`까지 파일이 존재한다.
- `images_manifest.json`에는 scene 00~20, 22~24만 있어 scene 21과 25가 누락돼 있다.
- `*_rejected`, `*_pre_v2_numeric`, `*_static_overlay_rejected`, `*_surface_smear_rejected`, `*_blur_rejected`가 남아 있다.
- scene 21 부근에서 반복된 503이 관찰됐다.
- planned scene 수는 56인데 scene 26 이후는 생성되지 않았다.
- 이 상태에서 단순 resume를 하면 최신 계약과 과거 생성물이 섞일 수 있으므로, 참조·프롬프트·텍스트 계약 fingerprint를 비교한 뒤 재사용 여부를 결정해야 한다.

현재 진행 접촉시트:

- `artifacts/job54_progress_contact_sheets_20260826/job54_scene_00_15.jpg`
- `artifacts/job54_progress_contact_sheets_20260826/job54_scene_16_31.jpg`
- `artifacts/job54_progress_contact_sheets_20260826/job54_scene_32_47.jpg`

생성되지 않은 칸은 `NOT GENERATED`로 표시했다. 이 시트는 새 Gemini 호출 없이 현재 디스크 산출물만 배열한 것이다.

## 8. Fal 적용 상태와 안전 범위

Job 54의 `fal_motion_plan.json`은 사전 계획일 뿐 Fal 호출 결과가 아니다.

- `fal_called=false`
- 계획 장면: 56
- 선택 후보: 2
- 이미지 OCR 전 적격 후보: 2
- 실제 Fal API 호출: 0

현재 원칙:

1. 텍스트·숫자·차트·기사 캡처·정보 표면이 있는 장면은 Fal 대상에서 제외한다.
2. Fal은 다음과 같은 장면 로컬 물리 요소만 움직인다.
   - 반도체: 웨이퍼 컨베이어 또는 회로의 빛 흐름 하나
   - 폭락/하락: 붉은 화살표나 하락선 하나
   - 환율/수급: 게이지 바늘 또는 흐름 표식 하나
   - 발표/선물: 커튼, 리본, 상자 중 하나
   - 캐릭터: 얼굴 반응과 한쪽 팔의 작은 동작
3. 다음 요소는 고정한다.
   - 카메라 위치와 줌
   - 화면 가장자리와 전체 배경
   - 모든 문자·숫자·차트 표면
   - 캐릭터 얼굴 구조와 사지 개수
4. 다음 결과는 차단한다.
   - 전 화면 지글링·노이즈
   - 전역 카메라 흔들림
   - 글자·숫자 재그리기
   - 배경 전체 물결 왜곡
   - 추가 손·팔·캐릭터
5. 생성 후에는 저해상도 프레임의 변경 픽셀 비율, 활성 타일 비율, 테두리 변경 비율로 국소 움직임인지 검사하고, 최종 프레임의 결정론 문구·픽셀 해시도 다시 확인한다.

현재 Fal 구현은 안전 계약과 사전 계획까지 있으며 Job 54에서 실제 품질 검증은 아직 하지 않았다. 정지 이미지 00~전체가 먼저 승인돼야 Fal 후보를 고정할 수 있다.

## 9. 다음 실행 기준

1. Job 54 현재 00~25를 접촉시트로 검토한다.
2. Job 52 보존 장면과 비교해 화풍·색감·정보 밀도·캐릭터 범위·물리 표면 처리를 평가한다.
3. prompt-stage 의미 오류, 생성 텍스트 오류, 수치 합성 오류, 캐릭터/해부학 오류를 서로 다른 실패 유형으로 기록한다.
4. 수정 fingerprint와 맞지 않는 Job 54 기존 이미지는 재사용하지 않는다.
5. 소수 장면 파일럿에서 각 실패 유형이 사라진 것을 확인한 뒤 나머지 장면으로 확대한다.
6. 모든 정지 이미지 승인 전에는 Fal, MP4 조립, 썸네일을 실행하지 않는다.

## 10. 검증 한계

- Gemini 콘솔의 최종 청구액은 API 응답에 포함되지 않으므로 원장의 원화 금액은 환경 설정 단가 기반 예상치다. 사용자가 본 콘솔 청구와의 최종 대조가 필요하다.
- Tesseract는 작은 한글과 장식 글꼴을 놓칠 수 있다.
- 멀티모달 QA가 503/504로 실패하면 문자·캐릭터 검수가 완결되지 않는다.
- 생성 모델이 승인 문자열을 직접 쓰는 전략은 허용하지만 정확성은 생성 후 검수와 재생성/국소 수리를 통과해야만 인정한다.

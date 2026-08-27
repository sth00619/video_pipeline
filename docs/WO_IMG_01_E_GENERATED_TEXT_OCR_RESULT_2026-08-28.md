# WO-IMG-01-E — 승인 문자 OCR·의사문자 오프라인 보완 결과

## 1. 결론

유료 API를 호출하지 않고, 짧은 승인 문구를 이미지 모델이 직접 쓰는 선택 레인에만 엄격 OCR 계약을 추가했다. 일반 장면의 기존 문자 허용 경로와 결정론 렌더 경로는 전역 변경하지 않았다.

- 승인 목록 밖의 OCR 문자·숫자는 더 이상 검토 대상으로만 넘긴 채 1차 게이트를 통과하지 않는다.
- 승인 문구는 전체 프레임 PSM 11, 전체 프레임 PSM 6, 2열×3행 국소 타일 PSM 6 순서로 정확 대조한다.
- 공백만 정규화하며 접두·접미 글자, 부분 문자열, 번역, 축약은 허용하지 않는다.
- 같은 OCR 행에서 `전`·`망`·`치`처럼 분할된 완전 연속 토큰은 `전망치`로 복원한다.
- 기존 8장 보존 PNG에서 scene35의 `경고`와 `전망치`를 모두 자동 검출했다.

이번 수정만으로 의사문자가 모두 해결됐다고 판정하지 않는다. scene15의 배경 의사문자는 Tesseract의 의미 있는 토큰 임계값에서 검출되지 않았으므로 기존 멀티모달 시각 QA가 계속 필요하다. scene47의 `질문`도 아직 OCR 미검출이다. 따라서 새 유료 이미지·Fal·TTS·조립 단계는 시작하지 않는다.

## 2. 선행 실패 재현

선행 테스트 커밋: `ec7f334`

| 명세 | 수정 전 결과 | 실제 결함 |
|---|---:|---|
| 엄격 레인의 `RISK`, `2021` | 실패 | `review_required`에만 기록되고 `passed=true` |
| `경고`, `전망치` 중 `경고`만 OCR | 실패 | 누락 문구를 검사하지 않아 통과 |
| `전`·`망`·`치` 분할 OCR | 실패 | 정확 문구 복원·감사 필드 없음 |

원문: [red.xml](evidence/wo_img01_e_generated_text_ocr_20260828/red.xml), [archive-red.xml](evidence/wo_img01_e_generated_text_ocr_20260828/archive-red.xml)

작업 트리 재현과 `git archive ec7f334` 격리 재현은 모두 **3 failed, 21 passed**다.

## 3. 최소 수정

수정 커밋: `df86769`

### 3.1 선택형 엄격 계약

`generated_text_ocr_policy`가 다음을 명시한 장면에만 적용한다.

```json
{
  "version": "strict-scene-local-generated-text-v1",
  "require_all_approved": true,
  "reject_unapproved": true,
  "targeted_exact_retry": "local_2x3_tiles_psm6"
}
```

8장 파일럿의 `pilot_only_short_approved_label_measurement` 레인이 이 계약을 명시적으로 선택한다. 기존 일반형 이미지, 기사형, 결정론 정보 표면, 승인 대본 원문에는 소급 적용하지 않는다.

### 3.2 의사문자 판정

엄격 레인에서는 다음을 모두 실패로 분류한다.

- 승인 목록에 없는 읽을 수 있는 한국어·영어
- 승인 목록에 없는 숫자
- 승인 문자열을 포함하지만 접두·접미 글자가 추가된 변형
- 승인 문구 누락

기존 일반 레인의 `PRESS`, `OUTLOOK` 같은 문맥형 비수치 표기를 멀티모달 검토로 넘기는 경로는 보존했다. 새 계약이 기존 동작을 전역 대체하지 않도록 한 것이다.

### 3.3 `전망치` 국소 재판독

2K 만화 전체를 960px 폭으로 축소한 희소문자 OCR은 배경 선화와 캐릭터 때문에 큰 라벨도 놓칠 수 있었다. 누락 승인 문구가 있을 때만 다음 보조 경로를 사용한다.

1. 전체 프레임 PSM 11
2. 전체 프레임 PSM 6
3. 누락 문구가 남으면 겹치지 않는 2열×3행 원본 국소 타일을 PSM 6으로 판독

국소 타일은 일반 OCR 결과를 느슨하게 합치는 경로가 아니다. 사전에 승인된 정확 문자열만 찾고, 실제로 찾은 타일 좌표와 판독 소스를 감사 필드에 남긴다.

## 4. 보존 PNG 실제 OCR 결과

이미지 재생성 없이 기존 파일의 SHA-256을 대조하고 Tesseract 5.5.0으로 다시 읽었다.

| scene | 승인 문구 | 새 정확 검출 | 비승인 OCR | 판정 |
|---:|---|---|---|---|
| 02 | `경고` | 없음 | `RISK`, `ill` | 엄격 레인 실패. 기존 비승인 영문을 자동 차단 |
| 15 | `엇갈림` | `엇갈림` — 전체 PSM 6 | 없음 | 승인 문구 OCR 복원. 육안 의사문자는 OCR이 못 잡아 시각 QA 계속 필요 |
| 35 | `경고`, `전망치` | `경고` — 전체 PSM 11, `전망치` — 타일 `[0,1024,1376,1536]` PSM 6 | 없음 | 기존 `전망치` false negative 해소 |
| 47 | `상반기 실적`, `질문` | `상반기 실적` | `상반기` | `질문` 미검출로 계속 보류 |

원문: [real-ocr.json](evidence/wo_img01_e_generated_text_ocr_20260828/real-ocr.json)

이 표의 `비승인 OCR 없음`은 화면에 의사문자가 없다는 뜻이 아니다. Tesseract가 의미 있는 문자열로 판독한 비승인 토큰이 없다는 뜻이다. 특히 scene15는 육안 문제 판정을 유지한다.

## 5. Job52 계열에 대한 구체적 개선 효과

- scene02와 같은 화면의 `RISK` 반복은 승인 `경고`가 맞더라도 최종 통과할 수 없다.
- scene35처럼 승인 한국어가 육안상 정확하지만 전체 프레임 OCR이 놓친 경우, 배경을 다시 생성하거나 문구를 무문자화하지 않고 해당 물리 영역을 국소 재판독한다.
- scene15의 `엇갈림`은 글자별로 분리돼도 정확한 연속열이면 승인 문구로 증명된다.
- `비전망치`, `전망치율`처럼 승인 문자열을 포함한 다른 단어는 정확 문구로 인정하지 않는다.

Job52 원본 48장이나 현재 동결 장면을 재생성·교체한 것은 아니다. 동일 문제를 다음 작업에서 반복하지 않도록 이미지 생성 뒤의 공통 검증 경로를 보완했다.

## 6. 검증

| 검증 | 결과 | 원문 |
|---|---:|---|
| 수정 후 집중 검사 | 50 passed | [green-focused.xml](evidence/wo_img01_e_generated_text_ocr_20260828/green-focused.xml) |
| `git archive df86769` 독립 집중 검사 | 50 passed | [archive-green.xml](evidence/wo_img01_e_generated_text_ocr_20260828/archive-green.xml) |
| 자산을 포함한 격리 전체 오프라인 검사 | 1083 passed, 1 deselected, 20 warnings | [full-offline.xml](evidence/wo_img01_e_generated_text_ocr_20260828/full-offline.xml) |

### 6.1 red 24건과 green 50건의 범위 차이

두 수치는 같은 파일 집합을 전후 비교한 값이 아니다. 선행 실패 재현은 결함을 직접 소유한 두 파일만 실행했고, 수정 후 집중 검사는 공용 OCR 판정이 연결되는 파일럿 정책과 Fal 안전성 회귀까지 범위를 넓혔다.

| 테스트 모듈 | 이전 전체 기준 | red 집중 | green 집중·현재 전체 | 이번 신규 |
|---|---:|---:|---:|---:|
| `test_image_text_contract.py` | 12 | 13 | 13 | +1 |
| `test_generated_image_text_gate.py` | 9 | 11 | 12 | +3 |
| `test_gemini_eight_scene_pilot.py` | 2 | 미실행 | 3 | +1 |
| `test_fal_motion_safety.py` | 22 | 미실행 | 22 | 0 |
| 합계 | 45 | 24 | 50 | +5 |

따라서 red에서 green으로 보이는 26건 증가는 다음과 같이 분해된다.

- 수정 단계에서 추가된 `test_generated_image_text_gate.py` 1건
- green 명령부터 포함한 `test_gemini_eight_scene_pilot.py` 3건(기존 2건 + 신규 1건)
- green 명령부터 포함한 기존 `test_fal_motion_safety.py` 22건

즉 `1 + 3 + 22 = 26`이며, 신규 테스트가 26개 생겼거나 전체 회귀에서 누락된 것이 아니다. red 커밋에 먼저 추가된 3건은 이미 red의 24건 안에 들어 있으므로 red→green 차이에는 나타나지 않는다.

### 6.2 전체 회귀 증가분 대조

직전 WO-PROVIDER-01 전체 원문은 1,079건이었다. 이번 실제 신규 테스트는 위 표처럼 5건이고, 현재 격리 전체 검사에서는 네트워크 의존 기존 Google RSS 테스트 1건을 명시적으로 제외했다.

```text
1,079 + 신규 5 - 외부 RSS 제외 1 = 1,083 passed
```

현재 [full-offline.xml](evidence/wo_img01_e_generated_text_ocr_20260828/full-offline.xml)에는 신규 5건의 정확한 테스트 이름이 모두 존재하고, 직전 [WO-PROVIDER-01 전체 XML](evidence/wo_provider_01_20260828/full-offline-green.xml)에는 존재하지 않는다. 따라서 새 테스트가 전체 스위트 컬렉션에서 빠진 정황은 없다.

제외한 한 건은 기존 Google RSS 외부 연결 테스트 `test_google_rss_fallback_when_naver_not_configured`다. 최초 격리 전체 검사에서는 참조 PNG·파일럿 명세·입력 자산을 복사하지 않아 23건, 이어 캐릭터 시트가 빠져 2건이 실패했다. 동일 커밋과 코드에 필요한 읽기 전용 자산을 포함한 최종 격리본에서는 위 표처럼 모두 통과했다. 중간 실패를 코드 회귀로 고쳐 쓰지 않는다.

## 7. 동결·비용·후속 경계

- Gemini·Claude·TTS·Fal/Kling 유료 호출: **0회**
- scene42 원장 SHA-256: `79a7e345f796824e1db409cd24bd3089d26bb502ef912bd221252a4d2a8cbc4f` 유지
- scene07·02·35 얼굴 재도전 원장 SHA-256: `933a479b16c952e03c6323a54af1e04b6c68c64ce295b473dd1c2382391e3838` 유지
- scene07·02·35·scene42 자동 재도전: 없음
- 상태 확인 attestation: 유료 재도전을 하지 않았으므로 새 객체를 만들지 않음
- Fal: 기존 fail-closed 유지. 문자 장면을 새로 허용하지 않음

다음 오프라인 우선순위는 scene15처럼 OCR이 놓치는 의사문자의 시각 QA 계보 강화, scene47 `질문`의 안전한 국소 판독, 결정론 레인의 빈 물리 표면 실패다. 별도 승인 전에는 유료 재도전을 하지 않는다.

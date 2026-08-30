# WO-PROVIDER-02 1단계 실 API 비교 결과

## 1. 결론

scene 07·15·28·35에 동일한 승인 대본, bounded prompt, 참조 이미지 3장,
텍스트 계약과 품질 하한선을 적용하고 `gemini-3-pro-image`와
`gemini-3.1-flash-image`의 모델 문자열만 바꿔 총 8회 요청했다. 8회 모두 HTTP
200으로 성공했다. 이번 표본에서는 503 가용성 차이가 관측되지 않았다.

Flash는 실측 비용이 더 낮고 일부 장면에서 얼굴·정보 밀도와 strict OCR 결과가
더 나았지만, 두 모델 모두 텍스트 및 물리 표면 계약에 실패한 장면이 있다. 따라서
이 결과만으로 운영 기본 모델을 바꾸거나 자동 Flash 폴백을 도입하지 않는다.
모든 결과는 사용자 전체 프레임 육안 검토 전까지 승인 차단 상태다.

## 2. 실행 불변식

- scene42는 요청하지 않았고 동결 상태를 유지했다.
- 장면×모델별 외부 POST는 1회이며 재시도는 0회다.
- 모델별 프롬프트를 만들지 않았다. 같은 장면 쌍은
  `final_prompt_sha256`과 참조 파일 SHA-256이 완전히 같다.
- service tier는 standard, 해상도는 2K다.
- 운영 기본값은 여전히 Pro다. Flash는 비교 하네스의 명시적 선택일 뿐 자동
  폴백 경로가 아니다.
- 실행 직전 Google Cloud 상태 페이지는 `No broad severe incidents`였지만,
  이는 두 모델의 개별 용량을 보증하지 않는다.

## 3. 사전 검사에서 발견해 공통 경로에 수정한 결함

최초 preflight에서 scene15·28·35도 고글 확대 얼굴 참조를 선택했다. 장면 자체가
아니라 공통 눈 계약의 `goggles or glasses must not erase...` 문장을 참조 선택기가
장면 요구로 오인한 것이 원인이었다. 또한 `risk control room`은 위험 장면으로
분류되지 않아 briefing 참조를 받았다.

공통 `select_contextual_reference_paths()`가 공통 하한선 앞의 장면 로컬 구간만
참조 선택에 사용하도록 수정했고, `risk control`·경고 신호를 위험/날씨 문맥으로
분류했다. 결과적으로:

- scene07: 얼굴 v2 + 고글 얼굴 확대 + 반도체 생산 화풍
- scene15: 얼굴 v2 + 반도체 생산/성장 화풍
- scene28·35: 얼굴 v2 + 위험 지도/시장 흐름 화풍

이 수정은 Job52 특정 결과 교체가 아니라 영상 생성 버튼이 타는 공통 V5 Gemini
참조 선택 경로에 적용된다. 회귀 테스트를 포함한 집중 검사는 15건 전부 통과했다.

## 4. 실측 결과

| scene | 모델 | HTTP | 시간(초) | 텍스트/표면 자동 게이트 | 실측 비용(USD) |
|---:|---|---:|---:|---|---:|
| 07 | Pro | 200 | 72.25 | 결정론 표면 검출 실패 | 0.144444 |
| 07 | Flash | 200 | 29.42 | 표면 렌더 후 최종 OCR 대조 실패 | 0.103590 |
| 15 | Flash | 200 | 33.63 | strict generated-text 실패: `엇갈림` OCR 누락 | 0.103111 |
| 15 | Pro | 200 | 47.70 | strict generated-text 실패: `엇갈림` OCR 누락 | 0.144700 |
| 28 | Pro | 200 | 35.93 | strict generated-text 실패: `대형주` OCR 누락 | 0.145064 |
| 28 | Flash | 200 | 67.80 | strict generated-text 실패: `대형주` OCR 누락 | 0.103274 |
| 35 | Flash | 200 | 30.26 | strict generated-text 통과 | 0.103843 |
| 35 | Pro | 200 | 32.49 | strict generated-text 실패: `경고` OCR 누락 | 0.143848 |

합계는 Pro `$0.578056`, Flash `$0.413818`, 전체 `$0.991874`다. 환율
₩1,400/USD 기준 약 ₩1,389다. Flash 실측 합계는 Pro보다 약 28.4% 낮았다.
비용은 응답 `usageMetadata`의 modality 세부 토큰으로 계산했다.

- Pro: 입력 `$2/M`, 이미지 출력 `$120/M`, 기타 출력·thinking `$12/M`
- Flash: 입력 `$0.50/M`, 이미지 출력 `$60/M`, 기타 출력·thinking `$3/M`

공식 가격 근거:

- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/image-generation

## 5. 육안 예비 관찰 — 최종 판정 아님

- scene07: Pro는 두 용기와 빈 화면 관계가 단순하지만 화면 비중이 크고 안전한
  표면 검출에 실패했다. Flash는 실험실 정보 밀도와 얼굴 층 구조가 더 풍부하지만
  주변 용기가 많아 “제외할 두 기업”의 의미가 약해질 수 있다.
- scene15: 두 모델 모두 승인 문자열 주위에 대괄호를 생성했다. Flash의 얼굴은
  v2 범위에 더 가까워 보이지만, 해당 표기는 사용자 육안으로 승인할 수 없다.
- scene28: 두 모델 모두 승인되지 않은 `KOSPI`를 추가했고, Flash는
  `[대형주]`처럼 괄호까지 만들었다. 둘 다 운영 승인 대상이 아니다.
- scene35: 두 모델 모두 육안상 `전망치`, `경고`를 표시했다. Flash만 strict
  게이트를 통과했으며 Pro 실패는 OCR false negative 가능성이 있으므로 실물과
  원본 해상도 국소 OCR을 함께 봐야 한다.

해부학·화풍·장면 의미는 자동 OCR과 별개다. contact sheet와 각 raw 이미지가
사용자에게 첨부되어 다음 다섯 항목을 직접 확인하기 전까지 `개선됨`, `승인 근접`,
`모델 우세`로 확정하지 않는다: 캐릭터 해부학, 화풍, 장면 의미, 텍스트와 물리
표면, 예상 밖 시각 결함.

## 6. 정보 포화 판단과 다음 단계

현재 4장으로 다음은 이미 확인됐다.

1. 두 모델 모두 동일한 3장 참조와 2K GenerateContent 계약으로 실행 가능하다.
2. 이번 구간의 가용성은 둘 다 4/4 성공이었다.
3. Flash는 비용이 낮지만 엄격한 텍스트·표면 계약을 자동으로 해결하지 않는다.
4. 모델 차이보다 공통 프롬프트의 문자열 표기 방식과 OCR 재현율 문제가 여전히
   결과를 크게 좌우한다.

반면 캐릭터·화풍·정보 밀도 우열은 사용자 실물 검토 없이는 확정할 수 없다.
따라서 2단계 10~15장 확대는 비용 때문에 막은 것이 아니라, 사용자 육안 판정이
없는 상태에서 표본만 늘리면 같은 불확실성을 반복하므로 현재 보류한다. 사용자
판정 후 모델 차이가 명확하지 않을 때만 2단계 확대가 새 정보를 제공한다.

## 7. 증거

- 명세: `provider-comparison-spec.json`
- 실행 manifest: `artifacts/wo_provider_02_stage1_20260829/manifest.json`
- 요청 원장: `artifacts/wo_provider_02_stage1_20260829/request_ledger.json`
- contact sheet: `artifacts/wo_provider_02_stage1_20260829/provider_comparison_contact_sheet.png`
- 장면별 raw/결정론 preview/최종 prompt: 같은 artifact 디렉터리

# WO-PROVIDER-02 모델 정책 리서치 출처 원장

- 조사일: 2026-08-30
- 질문: 비용을 우선 제약으로 두지 않을 때 `gemini-3.1-flash-image`로 빠르게 전환할지, `gemini-3-pro-image` 정책을 유지할지
- 원칙: 공식 1차 자료를 우선하고, 포럼·오픈소스·공급자 사례는 보조 근거로만 사용한다.

| 등급 | 출처 | 이 보고서에서 사용하는 주장 | 한계·주의 |
|---|---|---|---|
| 1차 | [Gemini API changelog](https://ai.google.dev/gemini-api/docs/changelog) | 2026-05-28 Flash Image와 Pro Image가 GA로 전환됐고 preview 모델은 2026-06-25 종료됐다. | 현재 503을 preview 지위로 설명할 수 없다. |
| 1차 | [Gemini image generation guide](https://ai.google.dev/gemini-api/docs/image-generation) | Flash는 속도·대량 처리, Pro는 전문 자산·복잡한 지시 중심이다. Pro는 최대 5개 캐릭터/6개 객체, Flash는 최대 4개 캐릭터/10개 객체의 고충실도 참조 안내가 있다. 텍스트 생성은 항상 정확하지 않다. | 마케팅성 요약이므로 실제 채널 계약 통과율은 로컬 실험으로 검증해야 한다. |
| 1차 | [Gemini 3 Pro Image model page](https://ai.google.dev/gemini-api/docs/models/gemini-3-pro-image) | Pro는 복잡한 그래픽 디자인, 제품 목업, 정확한 텍스트가 필요한 사실 기반 데이터 시각화를 겨냥한다. | 공급자 설명이지 이 저장소의 한국어 OCR·캐릭터 계약 보증은 아니다. |
| 1차 | [Gemini 3.1 Flash Image model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image) | Flash는 속도·고처리량을 겨냥하며 다국어 텍스트 렌더링을 개선했다. | 승인 문자열 무오류를 보장하지 않는다. |
| 1차 | [Gemini 3.1 Flash Image model card](https://deepmind.google/models/model-cards/gemini-3-1-flash-image/) | 전체 선호·시각 품질에서 Flash가 강하지만, 일반/캐릭터/객체·환경/다중입력 편집의 일부 축에서는 Pro가 동등하거나 우세하다. Flash의 알려진 한계에 작은 글자·긴 문단, 캐릭터 일관성, 좌우 공간 관계, 환각, 지연·타임아웃이 포함된다. | 공개 벤치마크는 Job52 화풍·한국어 금융 문구·결정론 오버레이 계약과 다르다. |
| 1차 | [GenerateContent image guide](https://ai.google.dev/gemini-api/docs/generate-content/image-generation) | Flash는 `thinkingConfig.thinkingLevel`의 `minimal`/`high`를 지원하며 기본값은 `minimal`이다. thinking 토큰은 노출 여부와 무관하게 과금된다. | 현재 Stage2 비교는 `thinkingConfig`를 보내지 않아 Flash 기본 minimal 조건이었다. |
| 1차 | [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) | Pro Image에는 Standard·Batch·Flex·Priority 가격이 있고 Flash Image 표에는 Standard·Batch가 제시된다. | 가격표는 변경될 수 있으므로 구현 시 다시 확인한다. |
| 1차 | [Gemini API optimization](https://ai.google.dev/gemini-api/docs/optimization) | Priority는 높은 중요도의 비차단 큐로 라우팅하며 동적 한도 초과 시 Standard로 완화된다. | 503을 완전히 제거한다는 보장은 아니다. 실제 계정·모델·지역에서 payload 수용과 원장 기록을 검증해야 한다. |
| 1차 | [Gemini API troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting) | 429/503에는 지수 백오프, jitter, 일시 오류 한정 재시도, 최대 시도 횟수를 권장한다. | 저장소는 이미 동등한 제어를 구현했으므로 무한 재시도 추가의 근거가 아니다. |
| 공식 예제 | [Google Cloud Flash Image Colab](https://colab.research.google.com/github/GoogleCloudPlatform/generative-ai/blob/main/gemini/getting-started/intro_gemini_3_1_flash_image_gen.ipynb) | 복잡한 Flash 이미지 생성에서 `thinking_level=HIGH`를 사용하는 공식 예가 있다. | 예제 성공이 채널의 품질 계약 통과를 보장하지 않는다. |
| 커뮤니티 | [Google AI Developers Forum: Pro high-demand 503](https://discuss.ai.google.dev/t/gemini-image-api-503-unavailable-high-demand-on-gemini-3-pro-image-preview/126785) | Pro 계열 503 high-demand가 외부 사용자에게도 관측됐다. | 사용자 보고이며 preview 시기 사례가 포함될 수 있다. 인과·빈도 일반화 금지. |
| 커뮤니티 | [Google AI Developers Forum: long prompt/reference 503](https://discuss.ai.google.dev/t/the-gemini-3-pro-image-preview-api-keep-getting-503-errors-for-hours/112188) | 긴 문맥·참조가 있는 요청에서 장시간 503을 겪었다는 사례가 있다. | GA 이전 일화다. 로컬 복잡 payload와 방향성만 비교한다. |
| 커뮤니티 | [Google AI Developers Forum: Flash image failures](https://discuss.ai.google.dev/t/gemini-image-generation-repeating-edge-artifacts-white-box-rendering-and-image-other-silent-failures/144669) | Flash에서도 HTTP 200 무이미지·시각 결함을 겪었다는 사례가 있다. | preview 시기 일화이며 현재 GA 품질로 일반화할 수 없다. |
| 공급자 사례 | [Google DeepMind Flash customer stories](https://deepmind.google/models/gemini-image/flash/) | 일부 실서비스가 Flash에서 큰 지연 단축과 텍스트/편집 품질을 보고한다. | 공급자 선정 사례이므로 독립 벤치마크보다 증거 등급이 낮다. |
| 오픈소스 | [CxOAGI/gemini-media-mcp](https://github.com/CxOAGI/gemini-media-mcp) | 모델과 thinking level을 별도 선택값으로 노출한다. | 채택 사례이지 품질 비교 증거가 아니다. |
| 오픈소스 | [spf13/gemini-image](https://github.com/spf13/gemini-image) | Flash를 일반 기본값, Pro를 전문·복잡 작업 선택지로 제공한다. | 이 저장소와 요구사항이 다르며 정책 아이디어만 참고한다. |

## 로컬 1차 증거

| 증거 | 확인한 사실 |
|---|---|
| `WO_PROVIDER_02_STAGE2_FULL47_RESULT_2026-08-29.md` | scene42를 동결한 47장 쌍대 비교. Pro 44/47 HTTP 200, Flash 46/47. 평균 지연 Pro 46.46초, Flash 31.47초. 승인 생성문자 정확성은 Pro 36/36, Flash 33/35. Flash는 비승인 영문·숫자·순위·티커·의사문자를 더 자주 추가했다. |
| Stage2 요청 원장 | 성공 응답에서 Pro thinking 토큰 합계 9,426, Flash 0. 현재 Flash 요청이 기본 `minimal` 조건이었다는 코드·공식 계약과 일치한다. |
| `WO_PROVIDER_02_SCENE00_FLASH_REPRODUCTION_RESULT_2026-08-29.md` | 콘택트시트 검은 칸은 malformed 이미지가 아니라 503에 따른 raw 부재였다. 동일 payload Flash 재시도 2/2는 정상 구도였으나 `KOSPI`, `PER 4배`, 비승인 문장 등 텍스트 계약 위반이 2/2 발생했다. |
| 운영 코드 감사 | 현재 버튼 운영 계약은 `gemini-3-pro-image` 고정이다. 공통 provider는 두 모델을 호출할 수 있으나 Flash `thinkingConfig`는 payload에 포함하지 않는다. |
| Stage2 harness 감사 | 비교 harness는 승인 내레이션 전체를 semantic basis로 노출했다. 결정론 수치가 base raster에 복제된 현상이 운영 버튼에도 동일하다고 아직 증명되지 않았다. |

## 출처 사용 결론

- 공식 문서와 로컬 결과가 함께 지지하는 결론만 운영 결정에 사용한다.
- 커뮤니티 사례는 503 또는 출력 결함의 “존재 가능성”만 보조하며 모델 우열의 정량 근거로 쓰지 않는다.
- Stage2는 Flash `minimal` 비교다. 따라서 Flash의 최종 품질 상한을 측정한 실험으로 해석하지 않는다.
- 그렇더라도 현재 검증된 결과만으로 Flash를 전역 기본값으로 바꾸는 근거는 부족하다.

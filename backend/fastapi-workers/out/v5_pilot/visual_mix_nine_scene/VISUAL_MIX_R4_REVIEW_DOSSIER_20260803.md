# V5 9장 시각 혼합 검수 dossier

검수일: 2026-08-03  
범위: 기사형 3장 · 상황형 3장 · 정보형 3장  
후속 단계: 이미지 재검수 전 Kling·MP4·썸네일 미진행

## 공통 판정 기준

- 두꺼운 검정 잉크 윤곽선·셀 셰이딩·갈색 페도라/네이비 슈트/흰 장갑 캐릭터 정체성
- 말풍선, 검은 요약칩, 제목 카드, 부유 텍스트 없음
- 정확 수치·퍼센트·통화·축 눈금 없음. 하락은 파란 선·화살표, 의미형 흐름은 무라벨 도형만 사용
- 영문 문구는 대본 의미에 맞고 장면 안의 하나의 물리 소품 표면에 결합
- 기사형은 검증 기사 원문과 노란 하이라이트·빨간 밑줄·출처만 사용

## 선택 산출물과 판정

| 유형 | 장면 | 선택 파일 | 판정 | 근거 |
| --- | --- | --- | --- | --- |
| 기사형 | article_kospi | `visual_mix_nine_scene_r4_info_retry_20260803/article_kospi.png` | 통과 | 실제 기사 캡처, 출처 표기, 강조 문장 밑줄·하이라이트 |
| 기사형 | article_us_market | `visual_mix_nine_scene_r4_info_retry_20260803/article_us_market.png` | 통과 | 실제 기사 캡처, 출처 표기, 강조 문장 밑줄·하이라이트 |
| 기사형 | article_sector | `visual_mix_nine_scene_r4_info_retry_20260803/article_sector.png` | 통과 | 실제 기사 캡처, 출처 표기, 강조 문장 밑줄·하이라이트 |
| 상황형 | semantic_rates_flow | `visual_mix_nine_scene_r4_semantic_rates_layout_retry_20260803/semantic_rates_flow.png` | 통과 | 미국→한국 자금 흐름을 지도·화살표·기상 대비로 표현, 무문자·무수치 |
| 상황형 | semantic_bigtech_ai | `visual_mix_nine_scene_r4_remaining_five_20260803/semantic_bigtech_ai.png` | 통과 | AI 투자와 수익 불확실성을 프로세서 파이프라인·터빈의 대비로 표현, 캐릭터 미사용 계약 준수 |
| 상황형 | semantic_chip_kospi | `visual_mix_nine_scene_r4_remaining_five_20260803/semantic_chip_kospi.png` | 통과 | 반도체 모듈·연결 기어·위험 소품으로 코스피 반등 조건을 비수치로 표현 |
| 정보형 | info_semiconductor | `visual_mix_nine_scene_r4_remaining_five_20260803/info_semiconductor.png` | 통과 | `SEMICONDUCTOR GOES DOWN`이 곡면 보드에 결합, 파란 하락 그래프, 고정 캐릭터 |
| 정보형 | info_dollar | `visual_mix_nine_scene_r4_info_retry_20260803/info_dollar.png` | 통과 | `DOLLAR UNDER PRESSURE`가 지도 벽에 결합, 파란 하락 그래프·국가 간 흐름 |
| 정보형 | info_fear | `visual_mix_nine_scene_r4_info_retry_20260803/info_fear.png` | 통과 | `FEAR IS COOLING`이 대형 아날로그 계기면에 결합, 수치 없는 진정 방향 표현 |

## 비용·계보

- 선택한 Gemini 생성 6장은 모두 `gemini-3-pro-image`와 V5 참조 자산을 사용했다.
- 선택본 기준 예상 누계는 약 ₩1,524이다. 최초 503 실패는 이미지 파일을 반환하지 않았고, 청구 실비는 Gemini 콘솔 대조 전까지 미확정이다.
- 각 요청 원장은 참조 자산 SHA-256, 참조 역할, 장면 유형 계약, archetype, 프롬프트 SHA-256을 보존한다.
- 첫 `semantic_rates_flow` 성공본은 UI/캐릭터 점유율 기준에서 불합격으로 제외했고, `layout_retry` 선택본으로 교체했다.

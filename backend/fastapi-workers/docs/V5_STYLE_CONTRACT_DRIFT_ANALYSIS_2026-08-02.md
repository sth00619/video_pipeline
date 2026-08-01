# V5 그림체 드리프트 원인 분석 및 스타일 계약

## 목적

7월 30일 승인된 8종 benchmark와 8월 1일 실제 4씬 파일럿의 그림체 차이를
파일·요청 기록으로 구분한다. 이 문서는 새 생성 결과를 통과 처리하지 않으며,
40씬 실행 전에 현재 실전 경로에 적용할 스타일 계약을 기록한다.

## 비교 대상

| 구분 | 산출물 | 생성 시각 | Gemini 호출 |
|---|---|---:|---|
| 승인 benchmark | `out/benchmark/gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_08_datalab.png` | 2026-07-30 01:23 KST | 있음 |
| 실제 정보형 파일럿 | `out/v5_pilot/kospi_july_2026/actual_four_scene/v5_actual_four_scene_pilot_20260801a/kospi_july_01_background.png` | 2026-08-01 05:09 KST | 있음 |
| 이후 trade/risk 재합성 | `out/v5_pilot/kospi_july_2026/primary_surface_revalidation_v2/` | 2026-08-01 19:09 KST | 없음 |

19:09 작업은 05시 Gemini 배경 PNG에 Pillow만 적용했다. 따라서 benchmark와
파일럿의 마스코트·무대 그림체 차이는 Pillow나 PNG 압축이 아니라 05시의 별도
Gemini 생성에서 이미 발생한 것이다.

## 확인된 입력 차이

| 항목 | 7/30 benchmark | 8/1 실제 파일럿 | 판정 |
|---|---|---|---|
| 모델 | `gemini-3-pro-image` | `gemini-3-pro-image` | 동일 |
| 해상도/비율 | 2K, 16:9 | 2K, 16:9 | 동일 |
| 서비스 티어 | standard | standard | 동일 |
| 참조 자산 | `character_reference_v2_textless`, `style_reference_v2_textless` | 동일 SHA-256 | 동일 |
| 텍스트 정책 | `strict_textless` | 정보형은 `diegetic_decorative` | 변경 |
| 라우팅 | benchmark `SceneSpec` 직접 호출 | `scene_type → archetype → primary-surface` 계약 | 변경 |
| 정보 표면 지시 | 후합성용 중간 공간만 예약 | primary 단일 표면·대체물 금지·비-primary 비문자 계약 | 변경 |
| 배치 지시 | `LayoutSketcher`의 layout contract 사용 | runtime 경로에서는 별도 layout contract 미전달 | 변경 |

## 재현성 한계

두 실행 모두 코드에서 `seed` 값을 기록했지만, Gemini HTTP payload의
`generationConfig`에는 `seed`, `temperature`, `topP`, `topK`가 전달되지
않는다. 따라서 기록된 seed는 API 난수 상태를 고정하지 못하며, 동일 프롬프트·참조
여도 결과가 달라질 수 있다. 모델 파라미터가 달라진 증거는 없지만, 현재 경로는
출력 미감을 결정론적으로 재현할 수 없다.

Git 이력은 `prompt_builder.py` 관련 변경이 아직 작업 트리에 커밋되지 않은 상태라,
7월 30일과 8월 1일 사이의 줄 단위 변경 이력을 Git만으로 완전히 복원할 수 없다.
대신 위 저장된 manifest와 request ledger가 실제 실행 계약 차이를 보존한다.

## 원인 판정

주된 원인은 참조 자산이나 모델명이 아니라 다음 두 가지의 결합이다.

1. `strict_textless` benchmark에서 `scene_type` 기반 `diegetic_decorative`
   정보형 프롬프트로 이동하면서 primary-surface·대체물 금지 문장이 대폭 추가됐다.
2. Gemini 출력 난수 상태가 고정되지 않아, 새 계약의 긴 제약과 별개로 그림체도
   요청마다 흔들릴 수 있다.

## 현재 운영용 스타일 계약

`V5_CINEMATIC_CARTOON_STYLE_CONTRACT` (`2026-08-02-cinematic-cartoon-recovery`)를
`build_prompt()`의 art direction에 추가했다. 이 계약은 다음을 요구한다.

- 균일한 굵기의 짙은 갈색 잉크 외곽선
- 경계가 읽히는 셀 셰이딩; 림 라이트·금속 반사·홀로그램 이외의 과도한 에어브러시 금지
- 장면 고유의 제한된 고채도 팔레트와 전경·중경·배경의 극장식 무대 깊이
- 단순하고 읽기 쉬운 원형 금화 마스코트 비율
- 3D 장난감 질감·프리미엄 반실사 일러스트·얇은 스케치 선·기업 인포그래픽 미감 금지

이 계약은 기존 11개 archetype의 primary-surface 규칙이나 검증 수치의
결정론적 렌더링 규칙을 변경하지 않는다.

## 다음 검증

현재 실전 경로에서 일반형 1장과 정보형 1장을 각각 1회 생성한다. 두 장은
`style_contract_version`을 실행 manifest에 기록하고, 기존 benchmark와 나란히
사람이 다음을 판정한다.

1. 마스코트 비율·눈·외곽선 일관성
2. 셀 셰이딩/조명/팔레트가 승인 benchmark와 같은 카툰 계열인지
3. 무대가 하나의 고밀도 세트로 읽히는지
4. 정보형의 AI 장식 정보가 primary 물리 표면에만 존재하는지

검토 전에는 40씬 또는 추가 대량 생성을 시작하지 않는다.

## 2026-08-02 현재 실전 경로 2장 비교 결과

승인된 비용 한도 안에서 실제 Gemini Pro 호출을 두 번만 수행했다. 두 요청은 모두
`max_attempts=1`, 자동 재시도 없음으로 성공했으며, 원장에는 장당 254원(합계 508원)
예약으로 남아 있다. 실제 콘솔 청구액 대조 전까지 비용 상태는
`unverified_until_console_reconciliation`이다.

| 구분 | 씬 | 결과 파일 | 판정 |
|---|---|---|---|
| 일반형 | `port_emergency` | `out/v5_pilot/kospi_july_2026/actual_four_scene/v5_style_contract_dual_20260802/general_port_narrative_04.png` | 스타일 계약 재현 실패 |
| 정보형 배경 | `data_lab` | `out/v5_pilot/kospi_july_2026/actual_four_scene/v5_style_contract_dual_20260802/kospi_july_01_background.png` | 스타일 계약 재현 실패 |
| 정보형 최종 | `data_lab` + Pillow 사실 오버레이 | `out/v5_pilot/kospi_july_2026/actual_four_scene/v5_style_contract_dual_20260802/kospi_july_01.png` | 오버레이 좌표는 primary 안으로 통과, 미감은 실패 |

확인된 사실은 다음과 같다.

1. 정보형의 검증 수치 카드가 지도 패널 내부의 지정 좌표에 들어갔다. 이번 결과는 과거의 좌상단 폴백 문제가 아니다.
2. 그러나 일반형과 정보형 모두 기존 성공본의 강한 극장식 명암, 소품 밀도, 균일한 굵은 선, 단순 셀 셰이딩보다 매끈한 벡터·프리미엄 일러스트 쪽으로 기울었다.
3. 따라서 새 스타일 문구를 추가했더라도 현재 `v4` 참조 자산 + 실전 런타임 경로가 사용자가 승인한 기존 성공 미감을 안정적으로 재현한다고 판정할 수 없다.
4. 이 두 장은 원인을 가리기 위한 비교 시도이며, 사용자의 시각 승인 전에는 40씬 또는 추가 대량 생성을 재개하지 않는다.

이번 결과는 "스타일 계약 적용 완료"가 아니라 "스타일 계약의 실제 효력 미달 확인"으로 기록한다. 다음 변경은 이 실패를 해결할 구체적 가설(참조 자산 구성, runtime 프롬프트 범위, 레이아웃 계약 복원)을 먼저 제시하고 승인받은 뒤에만 수행한다.

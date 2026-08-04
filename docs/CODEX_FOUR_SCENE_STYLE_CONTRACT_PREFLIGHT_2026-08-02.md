# 8월 코스피 4장면 스타일 계약 파일럿 — 사전검증

작성일: 2026-08-02  
상태: **사전검증 통과 · 이미지 API 미호출**

## 확정 정책

- 금융 수치, 사실 수치, Pillow 수치 오버레이를 사용하지 않는다.
- 대본의 의미를 짧은 영어 문구로 바꾸고, 그 문구는 표지판·스크린·게이지 같은 **실물 소품 표면**에만 넣는다.
- Gemini Pro 호출마다 캐릭터 참조와 화풍 참조 PNG를 함께 전달한다.
- 스타일은 굵은 검정 잉크 윤곽선, 셀 셰이딩, 갈색 페도라와 네이비 슈트의 금화 마스코트로 고정한다.

## 생성 계획

| 씬 | 장면 유형 | archetype | 소품 표면 문구 | 방향 |
|---|---|---|---|---|
| `kospi_august_semiconductor` | graph | `data_lab` | `SEMICONDUCTOR GOES DOWN` | 하락 |
| `kospi_august_dollar` | graph | `data_lab` | `DOLLAR UNDER PRESSURE` | 하락 |
| `kospi_august_fear` | metric | `risk_control_room` | `FEAR IS COOLING` | 하락 |
| `general_port_narrative_04` | general | `port_emergency` | 없음 | 서사 장면 |

## 비용 및 재현 정보

- 모델: `gemini-3-pro-image`
- 생성 수: 4장
- 자동 재시도: 없음
- 사전추정: **₩1,016** (장당 $0.14, 사전검증 시점 환율 기준)
- 참조 자산:
  - `character_reference_v4_identity_clean.png`
  - `style_reference_v4_medium_clean.png`
- 실행 입력: `backend/fastapi-workers/pilot-inputs/kospi_august_2026_style_contract_input.json`
- 사전검증 manifest: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/actual_four_scene/kospi_august_2026_style_contract_preflight/_manifest.json`

## 실행 전 차단 규칙

`verified_facts`, `v5_verified_overlays`, `market_chart`, `numeric_overlays` 중 하나라도 입력에 있으면 실행 스크립트가 이미지 API 호출 전에 실패한다. 따라서 이전의 숫자·출처·결정론적 오버레이 경로가 이 파일럿 결과에 섞일 수 없다.

## 다음 실행

사용자 승인 후 아래 명령에만 `--execute`를 붙여 4장을 생성한다. 생성 뒤에는 각 장면의 윤곽선, 페도라, 눈·뺨, 소품 표면 문구, archetype 단일성, 색감, 워터마크를 dossier로 판정한다.

```powershell
cd backend/fastapi-workers
python scripts/run_v5_four_scene_actual_pilot.py `
  --input pilot-inputs/kospi_august_2026_style_contract_input.json `
  --run-id kospi_august_2026_style_contract_actual `
  --execute
```

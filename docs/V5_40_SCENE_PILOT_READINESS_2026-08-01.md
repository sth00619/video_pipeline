# V5 40씬 파일럿 준비 현황 — 2026-08-01

## 결론

현재는 **3씬의 검증 입력과 V5 최종 이미지 계약은 준비되어 있으나, 40씬 전체의 검증 사실 세트는 아직 없다.** 따라서 실제 수치·출처 없이 40씬을 임의로 채우거나, 이미지 생성을 시작하지 않는다.

## 진입 조건 현황

| 조건 | 상태 | 근거/다음 조치 |
|---|---|---|
| 실제 검증 대본 | 부분 준비 | `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/v5_pilot_input.json`에 KOSPI 7월 3씬만 있음. 40씬 대본은 새로 수집·교차검증해야 함. |
| `verified_facts` + `v5_verified_overlays` | 부분 준비 | 3씬에는 출처 URL·사실값·좌표 계약이 존재. 나머지 37씬은 사실값과 출처가 없어 차단 상태가 맞음. |
| 이미지 비용 | 준비 | V5 Gemini Pro 추정단가는 환경변수 `V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD`로 설정돼 있다. 3씬 묶음은 `IMAGE_FINAL` ₩7,000 상한 아래에서만 시도한다. |
| 콘솔 대조 | 절차 준비 | 각 묶음 종료 직후 Gemini API Logs와 지출 콘솔을 대조하고, 원장에 `unverified_until_console_reconciliation`으로 남긴 추정치를 확정 또는 보정한다. |

## 실행 단위

```text
검증 사실 3–5씬 준비
→ 사전 비용 예약/드라이런
→ Gemini Pro 단건씩 (자동 재시도 없음)
→ 사람 시각 검토 + QualityGate
→ Gemini 콘솔 대조
→ 다음 3–5씬 묶음 승인
```

40씬 전량을 한 요청으로 실행하지 않는다. `IMAGE_FINAL`의 현재 ₩7,000 상한을 변경하지 않는다.

## 첫 묶음 후보

이미 출처와 오버레이 계약이 준비된 다음 3개가 A-3 및 40씬 운영 절차의 첫 묶음 후보이다.

| scene_id | scene_type | V5 archetype | 사실 오버레이 |
|---|---|---|---|
| `kospi_july_01` | `graph` | `data_lab` | 있음 |
| `kospi_july_02` | `graph` | `trade_calculator` | 있음 |
| `kospi_july_03` | `metric` | `risk_control_room` | 있음 |

## 40씬 확장에 필요한 입력 계약

각 신규 씬은 다음을 모두 만족해야 한다.

```json
{
  "scene_id": "stable_id",
  "narration": "검증된 대본 문장",
  "scene_type": "general | metric | graph | diagram | text",
  "verified_facts": [
    {
      "fact": "출처가 뒷받침하는 원문 사실",
      "figure": "검증된 표시값",
      "source_url": "https://...",
      "source_title": "출처 제목",
      "published_at": "ISO-8601",
      "confidence": 0.0
    }
  ],
  "v5_verified_overlays": [
    {
      "label": "표시 라벨",
      "value": "verified_facts의 값",
      "source_ref": "facts[0]",
      "anchor": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "kind": "physical_surface"}
    }
  ]
}
```

`metric`/`graph`/`diagram`은 위 두 배열이 모두 있을 때만 Pillow 사실 합성을 허용한다. `general`은 사실 오버레이 없이 V5 배경만 생성한다.

## 비용 계산 방식

1. 1장 추정 USD는 `V5_GEMINI_PRO_IMAGE_2K_ESTIMATE_USD`만 사용한다.
2. 호출 당일 `FX_USD_KRW`와 보수 버퍼로 원화 예약액을 계산한다.
3. 3장 최초 묶음의 사전 예약액과 `IMAGE_FINAL` 잔여액을 비교한 뒤에만 호출한다.
4. Gemini 응답에 실비가 없으므로 성공/실패 모두 원장은 `unverified_until_console_reconciliation`로 기록한다.
5. 콘솔 대조로 실제 지출·요청 수를 확인한 후 다음 묶음을 결정한다.

## 차단 규칙

- `earnings_stage`는 아직 `RENDER_BLOCKED_ARCHETYPES`에 남아 있으므로 어떤 묶음에도 넣지 않는다.
- 출처 URL, 사실 원문, 오버레이 값, 좌표가 하나라도 빠진 정보 씬은 렌더하지 않는다.
- 모델이 만든 장식 텍스트는 실제 사실로 취급하지 않는다.

## NAVER 검색 트렌드 추가 육안 검토 항목

2026-08-01 코드 확인 결과, `trend_charts[].ratio_note`와 `diagram_candidates[].rule`은 현재 데이터 팩에 보존되지만 각각의 렌더러가 이를 자동 강제하지는 않는다.

- `diegetic_trend_overlay.py`는 NAVER ratio 원문값을 그대로 그리지만, 자동으로 “검색 관심도”라는 뜻의 라벨을 더하지 않는다. 따라서 트렌드 그래프를 실제 영상에 넣기 전, 사람이 `NAVER 상대 검색 관심도` 또는 동등한 구분 문구가 화면에 있는지 확인해야 한다. `상승률`, `등락률`, `주가`처럼 금융 성과로 해석될 표현이면 실패다.
- `diagram_candidates[].rule`은 현재 인과 화살표를 자동 차단하는 코드가 아니라 데이터 계약 문구다. 별도 검토자의 명시 승인 기록 없이 화살표를 그린 다이어그램은 실패로 처리한다.

첫 3씬 검토표에는 아래 두 항목을 반드시 추가한다.

1. NAVER ratio가 주가 등락률·수익률로 오인될 표현 없이 **검색 관심도**로 표시됐는가.
2. 인과관계 화살표가 있다면, 씬 입력에 별도 검토 승인 근거가 있는가. 없다면 화살표가 없는가.

# Gemini Pro 4장면 파일럿 검수·재생성 운영 규약

최종 갱신: 2026-08-02  
대상: `graph`, `diagram`, `metric`, `general` 순서의 4장면 Gemini Pro 파일럿

## 목적과 안전선

- `graph`·`diagram`·`metric`의 검증 사실은 Gemini 프롬프트에 넣지 않는다. 각 장면의 `background.png` 생성 뒤에만 Pillow로 사실·출처·좌표를 합성한다.
- Gemini Pro 호출은 비용이 발생하므로 기본 동작은 dry run이다. `--execute`를 명시한 경우에만 외부 요청한다.
- 시스템은 자동 재생성하지 않는다. 사람의 `REGENERATE` 결정, 구체적인 사유, 그리고 검토한 후보 회차가 모두 있어야 재요청할 수 있다.
- OCR은 사람 검토를 돕는 참고값이다. OCR 결과·실패·미설치는 어떤 경우에도 자동 승인 근거가 아니다.

## 실행 단위와 보존 산출물

한 번의 파일럿은 `run-id`로 분리한다. 같은 실행의 재생성은 반드시 같은 `run-id`를 사용한다.

```text
backend/fastapi-workers/out/three_goals_e2e/<run-id>/
  cost_ledger.json
  report.json
  review_dossier.json
  candidates/<scene-id>/attempt-01/background.png
  candidates/<scene-id>/attempt-01/final.png
```

- `background.png`: Gemini Pro가 반환한 원본. 모델이 만든 숫자·문자·출처를 검토하는 기준 파일이다.
- `final.png`: 검증 장면에는 결정론적 Pillow 오버레이를 합성한 최종 파일이며, 일반 장면은 원본과 동일해야 한다.
- `cost_ledger.json`: 실제 제공자 요청마다 기록되는 비용 원장이다. 후보 회차별 장면 키와 요청 메타데이터를 확인한다.
- `review_dossier.json`: PNG 해시·해상도·OCR 상태·회차 이력·사람의 최종 결정을 모은 검수 원장이다.

## 실행 전 입력 계약

입력 JSON은 정확히 네 장면이며, 순서는 `graph`, `diagram`, `metric`, `general`이다.

- 앞의 세 장면은 `verified_facts`(또는 `facts`)와 `v5_verified_overlays`를 모두 가져야 한다.
- 각 오버레이는 유효한 `source_ref`와 primary surface 안의 `anchor`를 가져야 한다.
- `general` 장면은 검증 사실·V5 오버레이를 포함하면 안 된다.
- 프롬프트 사실 가드와 오버레이 계약을 dry run에서 통과하지 못하면 유료 호출을 시작하지 않는다.

## 실제 실행 명령

아래 명령은 유료 Gemini Pro 요청을 만든다. 비용 승인 뒤에만 실행한다.

```powershell
docker compose exec fastapi-workers python scripts/run_three_goals_images_e2e.py `
  --input /app/<검증된-4장면-입력>.json `
  --execute `
  --run-id gemini-pilot-YYYYMMDD-01
```

`report.json`과 `review_dossier.json`의 경로, 실행 단위, 장면 수, `cost_ledger.json`의 실제 요청 수를 먼저 확인한다. 입력의 사실값·API 키·원문은 공유 가능한 검수 문서에 복사하지 않는다.

## 장면별 판정 기준

각 장면을 원본과 최종 PNG를 나란히 놓고 다음을 확인한다.

| 항목 | graph / diagram / metric | general |
|---|---|---|
| 파일 무결성 | PNG, 1920×1080, 해시 기록 | PNG, 1920×1080, 해시 기록 |
| 모델 생성 문자·숫자 | 원본에 의미 있는 문자·수치·로고·출처를 만들지 않았는지 확인 | 의도하지 않은 문자·수치·로고가 없는지 확인 |
| 결정론적 오버레이 | 원본과 최종 해시가 달라야 함. label·value·source_ref·anchor가 입력 계약과 일치 | 원본과 최종 해시가 같아야 함 |
| 장면 품질 | mascot 비율·표정·카메라 구도, primary surface 이외 보조 화면, 과도한 빈 배경·프레임·분할선 확인 | mascot·소품·구도·문자 오염 확인 |
| OCR 상태 | `ADVISORY_REVIEW_REQUIRED`이면 검출 문자열을 사람 눈으로 확인, `UNAVAILABLE_OR_FAILED`이면 원본·최종을 수동 검수 | 동일 |

다음 중 하나라도 있으면 `APPROVE`하지 않는다: 모델이 만든 숫자/문자, 지정 surface 밖 오버레이, 출처 불일치, 해상도 불일치, 캐릭터 정체성 붕괴, 검수 불가능한 PNG 손상.

## 재생성 승인 파일

재생성은 해당 장면의 현재 후보를 보고 난 뒤에만 작성한다. 여러 장면은 `decisions` 배열에 각각 기록한다.

```json
{
  "decisions": [
    {
      "scene_id": "graph",
      "decision": "REGENERATE",
      "reviewed_attempt": 1,
      "reason": "원본 background.png의 primary surface 밖에 의미 있는 모델 생성 문자가 있어 재생성이 필요함"
    }
  ]
}
```

`reviewed_attempt`는 `review_dossier.json`의 `current_attempt`와 정확히 같아야 한다. 그 뒤에만 다음처럼 다시 실행한다.

```powershell
docker compose exec fastapi-workers python scripts/run_three_goals_images_e2e.py `
  --input /app/<검증된-4장면-입력>.json `
  --execute `
  --run-id gemini-pilot-YYYYMMDD-01 `
  --rerun-scene graph `
  --review-decisions /app/<재생성-승인>.json
```

새 후보는 `attempt-02`에만 기록되며, 기존 `attempt-01`과 비용 원장은 유지된다. 재생성 뒤에는 모든 장면의 회차 이력이 들어 있는 `review_dossier.json`을 다시 검토한다.

## 종료 조건

4장면 모두의 가장 최신 후보에 대해 PNG·원장·OCR 상태와 수동 시각 검토를 완료하고, 각 장면을 `APPROVE` 또는 `REGENERATE`로 명시해야 파일럿을 닫는다. 세 개의 검증 장면 중 하나라도 재생성 판정이면, 다음 단계의 장문 실제 E2E로 넘어가지 않는다.

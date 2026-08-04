# Gemini Pro 4장면 파일럿 결과 — 한국은행 통화정책

실행일: 2026-08-02  
실행 단위: `bok-policy-20260716-v2`  
상태: `ACTION_REQUIRED` — 사용자 시각 검토에 따른 diagram 재설계 완료, Gemini 재생성은 결제 크레딧 충전 대기

## 검증 주제

주제는 `2026년 7월 한국은행 기준금리 인상과 물가`다. 아래 값은 한국은행의 2026-07-16 통화정책방향 보도자료에서만 가져왔으며, Gemini 프롬프트에는 전달하지 않았다.

| 장면 | 결정론적 오버레이 사실 | 최종 후보 |
|---|---|---:|
| graph | 기준금리 2.75% | attempt-01 |
| diagram | 2.50% → 2.75% 상승선과 인상폭 0.25%p | attempt-04는 사용자 반려, 재생성 대기 |
| metric | 소비자물가 3.2% | attempt-02 |
| general | 검증 사실 오버레이 없음 | attempt-01 |

## 검수 결과

- 모든 최종 PNG는 1920×1080이다. Gemini 원본 2752×1536은 보존하고, 최종본에만 중앙 크롭과 Lanczos 리사이즈를 적용했다.
- graph·metric·general 후보는 첫 재검토 또는 첫 생성에서 승인했다.
- diagram은 읽을 수 있는 기호, 비원형 마스코트, 가짜 문자를 이유로 세 번 재생성했다. 이후 사용자 시각 검토에서 attempt-04의 지도·노드 배경과 분리된 인상폭 텍스트는 장면 의도에 맞지 않는다고 최종 반려했다.
- 재설계는 마스코트 기준 시트 `goldie_sheet_v1.png`를 모든 Gemini 요청에 실제 첨부하고, 중앙 벽면의 추상 상승 배경 위에 `2.50% → 2.75%`와 `0.25%p`를 Pillow로 합성한다. 수치와 방향은 검증 사실 원문에 없으면 렌더 자체가 실패한다.
- 재생성 요청 1회는 Gemini API의 `HTTP 429 RESOURCE_EXHAUSTED`(AI Studio 선불 크레딧 소진)로 이미지 생성 전에 거절됐다. 따라서 새 PNG 후보는 없고, 기존 dossier의 diagram 승인은 더 이상 유효한 최종 판정이 아니다.
- OCR은 `ADVISORY_REVIEW_REQUIRED`로 기록했다. OCR 결과는 승인 근거가 아니며, 최종 판정은 원본·최종 PNG의 수동 시각 검토로 내렸다.
- `review_dossier.json`에는 네 장면의 승인 사유와 선택 회차가 기록돼 있다.

## 비용 원장

- 성공 실행 단위 `bok-policy-20260716-v2`: Gemini Pro 요청 8회, 추정 ₩1,504, 상한 초과 ₩0.
- 재설계 후 attempt-05 요청은 `HTTP 429`로 거절됐다. 안전 원장은 요청 예약액 ₩188을 포함해 누적 추정 ₩1,692로 남기지만, 실제 과금 여부는 제공자 콘솔 대사 전까지 `unverified_until_console_reconciliation`이다.
- 최초 기술 검증 실행 `bok-policy-20260716-v1`은 원본 1920×1080 강제 규칙 때문에 첫 요청 뒤 중단됐다. 해당 1회는 ₩188로 별도 원장에 보존했다.
- 제공자 콘솔 대사는 아직 수행하지 않았으므로 원장 상태는 `unverified_until_console_reconciliation`이다.

## 산출물

- 입력 계약: `backend/fastapi-workers/pilot-inputs/bok_monetary_policy_2026_07.json`
- 최종 dossier: `artifacts/gemini_pilot/bok-policy-20260716-v2/review_dossier.json`
- 비용 원장: `artifacts/gemini_pilot/bok-policy-20260716-v2/cost_ledger.json`
- 후보 PNG: `artifacts/gemini_pilot/bok-policy-20260716-v2/candidates/`

## 다음 단계

1. AI Studio 프로젝트에 선불 크레딧을 충전한다.
2. 같은 재생성 승인 파일로 diagram만 다시 실행한다. 새 후보는 고정 캐릭터 참조와 중앙 벽면 상승선의 수동 시각 검수를 통과해야 한다.
3. 그 뒤에야 longform 조립·Kling 초반 구간·QC·YouTube 패키지·통합 비용 원장을 하나의 job ID로 검증한다.

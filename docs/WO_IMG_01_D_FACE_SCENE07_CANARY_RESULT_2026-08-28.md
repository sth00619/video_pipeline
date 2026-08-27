# WO-IMG-01-D — scene07 얼굴 v2 canary 결과

## 1. 결론

승인된 scene07 유료 canary를 기존 실패 계보에서 **외부 POST 1회만** 실행했다. 결과는 5.328초 만의 HTTP 503 `UNAVAILABLE`이며 이미지와 `usageMetadata`는 반환되지 않았다.

승인 조건에 따라 scene02·35는 호출하지 않았다. 이번 결과는 다음처럼 분리한다.

- 공급자 가용성: **실패 — HTTP 503**
- 얼굴 v2 계약: **평가 불가 — 이미지 없음**
- 결정론 텍스트/OCR 게이트: **평가 불가 — 이미지 없음**
- scene02·35 진행: **차단**

v2 얼굴 계약이 scene07에서 실패했다고 판정하지 않는다. 반대로 개선됐다고도 판정하지 않는다.

## 2. 실제 canary 요청 계보

| 항목 | 직전 scene07 실패 | 이번 canary |
|---|---|---|
| attempt ID | `246a77ba4da44508a39ec8c25b4e1b50` | `e7eb8f76e28241cfae233e29905ef6eb` |
| scene attempt | 1 | 2 |
| failure_n | 1 | 2 |
| 응답 | 503 `UNAVAILABLE` | 503 `UNAVAILABLE` |
| 소요 | 7.144초 | 5.328초 |
| payload SHA-256 | `b58ed621...df00a454` | `b58ed621...df00a454` |
| prompt SHA-256 | `dca49ed4...f1abd96` | `dca49ed4...f1abd96` |
| contract fingerprint | `e79c33bb...5e71495` | `e79c33bb...5e71495` |
| 첫 참조 SHA-256 | `7e7981e3...8e40e` | `7e7981e3...8e40e` |

payload·프롬프트·계약 fingerprint·참조 세트가 모두 동일하다. 기존 `face-v2:7` key와 같은 요청 상태 DB를 사용했으며 새 별칭이나 새 카운터로 상한을 우회하지 않았다.

## 3. 예산 판정

- 이번 신규 승인: ₩1,600
- 실행 전 기존 예약 노출: ₩4,800
- 실행 후 누적 예약 노출: ₩6,400
- 원장 성공 비용 합계: ₩0
- budget overrun: ₩0
- 실제 청구: 미확정

이번 503은 `excluded_from_success_estimate_billing_unverified`다. 성공 비용 합계에서 제외했지만 무과금 확정으로 해석하지 않는다. 예약 노출 ₩6,400도 확정 지출이 아니다.

## 4. 실행 전 차단 사고와 수정

최초 실행기 기동은 외부 POST 전에 차단됐다. `prepare_rows`가 애플리케이션 설정을 먼저 로드한 뒤 환경변수로 상태 DB를 지정했기 때문에, 승인된 기존 상태 DB 대신 기본 저장소를 보려 한 초기화 순서 문제였다.

이 첫 기동에서 다음은 변하지 않았다.

- 원장 항목: 3개 유지
- 예약 노출: ₩4,800 유지
- 신규 attempt ID: 없음
- 외부 POST: 0회

무네트워크 payload 재구성에서는 직전 요청과 payload 해시·prompt 해시·참조 해시가 모두 같았다. 따라서 payload 불일치가 원인이 아니었다.

수정 커밋 `32b144a`에서 승인 상태 DB 경로·project scope·장면 상한을 `prepare_rows`보다 먼저 런타임 설정에 직접 반영했다. 초기 claim과 manifest는 삭제하지 않고 `predispatch_blocked_20260828T023758KST` 파일로 보존했다. 수정 후 실제 POST 1회만 실행됐다.

## 5. 중단 조건 이행

canary가 503이면 scene02·35를 호출하지 않는 조건을 지켰다.

- `face-v2:2` 원장 항목: 기존 1개 그대로
- `face-v2:35` 원장 항목: 기존 1개 그대로
- `face-v2:7` 원장 항목: 기존 1개 + 승인 canary 1개
- 전체 원장 항목: 3개 → 4개
- scene42 attempt ID: `8729ad2c69e949f8b30887ff9bc202f8` 그대로
- scene42 원장 SHA-256: `79a7e345f796824e1db409cd24bd3089d26bb502ef912bd221252a4d2a8cbc4f` 그대로

Anthropic·TTS·Fal/Kling·FFmpeg 조립·썸네일은 실행하지 않았다.

## 6. 다음 상태

scene07은 `failure_n=2`, `needs_review`로 유지한다. 이미지가 없으므로 얼굴 크롭·홍채 비율·흰자·하이라이트·눈썹 검증은 수행할 수 없다. 공급자 503이 다시 canary에서 재현됐으므로 scene02·35로 확대하지 않고, 승인된 오프라인 후속인 빈 물리 표면·의사문자·`전망치` OCR 작업으로 돌아가는 것이 현재 안전한 순서다.

추가 유료 호출은 별도 승인 없이는 진행하지 않는다.

## 7. 증거

비민감 요약은 `docs/evidence/wo_img01_d_face_reference_20260828/face-scene07-canary-result.json`에 있다. 원본 manifest·원장·claim은 `artifacts/wo_img01_d_face_reference_pilot_20260828/`에 로컬 보존한다.


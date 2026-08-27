# WO-IMG-01-D — 얼굴 참조 v2 3장 실 API 파일럿 결과

## 1. 결론

승인된 범위대로 scene 02·07·35를 새 scene key로 각각 **1회만** Gemini 실 API에 요청했다. 세 요청 모두 이미지가 반환되기 전 HTTP 503 `UNAVAILABLE`로 끝났다. 자동 재시도는 0회이며 각 scene key는 `needs_review`로 격리했다.

따라서 이번 결과는 **얼굴 품질 실패가 아니라 공급자 실패로 인한 평가 불가**다. 이미지가 한 장도 없으므로 v2 얼굴 계약의 육안·정량 DoD, 텍스트·물리 표면·OCR 게이트는 평가할 입력 자체가 없다. 추가 호출은 새 승인 없이 진행하지 않는다.

- 성공 이미지: **0/3**
- 외부 POST: **3회** (장면별 1회)
- 자동 재시도: **0회**
- 응답: **503 `UNAVAILABLE` 3건**
- 성공 응답 `usageMetadata`: 없음
- 승인 예약 상한: **₩4,800**
- 원장 성공 비용 합계: **₩0**
- 예약 노출액: **₩4,800**
- 실제 청구: **미확정**
- scene42: 동결 상태 불변
- Anthropic·TTS·Fal/Kling·조립·썸네일: **0회**

`₩4,800`은 보수적 예약 상한이지 예상 비용이나 확정 지출이 아니다. 세 503 요청은 `excluded_from_success_estimate_billing_unverified`로 기록했으며, 이를 “무과금 확정”으로 확대 해석하지 않는다.

## 2. 실행 전 안전 확인과 Git 상태

실행 전 `git fetch` 후 로컬 main과 origin/main의 기반을 다시 확인했다. `apple`·`assemble`은 각 원격과 같은 상태였고 수정하지 않았다. 별도 실행 중 이미지 파일럿 프로세스가 없으며 scene42 원장도 동결 상태임을 확인했다.

오프라인 WO-IMG-01-D 세 커밋을 먼저 push했다.

- `d374b0f`: 선행 실패 계약
- `d4ee9e1`: 얼굴 참조 v2와 공통 프롬프트 계약
- `aa1d1a5`: 독립 증거와 결과 문서

그다음 유료 실행 범위·상한을 코드로 고정한 `caaeb2d`를 push하고, 그 버전으로만 파일럿을 실행했다. 실행기는 `{2,7,35}` 이외 장면, scene42, v1 얼굴 참조, 장면별 2회 이상 호출, 총 예약액 ₩4,800 초과를 실행 전에 거절한다.

## 3. 요청별 결과

| 장면 | 새 scene key | attempt ID | 응답 | 소요 | payload SHA-256 | 상태 |
|---:|---|---|---|---:|---|---|
| 02 | `face-v2:2` | `56f0fabebbe24f4ebaa1681212bb5680` | 503 `UNAVAILABLE` | 10.252초 | `6cb2cc37c89e630f5cdc33d68941c58efffcd305d3c382c859941febdb997c8e` | `needs_review` |
| 07 | `face-v2:7` | `246a77ba4da44508a39ec8c25b4e1b50` | 503 `UNAVAILABLE` | 7.144초 | `b58ed621dd9d1bffb159109f3a5f8c03e05a4b1a86a2d4a139045f23df00a454` | `needs_review` |
| 35 | `face-v2:35` | `f84afef34a064bfeba502f6a9e0f596a` | 503 `UNAVAILABLE` | 4.657초 | `697fb0c2322aad0d6312a09d4aba69dad72070dd42bb64e76c5461ab82051b1a` | `needs_review` |

세 원장 항목 모두 `attempt=1`, `failure_n=1`, `usage_metadata_status=absent`, `image_sha256=null`이다. QA 이벤트도 0건이다. 이는 이미지가 생성된 뒤 얼굴·텍스트 QA에서 거절된 것이 아니라, 공급자 응답 단계에서 중단됐다는 뜻이다.

## 4. v2 참조가 실제로 전송됐는지

세 요청의 실제 `request_evidence.references[0]`은 모두 다음 해시다.

`7e7981e389d07c4c3eca908708365cdcc809226c0f9a039f7ff7f62bbad8e40e`

이는 `channel_character_face_range_v2.png`의 고정 SHA-256과 일치한다. 기존 v1 해시 `3d113c43e9395435d1b07b6e5a015c17e606b246e7a4f177bd3de4d074489c45`는 세 실제 요청의 참조 목록에 없다.

따라서 이번 실행은 “v2를 설정만 했고 실제 요청에서는 빠졌다”는 상태가 아니다. **v2는 실제 전송됐지만 공급자가 이미지를 반환하지 않았다.** 이 둘을 구분한다.

## 5. scene42와 범위 제한

scene42 기존 원장 SHA-256은 실행 전후 `79a7e345f796824e1db409cd24bd3089d26bb502ef912bd221252a4d2a8cbc4f`로 같다. 다음 값도 변하지 않았다.

- attempt ID: `8729ad2c69e949f8b30887ff9bc202f8`
- 응답: `http_503`
- `failure_n=1`
- control status: `needs_review`

이번 파일럿은 이미지 생성만 다뤘다. 승인 대본, TTS, 자막, Fal/Kling, MP4 조립, 썸네일 단계는 시작하지 않았다. 텍스트·수치·물리 표면·OCR 게이트를 완화하거나 우회하지도 않았다.

## 6. DoD 판정

| 완료 기준 | 결과 | 근거 |
|---|---|---|
| v2가 실제 요청에 포함 | 통과 | 세 요청 모두 첫 참조 해시가 v2와 일치 |
| 장면별 1회, 재시도 없음 | 통과 | 원장 항목 3개, 각 `attempt=1` |
| 총 예약 상한 ₩4,800 | 통과 | `reserved_exposure_krw=4800`, overrun 0 |
| scene42 동결 | 통과 | 원장 해시와 상태 불변 |
| 얼굴이 승인 범위 안에 듦 | 평가 불가 | 이미지 0장 |
| 육안으로 같은 캐릭터 | 평가 불가 | 얼굴 크롭·콘택트시트 생성 불가 |
| 텍스트/물리 표면/OCR 통과 | 평가 불가 | 공급자 단계에서 종료 |
| 첫 성공 `usageMetadata` 보고 | 해당 없음 | 성공 응답 0건 |

WO-IMG-01-D의 오프라인 원인 수정과 호출 통제는 검증됐지만, **얼굴 품질 최종 DoD는 여전히 미완료**다.

## 7. 보존 증거

Git에 보존한 비민감 요약은 `docs/evidence/wo_img01_d_face_reference_20260828/face-pilot-result.json`이다. 로컬 원본 산출물 해시는 다음과 같다.

| 원본 | SHA-256 |
|---|---|
| `pilot_manifest.json` | `1fa1bcd0faebbd68c11e902c130a68b24122ab881764dfdc98d9f68287485e0d` |
| `request_ledger.json` | `a97436bc6e129fa182f411c94201b4429dfe19daf377fd79598b704bf63ff625` |
| `preflight.json` | `7c8455dd754bbe66c45771a3c9e03daa5aace5502ac8a2e5b4ed85a203a84df4` |

원본 원장과 manifest는 `artifacts/wo_img01_d_face_reference_pilot_20260828/`에 로컬 보존한다. API 키나 원문 payload는 문서에 기록하지 않았다.

## 8. 다음 판단

이번 세 key는 승인 조건대로 `needs_review`에 둔다. 같은 key를 자동 재시도하거나 새 별칭으로 상한을 우회하지 않는다. 공급자 가용 시간대를 바꾼 재실행을 원하면 별도 예산과 실행 승인을 받은 뒤, 기존 세 실패를 포함하는 동일 원장·동일 통제 계층에서 진행해야 한다.

성공 이미지가 생길 때만 다음 순서로 이어간다.

1. 얼굴 크롭과 v2 6장 참조의 나란히 비교
2. 홍채/눈 폭 38~58%, 흰자, 갈색 홍채, 이마 하이라이트, 완만한 눈썹 실측
3. 기존 텍스트·물리 표면·OCR 게이트 적용
4. 모두 통과한 뒤에만 Fal 적합성 검토


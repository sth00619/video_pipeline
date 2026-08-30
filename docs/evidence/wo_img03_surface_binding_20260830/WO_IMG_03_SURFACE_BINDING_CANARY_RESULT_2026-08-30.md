# WO-IMG-03 의미 표면 결박 canary 결과

## 1. 결론

공통 표면 결박 수정 커밋 `731ac00`을 Pro Priority 실 이미지로 검증하려 했으나, 동일한 scene00 요청이 두 번 연속 `HTTP 503 UNAVAILABLE`로 종료됐다. 새 이미지와 `usageMetadata`는 생성되지 않았다. scene07·15·28은 두 실행 모두 프로젝트 냉각 정책이 외부 POST 전에 보류했으므로 공급자 실패 건수에 포함하지 않는다.

따라서 이번 결과로 표면 결박의 실물 품질이 개선됐다고 주장하지 않는다. 오프라인에서 확인된 것은 scene00의 잘못된 칠판 표면 차단, scene07의 모니터 하부 상대 영역 검출, scene15의 표면별 중복 OCR 검출까지다.

## 2. 실행 계보

- 운영 계약 커밋: `731ac00`
- 실행기 범위 수정 커밋: `b795d3c`
- 실행 명세 커밋: `cb66d79`
- 모델/등급: `gemini-3-pro-image`, `priority`
- 대상: scene00·07·15·28, 장면별 1회, 자동 재시도 없음
- scene42: 제외 및 동결 유지
- TTS·Fal·영상 조립: 실행하지 않음

실행 전 오래된 canary 도구가 선택하지 않은 Job52 장면까지 최신 V5 계약으로 재검증하고, 공용 `prepare_rows()`가 호출자의 장면 목록을 무시하는 두 실행기 결함을 발견했다. 두 결함은 외부 POST 전에 발생했으며 각각 `5a68a36`, `b795d3c`에서 수정했다. 수정 후 사전 검증은 장면 4개와 예상 직접비 약 ₩1,354.752를 정확히 산출했다.

## 3. 공급자 시도 원장

| 실행 | attempt ID | HTTP | duration | payload SHA-256 | prompt SHA-256 |
|---|---|---:|---:|---|---|
| run2 | `e8aa5fc7cd15410f9e64967fdc9c669a` | 503 | 5.049초 | `140100ab12034044d42a4d6aa773987d22935cca87b2b98beb557ced2816d186` | `a5acb444f09133645f1d2bb8e8a7b0108f7ca77e77690fc5e950332869126a59` |
| run3 | `514cd53d6aea4e639b7dc4fbd708a357` | 503 | 5.500초 | `140100ab12034044d42a4d6aa773987d22935cca87b2b98beb557ced2816d186` | `a5acb444f09133645f1d2bb8e8a7b0108f7ca77e77690fc5e950332869126a59` |

두 실행의 payload와 prompt 해시는 동일하다. run2 manifest SHA-256은 `c5d3f515f1f7828f145c6c955b913e319ddc353ecdfa74707b2b865c0bb33849`, 원장은 `c513e9206e4c0301128083dd24702852b8300cd1ed7b6138990d371e3cde778f`다. run3 manifest는 `c327f1118b7c565d8fce80960f7410df9aa1f17f23c91abec02975d65b4c15ce`, 원장은 `6dd0f14ce4df9cb38cf7f186de6067045bc9f7900808502d4f64dbe0db9e3520`다.

각 실행에서 scene00만 실제 POST 1회가 발생했다. scene07·15·28의 `attempt_count`는 0이다. 두 503의 `amount_krw`는 0으로 기록됐지만 청구 확정 근거로 확대 해석하지 않으며 `excluded_from_success_estimate_billing_unverified` 상태를 유지한다.

## 4. 상태 확인과 중단 판단

두 번째 시도 전 Google Cloud Service Health를 확인했으며 2026-08-30 07:34 PDT 기준 `No broad severe incidents`였다. 공식 광범위 장애가 없다는 것은 개별 Gemini 이미지 용량 부족이 없다는 뜻이 아니다. 실제 요청이 같은 payload로 다시 503을 반환했으므로 세 번째 즉시 시도는 하지 않았다.

다음 유료 검증은 즉시 반복하지 않고 다른 부하 구간에서 동일 명세로 재개한다. 성공 응답을 얻기 전에는 이미지 실물·눈 구조·화풍·의미 전달·예상 밖 소품·표면 게이트를 판정하지 않는다.

## 5. 회귀 근거

공통 구현 커밋 `731ac00`의 전체 오프라인 회귀는 격리 Docker 환경에서 `1193 passed, 0 failed`였다. 실 이미지 공급자 실패는 이 코드 회귀 결과를 반증하지 않지만, 실물 품질을 증명하지도 않는다.


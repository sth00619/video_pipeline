# WO-IMG-01-H scene07 눈 구조 canary 결과

작성일: 2026-08-29  
대상: `gemini-3-pro-image`, scene07 한 장  
결론: 공급자 503으로 이미지 미생성, 품질 판정 불가

## 1. 실행 범위

사용자의 Gemini 이미지 재도전 상시 허가와 이번 scene07 단일 재시도 권고에 따라 외부 POST를 정확히 한 번 실행했다. 기존 surfacefix 실행기의 한 장·한 번·사용자 육안 전 중단 장치를 재사용하되 다음 계보를 새로 만들었다.

- scene key: `wo-img01-h-eye-layers:7`
- 증분 예약 상한: ₩1,600
- 과거 관련 canary 보수적 예약 노출: ₩28,800
- 누적 보수적 예약 노출 상한: ₩30,400
- scene42: 동결·제외
- 의미 표면 계획: 기존 단일 `main` 계획을 그대로 보존
- Fal/Kling·TTS·영상 조립: 미실행

## 2. 사전 확인

Google Cloud 공식 상태판은 확인 시점에 `No broad severe incidents`를 표시했다. 이는 광범위 Cloud 장애가 게시되지 않았다는 뜻일 뿐, `gemini-3-pro-image` 개별 용량을 보증하지 않는다.

- 확인 시각: `2026-08-29T00:59:20+09:00`
- 상태판 표시 최종 갱신: `28 Aug 2026, 08:38 PDT`
- 출처: <https://status.cloud.google.com/>

오프라인 실행기 테스트는 5 passed였다. 기존 surfacefix 역사적 사양의 상수를 오염시키지 않도록 새 실행기는 컨텍스트 안에서만 scene key와 누적 상한을 바꾸고 종료 시 원상 복구한다.

## 3. 실제 송신 계보

- bounded prompt SHA-256: `4eb7d08d86be67841ff6041f39f731657f7154e23ba16e2c154aceb0d80baf5c`
- 최종 Gemini prompt SHA-256: `5c117fad51214e6cd4b66953b3d8717066dd0f454bd39e2959a41edcb9555595`
- payload SHA-256: `00088ee50d8cb3a134c96f6f7c1303a03c5490e5613359672a7784d7f677beca`
- scene contract SHA-256: `8bfc06d61ac529437a31f3990fc5bb1d25c2f43095ad5c7599b4dff7f5ba157a`
- attempt ID: `3c0811b897854419bdb726ce36631ff6`

실제 전송 참조:

1. 얼굴 v2 — `7e7981e389d07c4c3eca908708365cdcc809226c0f9a039f7ff7f62bbad8e40e`
2. scene05 고글 얼굴 — `7b6c97c2713bb70d34f0a3d71022bda16bd9a032a6d0417457bce6083bfae6e2`
3. Job52 data-lab 화풍 — `87c52f3ef3c0bdd0bfddeb3ed08f15f7038c38c48fc5ebf291db625d8aed05e6`

최종 프롬프트에는 `job52-range-v2-operational-v3-eye-layers` 계약과 다음 구조가 포함됐다.

- 흰 공막 영역
- 그 안의 따뜻한 갈색 홍채
- 홍채 안의 더 어두운 동공
- 홍채 또는 동공 안의 흰 캐치라이트
- 검은 타원 속 흰 점만으로는 공막으로 인정하지 않음

## 4. 공급자 결과

- HTTP: `503 UNAVAILABLE`
- 응답까지 걸린 시간: 약 8.21초
- 원장 상태: `needs_review`
- 생성 이미지: 없음
- usageMetadata: 없음
- 성공 비용 추정 반영액: ₩0
- 보수적 예약액: ₩1,600
- 청구 여부: 미확정

따라서 이번 결과로 눈 구조 계약의 실제 개선 여부를 판정할 수 없다. 실패 원인은 얼굴 품질이나 프롬프트 품질이 아니라 공급자 가용성 계층이다. 새 이미지가 없으므로 OCR·물리 표면·사용자 육안·Fal 후보 판정도 시작하지 않았다.

## 5. 중단 판단

승인 범위가 한 장·한 번이므로 추가 POST를 실행하지 않았다. 원장의 재개 가능 시각이 기록됐더라도 동일 턴에서 자동 재시도하지 않는다. 다음 실행은 별도의 새 계보 또는 명시적으로 검증된 재개 절차를 사용해야 하며, 이번 attempt를 성공한 품질 표본처럼 재사용하면 안 된다.

## 6. 증거

`docs/evidence/wo_img01_h_eye_layers_canary_20260829/`에 다음을 보존한다.

- 승인 명세
- 사전 검증 JUnit
- preflight
- bounded/final prompt
- 요청 원장
- 최종 manifest

원본 실행 디렉터리는 `.gitignore` 대상인 `artifacts/wo_img01_h_eye_layers_canary_20260829/`에 보존한다.

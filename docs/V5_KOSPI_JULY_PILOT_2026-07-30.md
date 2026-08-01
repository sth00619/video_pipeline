# V5 KOSPI 7월 전망 파일럿 기록

## 목적

이 파일럿은 일반 카툰 배경과 검증된 숫자·문자 오버레이를 분리한 V5 운영 경로를 실제 입력으로 확인한다. 이미지 모델은 레퍼런스처럼 장식용 영문·차트·수치가 풍부한 카툰 배경을 생성하고, 화면의 한글 라벨과 검증 수치는 원문 URL이 연결된 사실에서만 Pillow로 합성한다. 검증 수치는 장면 위에 새 카드로 추가하지 않고 배경에 그려진 물리 모니터·전광판·계기판의 내부 화면을 교체한다.

## 생성·검증 흐름

1. NAVER API HUB로 최근 `코스피 7월 전망` 기사 후보를 수집했다.
2. 각 후보의 원문 URL을 요청하고 HTML 본문을 확보한 경우만 증거로 남겼다.
3. Claude `claude-sonnet-4-6`이 3회 교차검증한 뒤, 모델이 고른 `figure` 문자열을 원문 본문에서 다시 찾았다.
4. 원문에 없는 값·잘못된 `source_field`·숫자가 없는 항목은 차단했다.
5. 검증 사실 6건과 3개 내레이션 씬을 만들고, 각 씬에는 하나의 출처 URL이 있는 오버레이만 넣었다.
6. Gemini Pro는 장식용 정보 밀도가 있는 카툰 배경을 생성한다. 생성 이후에는 새 이미지 API를 호출하지 않고, 지정된 물리 정보면 내부를 Pillow 오버레이로 렌더링한다.

## 산출물

- 증거 원문·검색 결과: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/evidence.json`
- 교차검증 통과/거절 사실: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/verified_facts.json`
- Claude 대본: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/script.json`
- 검증 오버레이 입력: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/generated_backgrounds/kospi_july_2026_verified_backgrounds/v5_generated_background_pilot_input.json`
- 최종 3씬 검토 시트: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/final_rendered_v2/contact_sheet.png`
- 영상 조립 계약: `backend/fastapi-workers/out/v5_pilot/kospi_july_2026/final_rendered_v2/v5_pilot_assembly_manifest.json`

## 시각 정책 결과

- 오른쪽·가운데·왼쪽 배치가 각각 한 장씩 사용된다.
- 중앙 배치였던 초기 2번은 좌우 분할 무대라서 불합격 처리했다.
- `split_stage` 아키타입은 새 V5 실행 경로에서 제거하고, 한 장의 연속된 `risk_control_room`으로 교체했다.
- AI가 그린 그래프·게이지·선은 장식이며, 사실값으로 사용하지 않는다.

## 비용 및 회계

- 새 Gemini Pro 표준 요청: 4건. 처음 3건 + 분할 불합격 2번의 교체 1건.
- 승인된 추정 단가: 장당 `$0.14`.
- 추정 합계: `$0.56`(실행 시 환율 스냅샷 약 `₩1,016`).
- 모든 요청은 `max_attempts=1`이며 자동 재시도가 없다.
- 실제 청구 단가는 Gemini 응답에 없으므로 모든 항목은 `unverified_until_console_reconciliation` 상태다. 다음 유료 묶음 전에 콘솔 대조가 필요하다.

## 조립 시작 조건

조립 매니페스트는 이미지, 내레이션, 오버레이, 출처를 씬별로 연결하지만 TTS 길이를 임의로 추정하지 않는다. 실제 영상 조립은 다음 두 조건이 충족될 때만 시작한다.

1. 각 씬의 검증된 TTS WAV와 실측 길이 입력
2. 최종 3씬에 대한 사람 시각 검토와 Gemini 콘솔 비용 대조

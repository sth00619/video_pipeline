# V5 `weather_map` Primary Surface 사전 검토

작성일: 2026-07-31  
상태: **프롬프트 검토 완료 대기. 이미지 API 호출 없음.**

## 목적

기존 4개 archetype의 첫 검증 대상으로 `weather_map`을 준비한다. 이 문서는 실제 `ARCHETYPES` 정의를 기준으로 소품을 전수 조사하고, primary 표면과 대체물 금지를 구체화한 기록이다.

## 실제 무대 정의 대조

출처 코드: `backend/fastapi-workers/app/v5/scene/prompt_builder.py`의 `ARCHETYPES["weather_map"]`

| 정의 항목 | 현재 코드의 내용 | 검증 계약에서의 처리 |
|---|---|---|
| stage | TV 날씨 스튜디오, 대형 곡면 조명 지도 벽, 삼각대 방송 카메라 | 지도 벽은 primary 후보, 카메라와 삼각대는 비문자 |
| key props | 거대 지도 벽, 지도 위 폭풍 구름, 포인터, 스튜디오 카메라, 천장 스폿라이트 | 지도 벽 중앙부만 문자 허용. 구름·포인터·카메라·스폿라이트는 비문자 |
| lighting | 차가운 파란 스튜디오 조명, 지도 벽 발광, 스포트라이트 빔 | 텍스트도 지도 벽의 발광·곡면·원근을 상속해야 함 |
| visual detail | 폭풍 구름 아이콘, 방향 화살표, 글자 없는 색상 날씨 밴드 | primary 중앙 영역 안의 지도 윤곽/구름/화살표는 보조 그래픽으로만 사용. 지정 영역 밖의 같은 요소도 비문자 |

## 확정할 primary와 비-primary 목록

| 구분 | 문장 |
|---|---|
| primary physical surface | **the broad central geographic region of the single large curved illuminated map wall** |
| primary에서만 허용 | 짧고 읽을 수 있는 장식 영문·표본 수치 2~3개, 간단한 그래프·다이어그램 선. 모두 지도 윤곽·구름·화살표와 같은 물리 지도 벽 안에 결합되어야 함. |
| 비-primary 소품 | 스튜디오 카메라, 삼각대, 포인터, 천장 스폿라이트, 스튜디오 바닥 장치, primary 영역 밖의 지도 벽, 그 밖의 구름 아이콘·방향 화살표·날씨 밴드 |

## 대체물 금지 목록

primary가 아닌 그럴듯한 정보 표면으로의 이동을 막기 위해 다음을 명시적으로 금지한다.

- freestanding forecast board
- separate weather card
- side monitor
- desk display
- camera-mounted label
- lower-third banner
- independent alert panel

이 목록은 날씨 스튜디오에서 흔히 생길 수 있는 "따로 붙은 예보 카드"와 "방송 자막 바"를 겨냥한다. primary 지도 벽 안의 라벨과 혼동하지 않는다.

## 사전 프롬프트 판정 기준

생성된 프롬프트 문자열에서 아래 조건이 모두 확인되어야 한다.

- [ ] primary 문장이 곡면 지도 벽의 중앙 지리 영역까지 정확히 지정됨
- [ ] primary 안의 장식 문자/표본 수치는 `MUST`로 요구됨
- [ ] 구름·화살표·날씨 밴드와 카메라·포인터가 primary 외에서는 비문자라고 명시됨
- [ ] 별도 예보 보드·카드·보조 모니터·하단 자막 바가 명시적으로 금지됨
- [ ] 로고·한글·워터마크·분리 UI 카드 금지와 사실값의 결정론적 합성 원칙이 함께 존재함

## 다음 승인 전 결과물

프롬프트 문자열은 다음 파일에 비용 없이 생성해 검토한다.

`backend/fastapi-workers/out/v5_pilot/kospi_july_2026/weather_map_primary_prompt_review.md`

위 검토와 사람 승인 전에는 이미지 API를 호출하지 않는다.

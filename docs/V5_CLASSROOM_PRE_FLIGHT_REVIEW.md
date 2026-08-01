# V5 `classroom` Primary Surface 사전 검토

작성일: 2026-07-31  
상태: **프롬프트 검토 완료 대기. 이미지 API 호출 없음.**

## 실제 무대 정의 대조

출처 코드: `backend/fastapi-workers/app/v5/scene/prompt_builder.py`의 `ARCHETYPES["classroom"]`

| 정의 항목 | 현재 코드의 내용 | 검증 계약에서의 처리 |
|---|---|---|
| stage | 아늑한 대학 강의실, 큰 녹색 teaching wall, 목재 책상 | teaching wall의 중앙만 primary, 책상은 비문자 |
| key props | 세계지도 실루엣·화살표가 있는 teaching wall, 목재 포인터, 녹색 banker lamp, 열린 책 | 중앙 판서 영역만 문자 허용. 지도·화살표·포인터·램프·책은 비문자 |
| lighting | 따뜻한 교실 조명, 책상 램프의 부드러운 빛, 미세 반짝임 | 분필 문자도 벽의 분필 재질·램프 조명·원근을 상속 |
| visual detail | 분필형 지도 윤곽·화살표·원·연결 기하 표식 | primary 안에서는 문자 주변의 비문자 다이어그램으로 사용. primary 밖의 같은 표식은 비문자 |

## primary 및 비-primary 계약

| 구분 | 확정 문장 |
|---|---|
| primary physical surface | **the broad central chalk-writing area of the large green teaching wall** |
| primary에서만 허용 | 짧고 읽을 수 있는 장식 영문·표본 수치 2~3개, 분필형 간단 다이어그램/추이선. 모두 녹색 벽의 분필 질감·지우개 흔적·조명을 상속해야 함. |
| 비-primary 소품 | 모든 목재 책상, 열린 책, 목재 포인터, 녹색 banker lamp, 핀 메모, 교실 문, 시계, 중앙 영역 밖 teaching wall, 지도 실루엣·화살표·원·연결 기하 표식 |

## 대체물 금지 목록

- pinned paper note
- framed wall poster
- hanging chart
- separate blackboard
- desk display
- open-book page
- independent teaching card

이번 목록은 과거 `trade_calculator`의 독립 명패 누출과 `risk_control_room`의 상자 누출을 교실 맥락에 맞춰 선제 차단한다. 특히 종이 메모·포스터·책 페이지는 판서보다 더 그럴듯한 글자 표면으로 선택될 위험이 크다.

## 사전 프롬프트 통과 조건

- [ ] 큰 녹색 teaching wall의 중앙 분필 영역이 primary로 정확히 지정됨
- [ ] primary의 장식 문자/표본 수치가 `MUST`로 요구됨
- [ ] 책상·책·포인터·램프·핀 메모·문·시계·벽 외곽이 비문자로 명시됨
- [ ] 종이 메모·포스터·별도 칠판·책 페이지·독립 카드가 대체물로 금지됨
- [ ] 로고·한글·워터마크·분리 UI 카드 금지 및 사실값 결정론적 합성 원칙이 유지됨

## 검토 산출물

`backend/fastapi-workers/out/v5_pilot/kospi_july_2026/classroom_primary_prompt_review.md`

이 파일의 사람 검토·승인 전에는 `classroom` 이미지 API를 호출하지 않는다.

# V5 primary physical surface 재수정 기록

작성일: 2026-07-31

## 목적

Stage 4의 3개 실제 생성은 로고·한글 오염을 제거했지만, 한 장면 안의 여러 계기판·명패·화면에 장식 텍스트를 흩뿌렸다. 이는 한 개 표면을 요구한 `fact_surface_contract`와 여러 라벨을 요구한 배경 정보 밀도 지시가 충돌한 결과다.

이번 수정은 정보형 씬마다 **하나의 primary physical surface**만 자동으로 선택하고, 해당 표면 이외에는 읽을 수 있는 문자·숫자를 금지한다. 이 문서는 실제 수치의 AI 입력이나 오버레이 합성을 구현하지 않는다.

## 결정 방식

`recommend_v5_archetype()`은 기존 `ARCHETYPE_SURFACES`의 첫 항목을 `primary_physical_surface`로 고정한다. 같은 입력은 사람 선택 없이 같은 primary 표면을 얻는다.

| archetype | 자동 primary physical surface |
| --- | --- |
| port_emergency | one largest front container side |
| retail_shock | one built-in checkout receipt window |
| classroom | one central green teaching wall |
| weather_map | one central curved map wall |
| risk_control_room | one large central analog gauge face |
| trade_calculator | front face of the balance-scale base |
| data_lab | one central holographic map panel |

`risk_control_room`은 원래 계기판·명패·콘솔이 특히 많은 무대다. 따라서 이 archetype에서는 primary 외의 계기판·명패·콘솔을 비문자 소품으로 유지하는 계약을 명시적으로 강화한다.

## 프롬프트 계약

정보형 씬의 프롬프트는 다음을 동시에 요구한다.

1. primary 표면 하나는 짧고 읽을 수 있는 장식 영문·숫자 2~3개와 그래프 실루엣을 반드시 가진다.
2. 나머지 게이지·화면·지도·명패·문서·콘솔은 바늘, 색 블록, 추상 도형, 비문자 재질만 보인다.
3. 떠 있는 UI 카드·분리된 LCD·화면 위에 붙은 패널은 금지한다.
4. AI가 만드는 표기는 장식일 뿐이며, 실제 검증 값은 이후 Pillow/FFmpeg 결정론적 합성 단계가 책임진다.

## 이번 검증 범위

승인된 3씬(`kospi_july_01`, `kospi_july_02`, `kospi_july_03`)만 새 run ID로 Gemini Pro에 한 번씩 보낸다. 자동 재시도는 사용하지 않는다. 통과 기준은 primary 표면 한 곳으로의 정보 집중, 로고·한글 오염 회귀 없음, 분리 UI 카드 없음이다.

## 2026-07-31 확장 전 점검 교훈

`trade_calculator`에서는 독립 명패가, `risk_control_room`에서는 위기 상자가 primary를 대신해 문자를 받았다. 모델은 금지 목록에서 빠진 소품 중 무대 주제와 의미상 어울리는 물체를 대체 정보 표면으로 선택할 수 있다.

따라서 다음 archetype 확장 전에 다음 순서를 지킨다.

1. 해당 무대의 모든 주요 소품을 전수 목록화한다.
2. primary 하나를 물체 위치와 재질까지 구체화한다.
3. primary를 대신할 법한 독립 명패·화면·카드·간판을 명시적으로 금지한다.
4. 나머지 모든 소품을 개별 명칭으로 포함해 비문자 재질·도형·색상만 허용한다.

이 절차는 향후 `port_emergency`, `retail_shock`, `classroom`, `weather_map` 확장 때 먼저 검토하며, 현재 통과한 `data_lab`과 `trade_calculator` 규칙은 변경하지 않는다.

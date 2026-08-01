# V5 검증 데이터 물리 표면 교체 계약

## 목표

V5 카툰 장면의 지도·칠판·컨테이너·계기판·계산대·브리핑 스크린 안에
이미 존재하는 정보 표현을 검증된 기사 문구와 시장 수치로 교체한다.
화면 모서리에 별도 HUD 카드나 불투명 UI 박스를 추가하지 않는다.

## 데이터 역할

1. 네이버 뉴스/공개 기사 캡처는 기사 원문, 게시 시각, 출처 URL을 제공한다.
2. 시장 데이터 수집기는 종가·등락률·거래량처럼 계산 가능한 숫자를 제공한다.
3. `claude-sonnet-4-6`은 검증 원문을 장면용 짧은 영문 문구로 분류·번역한다.
4. Claude는 금융 숫자를 만들지 않는다. 문구에 숫자가 있으면 검증 원문에
   같은 숫자가 존재하는지 코드가 다시 검사한다.
5. 최종 합성기는 V5 primary 표면의 좌표와 재질을 사용해 원근·조명·질감을
   보존한 채 해당 표면의 내용만 교체한다.

## 실제 실행 흐름

```text
verified_facts + source_url
  -> v5_verified_overlays(value/source_ref/surface_title/surface_meaning)
  -> market_chart_from_verified_scene()
  -> plan_from_scene()이 archetype primary 물리 표면 선택
  -> detection_from_normalized_region()이 승인 좌표를 그대로 사용
  -> composite_planar()이 투명 정보 잉크를 원근 변환·재질 합성
  -> 최종 카툰 프레임
```

## 장면 예

| archetype | 교체할 물리 표면 | 결과 예 |
|---|---|---|
| `weather_map` | 곡면 지도 벽 | `SK HYNIX`, `-3.16%`, `GOES DOWN` |
| `port_emergency` | 지정 컨테이너 정면 | `PORT DELAY`, 실제 물류 지표, 하락 그래프 |
| `retail_shock` | 계산대 매립 영수증 창 | 실제 KOSPI/물가 수치와 짧은 의미 문구 |
| `classroom` | 중앙 칠판 | 검증된 인과 구조와 핵심 문구 |
| `risk_control_room` | 중앙 게이지 문자반 | 실제 위험 지표와 등락률 |
| `trade_calculator` | 저울 기둥 아래 받침 전면 | 실제 무역 수치와 비교 방향 |
| `data_lab` | 중앙 홀로그램 지도 | 실제 지수·등락률·연결 그래프 |

## 차단 규칙

- 검증 원문에 없는 수치는 렌더링 전에 실패한다.
- `market_chart.verified`가 `true`가 아니면 실패한다.
- primary 좌표가 캔버스 밖이면 실패한다.
- 검증 정보면 합성이 실패하면 원본을 조용히 통과시키지 않고 실패한다.
- V5 운영 경로는 `diegetic_fact_overlay.py`의 둥근 사각 카드 렌더러를
  호출하지 않는다.
- 이미지 생성 API는 사실값을 최종 표기하는 주체가 아니다.

## 현재 증거

- 실제 기사 수치 `KOSPI 7,096.89`, `+4.40%`를 data_lab 중앙 홀로그램
  지도 표면에 합성한 무과금 시안:
  `out/v5_pilot/verified_physical_surface_20260802/kospi_verified_data_lab_surface.png`
- 시안 원장:
  `out/v5_pilot/verified_physical_surface_20260802/kospi_verified_data_lab_surface.json`
- 이미지 생성 API 호출: 0건

## 남은 유료 시각 검증

실제 SK HYNIX 등락률을 사용할 때는 네이버 기사만으로 숫자를 추정하지 않는다.
공식/시장 수집기의 같은 거래일 수치와 기사 원문을 교차 확인한 뒤,
`weather_map` 1장으로 `종목명 + 실제 등락률 + 하락 문구`가 지도 속 기상
그래픽처럼 보이는지 사람 검토를 수행한다.

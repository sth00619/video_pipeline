# V5 긴급 경로 감사 및 국소 문구 치환 재설계

작성일: 2026-08-02  
상태: 조사·설계만 완료. 코드 수정, Gemini/FAL 호출, 이미지 생성 없음.

## 1. 결론

문제 시안 `kospi_verified_data_lab_surface.png`는 기존 통과 이미지를 그대로 두고 문구만 바꾼 결과가 아니다.

1. 먼저 `gemini-3-pro-image`로 `data_lab` 배경 전체를 새로 생성했다.
2. 그 새 배경의 넓은 primary 영역에 OpenCV 기반 차트 구성을 다시 합성했다.

따라서 다음 두 실패를 분리해야 한다.

- 캐릭터·색감·무대 이탈: 새 Gemini 배경 생성 단계에서 이미 발생했다.
- 화살표·막대·문구 배치 이탈: 그 뒤의 broad primary-surface 합성 단계에서 발생했다.

현재 방식은 사용자가 요청한 “통과 이미지의 기존 장식 문구 자리만 치환”과 다르다. 이 방식은 중단 대상으로 확정하며 추가 개발하지 않는다.

## 2. 실제 생성 경로

### 2.1 새 배경 생성

`scripts/run_v5_four_scene_actual_pilot.py`

1. `_classify_scene_types()`
2. `attach_v5_scene_contracts()`
3. `plan_v5_scene_contract()`
4. `recommend_v5_archetype()`에서 `data_lab` 선택
5. `LayoutSketcher` 텍스트 계약과 `build_prompt()` 적용
6. `GeminiProvider.generate()` 호출
7. `kospi_july_01_background.png` 저장

즉 새 배경은 기존 archetype 정의를 완전히 우회한 것은 아니다. 다만 archetype 이름과 프롬프트 계약을 사용해도, 새 생성 결과가 기존 승인 PNG와 같은 캐릭터·무대·미감을 보장하지는 못했다.

요청 원장:

- model: `gemini-3-pro-image`
- status: HTTP 200
- reserved: 2026-08-01T19:54:46Z
- completed: 2026-08-01T19:55:17Z
- estimated cost: USD 0.14 / KRW 254
- actual cost: `unverified_until_console_reconciliation`
- automatic retry: false

### 2.2 문제 정보면 합성

`scripts/render_verified_physical_surface_preview.py`

1. 위에서 새로 생성한 `kospi_july_01_background.png`를 입력
2. `plan_from_scene()`
3. `detection_from_normalized_region()`
4. `composite_planar()`
5. `render_chart_content()`로 새 차트 전체 생성
6. `apply_material_fx()`
7. `cv2.warpPerspective()`
8. alpha composite 후 문제 시안 저장

이 단계 자체의 Gemini/FAL 호출은 0건이다. 그러나 입력 PNG가 이미 유료 Gemini 신규 생성본이었다.

## 3. 픽셀 검증

새 Gemini 배경과 문제 시안을 직접 비교했다.

- 이미지 크기: 2752×1536
- 변경 픽셀: 112,786
- 전체 대비: 2.6682%
- 변경 bounding box: `(585, 235)–(1473, 873)`
- 프레임 오른쪽 36% 캐릭터 영역 변경 픽셀: 0

따라서 OpenCV 합성기가 캐릭터 얼굴을 망가뜨린 것은 아니다. 캐릭터 결함은 입력 배경에 이미 존재했다. 반면 지도 안 텍스트·그래프 구성 실패는 OpenCV 합성 단계의 책임이다.

## 4. 기존 승인 자산 보존 점검

기존 승인 파일은 별도 디렉터리에 그대로 존재하며, 2026-08-01~02 작업으로 덮어쓰지 않았다. 수정 시각도 2026-07-30~31로 유지된다.

확인한 승인 자산:

| archetype | 승인 파일 | SHA-256 앞 12자 |
|---|---|---|
| data_lab | `.../kospi_july_2026_scene_type_primary_text_v3/kospi_july_01.png` | `DF1041F550BF` |
| trade_calculator | `.../kospi_july_2026_trade_primary_v5/kospi_july_02.png` | `440D09F98327` |
| risk_control_room | `.../kospi_july_2026_risk_primary_v7/kospi_july_03.png` | `F1E6A1C03638` |
| weather_map | `.../weather_map_primary_v1/weather_map_primary_validation.png` | `ECA0401B4A5A` |
| classroom | `.../classroom_primary_v1/classroom_primary_validation.png` | `7844E40727B6` |
| port_emergency | `.../port_emergency_primary_v2/port_emergency_primary_validation.png` | `F16A0DA5DFAE` |
| retail_shock | `.../retail_shock_primary_v2/retail_shock_primary_validation.png` | `EBF41328716F` |
| briefing_podium | `.../briefing_podium_screenless_v2/briefing_podium_primary_validation.png` | `076E8C0391DB` |
| real_estate_office | `.../real_estate_office_screenless_v2/real_estate_office_primary_validation.png` | `605F1DC40579` |
| job_market_hall | `.../job_market_hall_screenless_v3_manual_retry_01/job_market_hall_primary_validation.png` | `85F283AF225F` |

현재 코드의 `ARCHETYPES`는 총 11개이며 `earnings_stage`는 차단 상태다. 따라서 파일·코드 기준으로는 **승인 사용 가능 10개 + 차단 1개**다. 일부 과거 문서의 “통과 11개/전체 12개” 표기는 현재 코드 및 산출물과 불일치하며, 파일 손상이나 소실을 뜻하지는 않는다.

차단된 `earnings_stage` 실패 후보 파일도 별도 경로에 보존되어 있으나 승인 자산으로 세지 않는다.

## 5. 요청 범위 재정의

앞으로 정보 문구 치환은 다음 범위로 한정한다.

1. 승인된 기존 PNG를 SHA-256으로 고정하고 읽기 전용 입력으로 사용한다.
2. 그 PNG에 이미 존재하는 장식 문구 위치를 자산별 `text slot`으로 수동 등록한다.
3. 기존 글자 픽셀만 지우는 승인된 glyph mask/clean plate를 사용한다.
4. 검증된 실제 문구와 수치만 같은 슬롯에 다시 그린다.
5. 캐릭터, 무대, 조명, 소품, 그래프 위치는 다시 생성하거나 재배치하지 않는다.
6. 원본은 덮어쓰지 않고 별도 출력 파일을 만든다.

이 방식에서 `archetype` 공통 좌표는 충분하지 않다. 같은 archetype도 생성 이미지마다 실제 글자 위치가 달라지므로 슬롯은 반드시 **승인 PNG의 SHA-256**에 귀속한다.

## 6. 제안 데이터 계약

```json
{
  "base_asset": {
    "path": "approved/weather_map_primary_validation.png",
    "sha256": "..."
  },
  "slot": {
    "slot_id": "weather_main_label_01",
    "original_text": "HEAVY RAIN",
    "glyph_mask_path": "masks/weather_main_label_01.png",
    "text_box": [x, y, width, height],
    "rotation_deg": 0,
    "font_profile": "weather_map_bold_outline_v1",
    "max_lines": 2
  },
  "verified_replacement": {
    "text": "SK HYNIX",
    "value": "[검증된 등락률]",
    "source_ref": "...",
    "source_url": "..."
  }
}
```

수치 토큰은 Claude가 만들지 않는다. 뉴스·거래소 등 검증 원문에 실제 포함된 값만 입력 계약을 통과한다. Claude는 검증된 사실을 짧은 영문 문구 후보로 정리하는 역할까지만 맡는다.

## 7. 렌더링 규칙

- 새 사각 카드, 새 패널, 새 화살표, 새 막대그래프를 만들지 않는다.
- 기존 장식 글자 영역 이외 픽셀은 변경하지 않는다.
- 원근은 새로 추정하지 않는다. 슬롯에 저장된 회전·기울기만 재사용한다.
- 장문의 문장을 억지로 축소하지 않는다. 슬롯 길이를 넘으면 실패 처리하고 더 짧은 검증 문구를 요구한다.
- 기존 텍스트 제거는 광범위 인페인팅이 아니라 승인된 작은 glyph mask와 clean plate로만 처리한다.
- 출력 후 mask 바깥 픽셀이 원본과 동일한지 자동 비교한다.
- 실패 시 generic card, broad surface compositor, Gemini 재생성으로 폴백하지 않는다.

## 8. 첫 검증 제안

첫 구현 검증은 이미 승인된 `weather_map` 한 장만 사용한다.

- 기존 `HEAVY RAIN` 슬롯: 검증된 종목명 또는 짧은 시장 상태 문구
- 기존 `WIND ADVISORY` 슬롯: 검증된 방향 문구
- 기존 `55°F` 슬롯: 검증된 등락률

실제 수치는 출처 확인 전 넣지 않는다. 코드 반영 전에는 다음 4개를 먼저 제출한다.

1. 기준 PNG 경로와 SHA-256
2. 세 슬롯의 glyph mask/좌표 시각화
3. 허용 문구 길이와 글꼴 프로필
4. mask 밖 픽셀 불변 테스트 계획

이 검토가 승인된 뒤에만 국소 편집 샘플 1장을 만든다.

## 9. 중단 상태

- OpenCV broad primary-surface 합성: 폐기, 추가 개발 금지
- Gemini/FAL 이미지 생성: 보류
- 40씬 파일럿: 보류
- 기존 승인 archetype 자산: 읽기 전용 보존


# V5 최종 후보 세트 상태 — 2026-07-30

## 현재 결론

Gemini 3 Pro Image의 strict_textless 경로로 만든 8개 장면을 V5 최종 후보로 보관한다.
다만 이는 **최종 운영 lane 확정이 아니라 사람 검토 대기 후보**다. 라우터의 실제 hero/body
렌더링 잠금은 유지한다.

## 후보 세트

| 씬 | 마스코트 위치 | 원본 |
|---|---|---|
| 01 항만 위기 | 오른쪽 | `gemini_pro_strict_textless_v5_identity_continuity_01_port/bench_01_port.png` |
| 02 매장 가격 충격 | 왼쪽 | `gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_02_retail.png` |
| 03 강의실 설명 | 오른쪽 | `gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_03_classroom.png` |
| 04 강의실 비교 | 왼쪽 | `gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_04_classroom2.png` |
| 05 날씨 스튜디오 | 오른쪽 | `gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_05_weather.png` |
| 06 양분 무대 | 중앙 | `gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_06_split.png` |
| 07 무역 분석실 | 왼쪽 | `gemini_pro_strict_textless_v5_identity_continuity_07_trade/bench_07_trade.png` |
| 08 데이터랩 | 중앙 | `gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_08_datalab.png` |

01은 내부 분할컷처럼 보이던 구도를, 07은 기준 마스코트와 다른 얼굴·테두리 풍을
재생성으로 보정했다. 모든 요청은 씬당 한 번만 실행했고 자동 재시도는 사용하지 않았다.

## 자동 검증 범위

- 구조 QualityGate: 8/8 통과
- 레이아웃: 좌 3, 중앙 2, 우 3으로 씬 계약에 따라 배치
- 빈 배경·16:9·소품 밀도·자막/로고 안전영역: 자동 점검 대상
- 캐릭터 정체성·분할컷·텍스트 오염: 사람 검토 항목

로컬 OCR 엔진이 없으므로 자동 통과는 무문자 통과를 뜻하지 않는다. AI가 그린
숫자·글자는 어떤 경우에도 사실 정보로 사용하지 않으며, 검증 수치는 Pillow/FFmpeg
오버레이만 사용한다.

## 비용 기록

- 8씬 구도 세트: 추정 $1.12
- 01/07 보정 검증: 추정 $0.28
- 합계: 추정 $1.40, 실행 시점 환율 스냅샷(1 USD = 1,815 KRW) 기준 2,540원
- 실제 청구액: `unverified_until_console_reconciliation`

## 다음 운영 진입 게이트

1. 이 8씬 후보의 사람 시각 검토 승인
2. Google AI Studio/결제 콘솔의 실제 청구 대조
3. 검증 완료 대본과 씬별 `v5_verified_overlays` 입력 준비
4. 40씬 비용 상한과 콘솔 대조 시점 승인
5. 첫 1~3씬만 렌더링해 사람 검토 후에 나머지 씬 진행

`docs/V5_VERIFIED_SCENE_INPUT_TEMPLATE.json`은 이 입력의 형식이며,
`scripts/validate_v5_pilot_input.py --input <실제-입력.json>`은 API 호출 전에
출처 URL·검증 사실 원문·오버레이 값 일치·좌표·배경 파일을 차단형으로 검사한다.
템플릿은 실제 사실을 포함하지 않으므로 그대로는 의도적으로 실패한다.

P5 LoRA는 현 시점에서 착수하지 않는다. Gemini 참조 기반 생성에서 캐릭터 드리프트가
정해진 임계치를 넘는다는 별도 증거와 데이터셋 권리 확인이 있을 때만 검토한다.

# V5 일반 씬 FAL 모션 파일럿 결과 — 2026-08-01

## 범위

- 입력: Gemini 최종 후보 `port_emergency` 일반 씬 1장
- 계약: `scene_type=general`, `v5_verified_overlays=[]`, `use_kling=true`
- 모션: `walking_intro`, 5초, 오디오 비활성화, 카메라 고정
- 공급자: FAL `fal-ai/kling-video/v2.6/pro/image-to-video`
- 재시도: 없음 (`automatic_retry=false`)
- 폴백: 없음 (`fal_only=true`)

## 실행 전 안전 검증

| 항목 | 결과 |
|---|---|
| 검증 사실 오버레이 존재 | 없음 |
| 기사 증거 씬 | 아님 |
| 일반 씬 Kling 후보 | 통과 |
| 생성 이미지 API 호출 | 없음 |

## 결과

- 생성 상태: `success_unverified_until_fal_console_reconciliation`
- 출력: `out/v5_motion_pilot/general_port_walking_intro_20260801/general_port_walking_intro.mp4`
- 실제 파일 길이: 5.041667초
- 추정 비용: $0.35 / ₩490 (`USD_KRW=1400` 스냅샷)
- 실비 상태: FAL 콘솔 대조 전이므로 미확정

## 사람 육안 검토 결과

| 항목 | 판정 | 관찰 결과 |
|---|---|---|
| 캐릭터 행동 | 통과 | 걷는 자세 → 정지 → 손 흔들기가 구분된다. |
| 반응 소품·광원 | 부분 통과 | 첫 프레임의 번개 변화가 의도된 반응인지 원본 보존 실패인지는 확정하지 않는다. |
| 카메라 | 통과 | 배경 앵커 위치가 유지돼 팬·줌·흔들림·리프레이밍이 없다. |
| 생동감 | 통과 | 기존 지글링보다 캐릭터 중심 움직임이 분명하며, 안전성을 우선한 절제된 결과다. |

## 동결된 운영 정책

- `scene_type=general`이고 검증 사실 오버레이가 없는 씬에만 이 5개 모션 템플릿을 사용한다.
- `metric`·`graph`·`diagram` 또는 `v5_verified_overlays`가 있는 씬은 계속 FAL 대상에서 제외한다.
- 다음 일반 씬 모션 검토 때에는 반응 소품 또는 광원의 변화가 보이는 프레임과 보이지 않는 프레임을 나란히 제출한다. 이 비교가 없으면 반응 소품 평가는 보류한다.

## 회계 원칙

- FAL 콘솔의 요청 건수와 실비를 확인한 뒤에만 이 파일럿 비용을 확정한다.
- 이번 성공은 정보 오버레이가 없는 일반 씬에만 적용된다. `metric`·`graph`·`diagram` 및 검증 사실 오버레이 씬은 계속 FAL 대상에서 제외한다.

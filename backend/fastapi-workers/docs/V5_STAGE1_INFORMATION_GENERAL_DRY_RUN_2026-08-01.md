# V5 유형 1·2 — 5씬 라우팅 드라이런

작성일: 2026-08-01  
범위: 이미지/LLM API 호출 없이 `ScriptWorker`의 scene type 분류와 `ImagesWorker`용 V5 렌더 계약만 점검했다.

## 결과

5개 씬 모두 V5 계약을 생성했다. 정보형 3개는 Gemini Pro hero lane과 사실 오버레이 후합성 경로로, 일반형 1개는 Gemini Pro body lane·오버레이 비적용 경로로 분리되었다. `earnings_stage`는 후보에 포함되지 않았으며, 이번 드라이런도 차단 상태를 건드리지 않았다.

| 씬 | scene_type | archetype | tier | 사실 오버레이 입력 | 해석 |
|---|---|---|---|---:|---|
| `kospi_july_01` | `graph` | `data_lab` | `hero` | 있음 | 정보형: 지도 패널에 AI 장식, 검증값은 Pillow 후합성 |
| `kospi_july_02` | `graph` | `trade_calculator` | `hero` | 있음 | 정보형: 저울 받침 primary surface 사용 |
| `kospi_july_03` | `metric` | `risk_control_room` | `hero` | 있음 | 정보형: 중앙 게이지 primary surface 사용 |
| `general_port_narrative_04` | `general` | `port_emergency` | `body` | 없음 | 일반형: 항만 서사에 맞는 캐릭터 중심 무대, 사실 오버레이 미적용 |
| `text_key_message_05` | `text` | `classroom` | `hero` | 없음 | 장면 속 짧은 문구용 정보형. 실제 사실값이 없으므로 이번 입력에서는 합성할 값 없음 |

## 발견·수정한 드라이런 어댑터 결함

`scripts/dry_run_v5_images_worker_pipeline.py`가 제목 없는 씬의 `scene_id`를 `title`로 복사하고 있었다. 예를 들어 `general_port_narrative_04`의 순번 `04`가 scene type 분류기에서 수치 신호로 해석되어 `metric`으로 오분류됐다.

수정: 제목이 없으면 빈 문자열을 넘기도록 변경했다. 이는 드라이런 어댑터만의 문제이며, 금융 수치나 실제 `ScriptWorker`의 사실 데이터를 만들거나 변경한 작업이 아니다.

수정 뒤 5씬 결과에서 일반형은 `general/body/not_applicable`로 정상 분리됐다.

추가로 일반형 장소 선택 규칙을 보정했다. `general` 씬에 항만·물류 단서와 `background`가 함께 있으면 이전에는 설명 단서가 먼저 잡혀 `classroom`으로 갈 수 있었다. 이제 항만·물류 단서를 먼저 평가해 `port_emergency`를 선택한다. 이 규칙은 `test_general_port_narrative_prefers_port_stage_over_background_wording`으로 고정했다.

## 참조 자산 재생성 합류 상태

이번 단계에서 새 참조 자산을 생성하거나 교체하지 않았다. 현재 `out/references/`에서 실제 Gemini 요청에 사용되는 파일은 아래 두 개뿐이며, 모두 2026-07-29 생성본이다.

| 역할 | 파일 | SHA-256 |
|---|---|---|
| 캐릭터 참조 | `out/references/character_reference_v2_textless.png` | `d4f39ae039d1b1dd33010c5c4d56dd78e118df9a729cfa0dc627ad6a0c70e797` |
| 스타일 참조 | `out/references/style_reference_v2_textless.png` | `867fce78732b3603df709479a67366987bda34642e515123f51aab00c75fae87` |

`scripts/build_v5_gemini_references.py`를 확인한 결과, 두 파일은 `final (1).mp4`의 5초 프레임을 크롭한 완성 장면 이미지다. 따라서 파일명에 `textless`가 붙어도 순수한 캐릭터 시트/스타일 시트는 아니다. 새로 정제한 참조 자산은 아직 이 디렉터리에 나타나지 않았으므로, 이번 5씬 드라이런은 참조 자산 재생성의 완료를 검증하거나 이를 반영한 결과가 아니다.

## 검증 근거

- 결과 JSON: `out/v5_pilot/kospi_july_2026/scene_type_routing_dry_run_5_scene_report.json`
- 입력 JSON: `out/v5_pilot/kospi_july_2026/scene_type_routing_dry_run_5_scene_input.json`
- 테스트: `test_scene_type_classification.py`, `test_v5_scene_type_archetypes.py`, `test_v5_scene_type_prompt_contract.py` — **26 passed**
- 이미지 API 호출: 0건
- LLM API 호출: 0건

## 다음 승인 필요 지점

1. 참조 자산 재생성 결과를 실제 이미지로 검토한다.
2. 이 라우팅 계약을 사용한 소규모 정보형·일반형 실제 이미지 생성은 장면/비용 상한을 정해 별도 승인 후 실행한다.
3. 기사 캡처형 구현은 `V5_STAGE0_ARTICLE_CAPTURE_STATUS_2026-08-01.md`의 URL형 런타임 검증 또는 이미지 입력형 계약 결정을 받은 뒤에만 시작한다.

# WO-IMG-01-F 결과 — scene07 해부학·화풍·의미 전달 회귀

- 작성일: 2026-08-28 KST
- 대상 attempt: `a259e66e5bdd462997a639dade7dd77e`
- 대상 이미지: `artifacts/wo_scene07_promptfix_canary_v3_20260828/scene_07_raw.png`
- 이미지 SHA-256: `93eea450aea1fd398fb4774f9c303c3acedaed0d44ef46dbe84f4710fa2834c3`
- 최종 판정: `rejected_by_user_visual_review`
- 유료 API 호출: 0회

## 1. 결론

사용자 판정이 맞다. 이 canary는 해부학, 채널 화풍, 장면 의미 전달에서 모두 실패했다. 종전 보고가 얼굴의 일부 수치와 OCR·물리 표면만 확인한 뒤 “일부 개선”으로 표현한 것은 검증 범위가 지나치게 좁었다. HTTP 200과 부분 계측 개선은 전체 이미지 승인 근거가 아니다.

이번 조사에서 원인은 세 계층으로 분리됐다.

1. sentinel 문자 치환은 해부학·화풍 문장을 삭제하지 않았다. 이 수정과 회귀 사이의 직접 인과 가설은 실제 송신 payload 재구성으로 배제했다.
2. 공통 참조 선택기가 `data laboratory`를 인식하지 못해, 실제 데이터 연구실 참조 대신 기본 브리핑·시장 흐름 참조를 골랐다.
3. 운영 `ImagesWorker`에는 해부학·화풍·장면 의미의 전체 시각 QA가 있지만, 이번 독립 canary 실행기는 그 단계를 호출하지 않고 얼굴 수치와 텍스트 표면만 판정했다.

따라서 특정 scene07 그림을 손으로 고친 것이 아니라, 모든 주제의 공통 참조 선택·캐릭터 실루엣 계약·canary 승인 절차를 보완했다.

## 2. 기존 판정에서 누락된 실패

| 범주 | 사용자 육안 판정 | 이번 최종 판정 |
|---|---|---|
| 캐릭터 해부학 | 동전 아래에 긴 사람 다리가 달린 형태 | 실패 |
| 화풍 | 굵은 잉크·셀 셰이딩보다 가는 선·부드러운 그라데이션 | 실패 |
| 장면 의미 | 병 두 개가 계산에서 제외된 기업이라는 관계가 읽히지 않음 | 실패 |
| 정보 표면 | 그래프 장식으로 가득 차 결정론 텍스트 표면 없음 | 실패 |
| 얼굴 세부 | 홍채 크기·색·반사광·눈썹 계약 실패 | 실패 |

병 두 개의 존재는 `required_prop_count=2`를 만족했을 뿐이다. “두 기업을 제외해도 전체 영업이익이 크다”는 관계를 전달하지 못했으므로 의미 보존 성공으로 판정하지 않는다.

## 3. 실제 송신 payload 포렌식

실행 당시 코드 커밋 `f5340c6`을 `git archive`로 별도 추출하고, 현재 산출물을 읽기 전용으로 연결한 뒤 가짜 provider로 실제 POST 직전 프롬프트와 참조 선택을 재구성했다.

### 3.1 해시 재현

| 계층 | 원장 값 | 재구성 결과 |
|---|---|---|
| worker 이전 prompt SHA-256 | `cf4c9f2f84a7c74c3ff44a6ed20a7269236853caf234abb516b0ae6f30270778` | 일치 |
| 실제 송신 prompt SHA-256 | `f57eb9028db7c428cfc71e4b4e01f9b2fc063b873baecf18fbf8fa746d3f6bfc` | 일치 |
| payload SHA-256 | `46c5316d1bd1899b8fde0bb1b12a95203b66d8629890b4bc5be8828c45d0ad75` | 원장 보존 |

실제 송신 프롬프트에는 `compact anatomy`, `Use natural connected anatomy`, `bold ink outlines`, `cel shading`, `Two unlettered containers`가 모두 남아 있었고 `shapesinguistic`는 없었다. 따라서 sentinel 연쇄 치환 방지 코드가 해부학·화풍 지시를 삭제하거나 축소했다는 가설은 배제한다.

### 3.2 실제 전송 참조

| 순서 | 파일 | SHA-256 | 판정 |
|---:|---|---|---|
| 1 | `channel_character_face_range_v2.png` | `7e7981e389d07c4c3eca908708365cdcc809226c0f9a039f7ff7f62bbad8e40e` | 정상 전송 |
| 2 | `channel_style_job52_briefing.png` | `b31b98d6b761534cdfcac5e1ac747e8a2be69c4bf168ac35b0e06b596c15c46a` | 전송됐으나 문맥상 차선 |
| 3 | `channel_style_job52_market_flow.png` | `c9e821d51a44d7184f84de92962e76b244c8794d49c87ea009f143948a303a74` | 전송됐으나 문맥상 차선 |

참조가 누락된 것은 아니다. 문제는 `select_contextual_reference_paths()`가 `data-lab`만 일부 분기로 인식하고 실제 prompt의 `data laboratory`는 인식하지 못해 기본 `briefing` 그룹으로 떨어진 것이다. 저장소에는 더 가까운 `channel_style_job52_data_lab.png`가 이미 있었지만 선택되지 않았다.

## 4. 공통 운영 수정

### 4.1 데이터 연구실 문맥 선택

`data laboratory`, `data lab`, `data-lab`, `data_lab`, `earnings laboratory`, `lab coat`를 공통 `data_lab` 문맥으로 묶었다. 다음 요청에서는 얼굴 v2와 역할별 scene05 확대 얼굴을 유지하면서, 남은 화풍 슬롯에 `channel_style_job52_data_lab.png`를 우선 사용한다.

- 데이터 연구실 참조 SHA-256: `87c52f3ef3c0bdd0bfddeb3ed08f15f7038c38c48fc5ebf291db625d8aed05e6`
- 적용 지점: 실제 영상 생성과 단일 장면 재생성이 모두 호출하는 `select_contextual_reference_paths()`

이 규칙은 scene07 번호를 보지 않는다. 데이터 연구실·실적 연구실·실험복 맥락을 가진 새 주제의 장면에도 동일하게 적용된다.

### 4.2 동전 실루엣 계약

기존 `compact anatomy`, `natural connected anatomy`는 여분 손·융합 손은 막아도 “동전 머리 + 긴 인간 다리”를 충분히 배제하지 못했다. `character-integrity-v5-coin-silhouette`와 `job52-range-v2-operational-v2`에 다음 구조를 명시했다.

- 하나의 둥근 동전 원판이 머리이자 몸통 전체다.
- 별도 인간 몸통을 추가하지 않는다.
- 팔 두 개는 옆 테두리, 짧고 둥근 다리 두 개는 아래 테두리에 붙는다.
- 긴 인간 다리가 동전 머리 아래로 늘어지는 형태를 금지한다.

의상·모자·표정·행동·구도는 계속 장면별로 달라질 수 있다. 실루엣만 공통 정체성 경계로 고정한다.

### 4.3 canary 사용자 육안 보류

공통 `canary_visual_review.py`를 추가했다. 유료 canary가 HTTP 200을 반환해도 다음을 자동으로 기록한다.

- `status=pending_user_visual_review`
- `image_attachment_required=true`
- `approval_blocked=true`
- 필수 육안 항목: 해부학, 화풍, 장면 의미, 텍스트·물리 표면, 예상 밖 시각 결함

사용자가 모든 항목을 명시적으로 통과시키기 전에는 `개선됨`, `승인 근접`, `통과` 판정을 만들 수 없다. 얼굴 수치·OCR·물리 표면 같은 기존 자동 게이트는 그대로 유지한다.

운영 `ImagesWorker._inspect_generated_visual_image()`에는 이미 `character_anatomy`, `style_severe_mismatch`, `scene_semantic_mismatch`, 필수 소품 검사가 있다. 이번 결함은 제품 워커의 게이트를 삭제해서가 아니라 독립 canary가 그 공통 전체 시각 QA를 우회한 데서 보고 누락이 발생했다. 이후 canary는 사용자 육안 보류를 반드시 추가하고, 제품 운영 경로는 기존 자동 전체 시각 QA도 계속 수행한다.

## 5. 과거 spec과 새 계약의 관계

기존 `scene07-promptfix-canary-spec.json`은 이미 실행된 요청의 승인 prompt SHA-256을 보존한다. 해부학 계약을 강화한 현재 prompt는 그 해시와 달라진다. 과거 spec의 해시를 덮어써 이력을 지우지 않고, 같은 실행기를 다시 사용하면 hash drift로 중단한다. 다음 유료 재도전은 새 계약 버전·새 prompt hash·새 scene key를 가진 별도 spec과 원장으로만 진행한다.

## 6. 진행률 정정과 세 목표

목표 3의 기존 75~82% 추정은 이 canary의 전체 시각 회귀를 반영하지 못했다. 이를 약 65~70%로 하향한다. 텍스트·수치·OCR 계약의 진전은 유효하지만, 실제 생성 이미지에서 해부학·화풍·장면 의미까지 반복 통과했다는 증거는 아직 부족하다.

- 목표 1: 승인 대본·TTS·자막 청크가 장면 의미의 기준이라는 계약은 변하지 않았다. 이번 scene07은 그 의미를 그림이 충분히 전달하지 못한 목표 3의 실패다.
- 목표 2: 실패 이미지를 Fal로 보내지 않는 기존 순서를 유지한다. 문자·그래프뿐 아니라 해부학·화풍·의미 실패도 Fal 전 차단 사유다.
- 목표 3: 참조 문맥, 실루엣, canary 육안 보류를 공통 운영 계약에 추가했다. 다음 실 API 표본에서 실제 성공 여부를 다시 확인해야 한다.

## 7. 검증과 다음 단계

- red: `42de8ad`, 4 failed — 데이터 연구실 참조, 명시적 실루엣, canary 사용자 보류, 보고서 정정 누락 재현
- green 집중: 23 passed (`green-focused.xml`)
- green 운영 경계: 실 provider audit·단일 재생성·전체 시각 QA 포함 71 passed (`green-operational.xml`)
- 전체 오프라인: 1,121 passed, 20 warnings (`full-offline.xml`)
- scene42 동결 유지
- TTS, Fal/Kling, MP4 조립, 썸네일 미실행
- 이번 교정 중 Gemini 포함 유료 API 호출 0회

다음 유료 canary는 오프라인 회귀가 끝난 뒤 새 spec으로 한 장만 실행한다. 결과 이미지를 사용자에게 실물 첨부하고, 공급자 성공·자동 품질 게이트·사용자 육안 판정을 서로 분리해 보고한다.

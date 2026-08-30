# WO-IMG-03 — 유사 사례 검증과 공통 이미지 파이프라인 이식

작성일: 2026-08-30
범위: 오프라인 조사·공통 코드·회귀. 유료 이미지 호출 0회, TTS/Fal/조립 0회, push 0회.

## 1. 결론

외부 사례는 우리 문제를 한 번에 해결하는 복사 가능한 제품이 아니라, 서로 다른 실패 층을 분리하는 근거로 쓸 수 있었다.

- 정보 이미지의 **부분 정확도**와 **장면 전체 완전정확도**는 분리해야 한다.
- 숫자·문자·기하처럼 물리적으로 확인 가능한 항목은 결정론 검사로, 의미·화풍·모호한 소품은 구조화된 판정과 사용자 육안으로 확인해야 한다.
- 참조를 보냈다는 사실만으로 일관성이 보장되지 않는다. 참조 선택 이유와 생성 후 후보 검수가 별도 단계여야 한다.
- 자동 판정과 사용자 판정이 갈리면 한쪽을 조용히 덮어쓰지 않고 이견 자체를 보존해야 한다.

이를 특정 Job이나 scene 번호 분기로 구현하지 않고, 공통 `visual_qa`, canary 검토, 품질 집계 모듈에 반영했다.

## 2. 1차 자료·공개 코드 재검증

| 사례 | 확인한 원자료 | 검증 결과 | 채택 여부 |
|---|---|---|---|
| IGenBench | [논문](https://arxiv.org/abs/2601.04498), [공개 저장소](https://github.com/MisterBrookT/IGenBench) commit `f4b253a8fdb90754cacc1c7c9d0dc31503b2eaf3` | 600개·30유형, atomic yes/no, Q-ACC와 I-ACC 분리, 최상위 0.90/0.49, Data Completeness 0.21을 확인. 공개 `EvalEngine`도 질문 하나씩 판정하고 전체 질문 완료를 별도 확인한다. | 명칭은 복제하지 않고 `item_accuracy`와 `fully_accurate_scene_rate`로 이식 |
| ArtChart | [논문](https://arxiv.org/abs/2607.16060) | 텍스트 없는 회색조 구조 조건, OCR·배치·미학 보상, 6축 평가를 확인. | 현재의 base raster → 물리 표면 → 결정론 텍스트 구조를 유지하는 근거로 사용. 모델 학습/RL은 미채택 |
| Phantom | [논문](https://arxiv.org/abs/2502.11079), [공개 저장소](https://github.com/Phantom-video/Phantom) commit `bd84b602dcc949e23c89cbbf266b6f5975f2f025` | 다중 참조의 외형 혼동과 텍스트-이미지 정렬 개선은 확인. 그러나 “참조 이미지는 4장 이하”라는 문장이나 코드 상한은 찾지 못했다. | **4장 이하 규칙은 근거 미확인으로 미채택.** 참조별 역할 설명과 혼동 위험만 유지 |
| SciDraw-Bench | [논문](https://arxiv.org/abs/2606.28406) | OCR label recall/CER, 명시적 루브릭의 항목별 yes/no, 최소 2개 판정자, inter-judge agreement 보고를 확인. 사람 검증은 논문에서도 진행 중이라고 제한한다. | 사용자-자동 판정의 일치율·이견 원장으로 경량 이식 |
| VISTAR | [논문](https://arxiv.org/abs/2508.06152) | 결정론 물리 지표와 HWPQ 구조화 의미 평가의 이중 층을 확인. 현재 공개 PDF는 본문에서 “full prompt in Appendix E”라고 말하지만 17쪽 파일에 Appendix E 원문은 포함되지 않았다. | 이중 층 원칙만 채택. 미확보 프롬프트를 재구성하거나 원문처럼 주장하지 않음 |
| ViMax | [논문](https://arxiv.org/abs/2606.07649), [공개 저장소](https://github.com/HKUDS/ViMax) commit `05a48943878312d88fe5a016c12a9654940ecc43` | `ReferenceImageSelector`는 후보가 8개 이상이면 텍스트 1차 축소 후 멀티모달 재선택하고, 이전 프레임·캐릭터·배경 역할을 설명한다. `BestImageSelector`는 복수 후보의 캐릭터·공간·설명 일치도를 비교한다. | 참조 계보와 생성 후 별도 검수라는 단계 분리만 채택. LLM 선택기를 그대로 복제하지 않음 |

## 3. scene28의 새 실패와 원인

scene28 실물에서 오른손의 검은 소품은 콘솔에 붙은 제어 레버처럼 보이지만 총·무전기·드릴로도 읽힌다. 프롬프트에는 특정 손소품 지시가 없고, `risk_control_room` 프로필이 `one narration-essential risk prop`라고만 요구했다. 따라서 원인은 “총을 요청함”이 아니라 **역할·형태·부착점 없는 소품 슬롯을 모델에 열어 둔 것**이다.

공통 프로필을 다음처럼 수정했다.

- 장면에 필요한 레버나 게이지는 콘솔 베이스에 물리적으로 결합해야 한다.
- 레버·스위치·도구형 소품은 기능을 한눈에 판별할 수 있어야 한다.
- 승인 내레이션이 정확한 물체를 요구하지 않으면 캐릭터 손에 무기·총·드릴·무관한 도구처럼 읽히는 물체를 두지 않는다.

이 규칙은 scene28 번호를 알지 못하며 모든 `risk_control_room` 장면에 적용된다.

## 4. 공통 운영 코드 반영

### 4.1 항목 정확도와 장면 완전정확도

신규 `app/utils/scene_accuracy_metrics.py`는 다음을 별도로 기록한다.

- `item_accuracy`: 실제 pass/fail로 판정된 항목 중 통과 비율
- `fully_accurate_scene_rate`: 텍스트·의미·얼굴·화풍·구성·표면·예상 밖 이상 징후가 모두 통과한 장면 비율
- `pending`과 `not_applicable`: pass로 바꾸지 않고 별도 집계. pending은 장면 완전정확도를 차단한다.

공통 `assess_visual_alignment()` 결과에 `accuracy_metrics`를 자동 부착했다. 따라서 “텍스트는 통과했지만 의미/표면은 실패”한 장면을 텍스트 통과율 하나로 성공처럼 요약할 수 없다.

### 4.2 자동 QA의 모호한 소품 검사

`visual_qa.py` 정책을 v19로 올리고 `unexpected_or_ambiguous_props` 구조화 필드를 추가했다. 정체나 인과적 역할이 읽히지 않는 소품, 특히 총·드릴·무전기처럼 오인 가능한 손소품이 있으면 `unexpected_or_ambiguous_prop` 하드 실패가 된다.

### 4.3 유료 canary의 목록 밖 이상 징후 검사

`canary_visual_review.py` v2는 다음 두 항목을 필수로 추가했다.

- `unexpected_or_ambiguous_props`
- `unlisted_failure_scan`

즉 보고서 작성자가 원래 고치려던 항목만 보지 않고, 기존 실패 목록 밖의 이상 징후를 한 번 더 훑어야 한다. 결과 이미지 실물과 SHA-256이 없으면 기존처럼 검토 객체를 만들 수 없다.

### 4.4 판정 이견 원장

신규 `visual_judgment_disagreement_log.py`는 자동 판정과 사용자 판정의 공통 boolean 항목만 비교해 일치율과 이견 목록을 기록한다. 이견은 자동으로 합의 처리하지 않으며 사용자 확인 전 승인을 열지 않는다.

## 5. 채택하지 않은 것과 한계

- Phantom의 “4장 이하”는 현재 확보한 논문·코드에서 검증되지 않아 운영 상한으로 쓰지 않는다.
- VISTAR Appendix E 프롬프트 원문은 현재 PDF에서 확보하지 못했으므로 흉내 낸 프롬프트를 원문처럼 쓰지 않는다.
- ViMax의 복수 후보 생성/선택은 비용과 지연을 크게 늘린다. 현재 운영에는 품질 실패 후 표적 재생성 구조가 이미 있으므로, 이번에는 단계 분리 원칙만 반영했다.
- 자동 비전 판정은 사람을 대체하지 않는다. SciDraw-Bench도 사람과의 보정이 완료되지 않은 자동 지표를 calibrated measurement로 해석하지 말라고 제한한다.
- 외부 연구의 수치를 우리 파이프라인 성능 수치로 전용하지 않는다. 우리 지표는 다음 실 canary부터 자체 데이터로 채운다.

## 6. 테스트

- 선행 실패: 신규 모듈 부재, 모호한 `risk prop`, canary 필수 항목 부재를 재현했다.
- 수정 후 집중 회귀: 52 passed.
- 현재 작업 트리를 읽기 전용으로 마운트한 격리 Docker 전체 회귀: **1,187 passed, 0 failed, 20 warnings**.
- 호스트 Python은 `faster_whisper`, `cv2` 부재로 수집 실패했으므로 전체 green 근거로 사용하지 않았다.
- 유료 호출은 하지 않았다. 다섯 실패 원인의 오프라인 방어가 끝나고 다음 실증 계보를 고정한 뒤 진행한다.

## 7. 다음 단계

1. scene00의 비교 수치를 저울의 실제 픽셀 표면에 결박한다.
2. scene07의 `summary_monitor` 실제 픽셀 quad를 찾아 `143조 원` 최종 합성을 보장한다.
3. scene15의 `max_occurrences=1`을 원본 해상도 표면별 OCR로 확인한다.
4. scene28 모호한 소품 금지와 색조/얼굴 분리를 다음 실물에서 확인한다.
5. 다음 유료 canary는 다섯 항목을 모두 포함하고, `item_accuracy`, `fully_accurate_scene_rate`, 자동-사용자 이견을 같은 보고서에서 나란히 제시한다.

push는 사용자 지시대로 계속 보류한다.

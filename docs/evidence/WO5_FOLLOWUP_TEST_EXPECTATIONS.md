# WO-5 승인 후 테스트 기대값 정리

Antigravity의 WO-5 최종 승인 후, 구현과 불일치하던 테스트 기대값을 제품 코드 변경 없이 정리했다.

## 변경 커밋

- `93f4e92` `test(wo5): align stale expectations with approved contracts`

## 변경 사항

- `tts_sentence_pause_ms`: `200` → `350`
- `tts_thought_group_pause_ms`: `70` → `110`
- grounding 헤더: `CRITICAL ENTITY GROUNDING INSTRUCTIONS` → `CRITICAL ENTITY & FIGURE GROUNDING INSTRUCTIONS`
- `원달러 환율` 기대 영문명: 오래된 가상 라벨 `USD/KRW CORP` → SSOT의 검증 공식명 `USD/KRW Exchange Rate`

마지막 항목은 첫 번째 문자열 assertion을 정리한 뒤 드러난 같은 테스트의 후속 불일치다. `fictionalized_labels` 인자는 호출 계보에 남아 있으나 현재 `_build_prompt_from_narration()`의 엔티티 표기 계약은 `entity_english_map.get_entity_english_name()`의 검증된 공식 영문명을 사용한다. 제품 구현은 수정하지 않았다.

## 검증

관련 테스트:

```text
6 passed in 0.76s
```

전체 테스트:

```text
10 failed, 513 passed, 13 warnings in 121.37s (0:02:01)
```

기존 WO-5 증거의 `13 failed, 510 passed`에서 기대한 세 테스트가 통과로 이동했다. 남은 실패는 다음 조사 범위와 정확히 일치한다.

- article discovery 공급자 구성: 1건
- 60초 영상 Fal 클립 정책 3↔4 불일치: 1건
- info-surface compositor 상태/API 불일치: 6건
- provider request audit 비용 원장 불일치: 2건

전체 출력은 `WO5_followup_full_pytest_log.txt`에 보존했다.

- 줄 수: 95
- SHA-256: `e1fd377d2b4b6c893874481c3668d72ac36523d308fdc98c2eb71f99648788f8`
- `C:\tmp` UTF-16 원본과 저장소 UTF-8 파일의 줄 단위 비교: `95/95`, 차이 `0`

기존 사용자 변경 `logs/pipeline-autostart.log`는 포함하거나 수정하지 않았다.

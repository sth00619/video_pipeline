# WO-IMG-01-B — 상류 사실값 근거 검증 게이트

## 1. 결론

`facts_from_verified_scene()`의 단방향 부분 문자열 결함을 **실패 테스트 선행 → 수정 → 커밋 사본 격리 재검증** 순서로 수정했다.

- 테스트 선행 커밋 `1c4e071`: `4배 ← 14배`, `143조 ← 143조 5000억 원`이 모두 잘못 허용돼 **2 failed**.
- 구현 커밋 `ef57daa`: 완전한 수치·날짜 토큰 계약을 공용 모듈로 만들고 자동 오버레이 생성과 최종 표면 어댑터 양쪽에 적용.
- 수정 커밋만 `git archive`로 추출한 검사: 새 회귀 **24 passed**.
- 작업 트리의 관련 집중 검사: **75 passed**.
- 소켓을 차단한 전체 검사: **1000 passed, 1 deselected**. 제외한 한 건은 기존 Google RSS 실제 접속 테스트다.

이번 작업은 운영 배포가 아니다. Gemini·Claude·TTS·Fal 호출, 이미지·영상 생성, scene42 재개, 8장 파일럿, 원격 push 및 Git 이력 정리는 하지 않았다.

## 2. 선행 red 명세

파일: `backend/fastapi-workers/tests/test_verified_fact_value_exact_regression.py`

| 오버레이 요청값 | 원본 `figure` | 원본 `fact` | 기대 | `1c4e071` |
|---|---|---|---|---|
| `4배` | `14배` | `PER 14배` | 거절 | 잘못 허용, 테스트 실패 |
| `143조` | `143조 5000억 원` | `기업의 영업이익은 143조 5000억 원이다.` | 거절 | 잘못 허용, 테스트 실패 |

두 사례는 실제 Job 이미지나 OCR 결과가 아니다. 합성한 scene 객체를 실제 `facts_from_verified_scene()`에 넣어 **상류 어댑터 로직만** 재현했다. 픽셀·OCR·공급자 응답은 관여하지 않는다.

원문 증거: [최초 red](evidence/wo_img_01_b_fact_value_20260827/red.xml), [`1c4e071` 격리 red](evidence/wo_img_01_b_fact_value_20260827/committed-red.xml).

## 3. 원인과 계층 관계

수정 전 검사는 다음이었다.

```python
evidence = " ".join(str(fact.get(key) or "") for key in ("figure", "fact"))
if not value.strip() or _normalise(value) not in _normalise(evidence):
    raise ValueError(...)
```

`_normalise`는 공백을 제거하고 대소문자를 접었다. 그러므로 `4배 in PER14배`, `143조 in 143조5000억원`이 참이었다. 이 값이 승인되면 Pillow와 최종 OCR 정확 대조가 모두 정확히 작동해도 틀린 승인값을 그대로 통과시킨다.

또한 자동 오버레이 생성기의 장면 로컬 선택도 `value in narration` 방식이었다. 원본 사실 자체는 올바른 `PER 4배`여도 현재 장면이 `PER 14배`만 말할 때 `4배` 사실이 장면에 잘못 붙을 수 있었다. 최종 어댑터만 고치면 해당 오버레이가 뒤에서 거절되지만, 생성 단계와 검증 단계가 다른 계약을 쓰는 구조가 남는다. 이번에는 두 단계가 같은 공용 계약을 소비하도록 했다.

해당 검사식의 Git 기록은 `26729da`, **2026-08-02 03:09:52 +09:00**까지 거슬러 올라간다. 이는 저장소에 기록된 도입 시점이다. Job52의 실행일보다 앞선 코드이지만, Job52가 이 함수와 `v5_verified_overlays` 경로를 실제로 사용했다는 뜻은 아니다. 현재 보존된 48개 scene 계약 입력에는 `v5_verified_overlays`가 **0개**이므로, 이번 증거만으로 Job52 실제 피해를 판정하지 않는다.

## 4. 수정된 계약

공용 모듈: `backend/fastapi-workers/app/v5/overlay/fact_value_contract.py`

### 4.1 근거 토큰

`figure`와 `fact`에서 경계가 닫힌 다음 값을 추출한다.

- 부호·쉼표·소수점이 보존된 수치
- `%`, `%p`, `bp/bps`, `pt/포인트`, `배`
- `조 5000억 원` 같은 복합 금액과 원·달러·엔·유로
- 년·월·일·분기·단계·개·명
- `YYYY-MM-DD`, `YYYY.MM.DD`, `YYYY/MM/DD` 날짜

비교 시 공백류만 제거한다. 부호, 숫자, 소수점, 쉼표, 단위, 날짜 구성요소를 고치거나 추정하지 않는다.

예시:

| 근거 | 요청 | 결과 |
|---|---|---|
| `PER 14배` | `4배` | 거절 |
| `영업이익 143조 5000억 원` | `143조` | 거절 |
| `하락률 -4%` | `4%` | 거절 |
| `상승률 14.1%` | `4.1%` | 거절 |
| `관세율 15%` | `15` | 거절 |
| `기준일 2026-08-20` | `2026-08-2` | 거절 |
| `PER 4배` | `4배` | 허용 |
| `영업이익 143조 5000억 원` | `143조 5000억 원` | 허용 |
| `2.50% → 2.75% (+0.25%p)` | `+0.25%p` | 허용 |

### 4.2 구조화 값과 단위 분리 호환

기존 자동 계약에는 `value="2,650"`, `unit="pt"`, `figure="2,650pt"` 또는 `fact="코스피 2,650 포인트 기록"`처럼 값과 단위가 나뉜 형식이 있다. 구조화 `value`가 요청값과 정확히 같을 때만 제한된 단일 단위 접미사(`pt/포인트`, `%`, 원, 배 등)를 근거 토큰에 결합해 허용한다.

이는 임의 substring 허용이 아니다. 구조화 값 `2,65`는 `2,650pt`를 통과하지 못하고, `143`은 복합 단위 `143조 5000억 원`을 통과하지 못한다. 다만 이 호환 규칙은 구조화 `verified_facts.value`를 신뢰하는 계약이다. 이 필드 자체의 생성·팩트체크 계보는 이번 모듈이 검증하지 않는다.

### 4.3 소비자 통합

- `runtime_contract._build_v5_verified_overlays`: 현재 장면 내레이션/승인 화면 문구에 완전값이 있어야 오버레이 후보로 선택한다.
- `diegetic_fact_overlay.facts_from_verified_scene`: 선택된 `source_ref`의 `figure/fact` 완전값과 다시 대조한다.
- `upward_trend`: 대표값뿐 아니라 시작값·종료값도 완전한 독립 토큰이어야 한다.

따라서 생성기와 최종 렌더 어댑터 사이에 검사 기준이 갈라지지 않는다.

## 5. 검증

| 실행 | 결과 | 증거 |
|---|---|---|
| 수정 전 작업 사본 | 2 failed | [red.xml](evidence/wo_img_01_b_fact_value_20260827/red.xml) |
| `1c4e071`만 격리 추출 | 2 failed | [committed-red.xml](evidence/wo_img_01_b_fact_value_20260827/committed-red.xml) |
| 관련 기존+신규 집중 검사 | 75 passed | [green-focused.xml](evidence/wo_img_01_b_fact_value_20260827/green-focused.xml) |
| `ef57daa`만 격리 추출 | 24 passed | [committed-green.xml](evidence/wo_img_01_b_fact_value_20260827/committed-green.xml) |
| 소켓 차단 전체 검사 | 1000 passed, 1 deselected | [offline.xml](evidence/wo_img_01_b_fact_value_20260827/offline.xml) |

격리 검사는 각 커밋의 `app/`과 해당 새 테스트만 `git archive`로 `/tmp/fact_red_commit_verify.83VRa9/`, `/tmp/fact_green_commit_verify.NJG1ji/`에 풀어 수행했다. 기존 미커밋 변경이나 미추적 `tests/conftest.py`에 의존하지 않는다.

집중 검사 범위:

- 두 선행 절단 사례
- 부호·소수점·퍼센트·날짜·단위·복합 금액 경계
- 구조화 값과 `pt/포인트` 호환
- 추세선 시작·종료값 절단
- 유효한 `4배` 사실이 `14배` 장면으로 붙는 장면 로컬 오연결
- 기존 diegetic 렌더, primary surface, 자동 오버레이 계약

Google RSS 테스트는 외부 연결 자체가 테스트 내용이라 소켓 차단 검증에서 제외했다. 이번 코드와 관련 없는 실패를 수정하거나 성공으로 계산하지 않았다.

## 6. 불변 확인

| 대상 | SHA-256 |
|---|---|
| 공용 완전값 계약 | `514cf8103b41ede0b70f4f60c111963928479a6d9f2e48603f62a9acaf901259` |
| 최종 표면 어댑터 | `a77eab483d683a816ea60224ece4386d44a4f317e10ab1fd35fb66d313f2a1f2` |
| 자동 오버레이 생성 계약 | `4de782e91d34e1e6c9d283aff08ecf4347443032b5a8463e2e74a44e0e0f91b1` |
| 선행 red 테스트 | `448b03d21c400df8cbb7fa33d7f1cbceb285d3518abbf102106402a3c55295c4` |
| 추가 경계 테스트 | `38ebf533409af398c855a58345880b7711b2598f9f7b44e9b00d466f69a370bc` |
| 동결 scene42 요청 원장 | `f9f016644e9f4288bd3f754d2d9caeea3a5a6e00c26f1cec6b5f6af9aea9daa3` |
| 48개 원본 scene 계약 | `72dd95c1f577acca6793d850567d045c28c7a0e5cd05f3229d9d105c8dc8cdf6` |

scene42에는 새 요청을 추가하지 않았다. 원장 파일 해시도 이전 체크포인트와 동일하다.

## 7. 한계와 다음 체크포인트

1. 이 게이트는 `verified_facts` 객체 안의 `figure/fact/value/unit`이 앞선 팩트체크에서 올바르게 확정됐다는 전제를 가진다. 서로 모순된 필드의 원 출처 기사까지 다시 조회하지 않는다.
2. 지원 목록에 없는 새 금융 단위는 부분 문자열로 우회하지 않고 거절될 수 있다. 허용 단위를 추가할 때는 실패 테스트와 출처 필드 계약을 먼저 추가해야 한다.
3. 보존된 48개 입력에는 오버레이가 0개라 실제 Job 이미지의 개선을 입증하지 않는다. 이번 결과는 순수 계약·렌더 전 검증이다.
4. 7절 최종 OCR 정확 대조와 이번 상류 사실값 대조는 모두 구현됐지만, 이전 준비 감사에서 남은 **정보성/장식성 라우팅, 표면 계획, 실제 OCR 가독성 검증**은 아직 완료되지 않았다.
5. 따라서 8장 유료 파일럿은 아직 실행하지 않는다. 다음은 표면별 문자열 위치와 추세선 시작·종료값을 최종 OCR 게이트에 연결하는 WO-IMG-01-C 오프라인 검증이다.

Fal 정책은 변경하지 않았다. 문자·숫자 표면은 고정하고 캐릭터·사물·조명·배경의 안전한 동작만 허용한다는 기존 방향을 유지한다.

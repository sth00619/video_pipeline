# 대본 하우스 스타일 이식 및 레퍼런스 비교 하니스 구현 리포트

## 범위와 결론

- 구현 대상은 `claude-sonnet-4-6`만 사용하는 대본 생성·수사 장치 보강·8축 분석·수동 확정 하드 게이트다.
- 특정 채널의 문장, 시그니처 문구, 문체를 복제하지 않는다. 재사용 가능한 편집 장치와 집계 지표만 사용한다.
- 외부 채널의 권리 확인 원문이 아직 제공되지 않아 실제 레퍼런스 p10/p50/p90 밴드는 산출하지 않았다. `corpus/reference_baseline.json`은 이를 명시한 빈 템플릿이다.

## 사전 확인 근거

작업 전 실제 코드에서 아래 시그니처를 확인했다.

| 파일 | 확인한 시그니처·경로 | 적용 지점 |
| --- | --- | --- |
| `backend/fastapi-workers/app/utils/script_style.py` | `get_script_style_guide(profile)`, `assess_storytelling(sections, script)` | `format_name`, `house_style_enabled`를 확장했다. |
| `backend/fastapi-workers/app/workers/script_worker.py` | `ScriptWorker.generate(...)`, `_generate_with_verified_facts(...)`, `_call_llm_with_fallback(...)` | P1/P2/P3 플래그와 최종 하우스 스타일 검증을 연결했다. |
| `backend/fastapi-workers/app/utils/quality_gate.py` | 기존 씬·자막·이미지 결정론 게이트 | `assess_script_house_style(...)`를 추가했다. |
| `backend/spring-app/src/main/java/com/pipeline/video/service/ScriptService.java` | `confirm(Long, String, List<Map<String,Object>>, String)` | 저장·승인 직전에 FastAPI 하드 게이트를 호출한다. |

## 구현 구성

### 하우스 스타일과 생성 경로

`backend/fastapi-workers/app/utils/script_style.py`의 `HOUSE_STYLE_V1`은 반말 2인칭, D1~D8 편집 장치, 포맷별 필수 장치, 금칙 투자 지시·과장 표현을 선언한다. `SCRIPT_HOUSE_STYLE_ENABLED=false`가 기본값이므로 기존 작업은 변하지 않는다.

`backend/fastapi-workers/app/workers/script_worker.py`는 Claude 고정 호출만 사용한다. P2(비유 보강)와 P3(가짜 독자 질문 보강)는 각 플래그가 켜졌을 때만 최대 한 번의 Claude 호출로 실행하며, 검증 사실·숫자·날짜·회사명·인과관계의 변경을 금지한다. P1 숫자 추적은 최종 결정론 게이트에서 검증 사실과 대본 숫자를 대조한다.

| 런타임 키 | 기본값 | 역할 |
| --- | ---: | --- |
| `script_house_style_enabled` | `false` | 하우스 스타일·확정 게이트 전체 활성화 |
| `script_pattern_numbers_enabled` | `false` | 숫자 추적 하드 실패 활성화 |
| `script_pattern_analogy_enabled` | `false` | P2 비유 보강 |
| `script_pattern_fake_question_enabled` | `false` | P3 가짜 독자 질문 보강 |
| `script_pattern_llm_labeling_enabled` | `false` | 분석 어드바이저리용 Claude 라벨 보강 |

키는 `POST /pipeline/config`으로 다음 작업부터 변경한다. 예: `{"script_house_style_enabled": true, "script_pattern_numbers_enabled": true}`.

### 8축 분석과 하드 게이트

`backend/fastapi-workers/app/utils/script_pattern_analyzer.py`가 아래 지표를 결정론적으로 산출한다. 선택적 Claude 라벨은 비유·질문 같은 어드바이저리 보강에만 쓰며, 통과/실패 판정에는 의존하지 않는다. 라벨 결과는 해시 기반 로컬 캐시에 저장한다.

1. D1~D8 장치·순서
2. 가짜 독자 질문, 비유, 공포 재해석, 체크포인트
3. 문장 길이, 짧은 강조문, 종결 다양성, 접속어, 연속 종결
4. 반말 비율, 2인칭, 스테이크 프레이밍
5. 추상 개념의 비유 커버리지
6. 첫 3초 숫자 훅·질문·대조
7. 매수/매도 지시, 과장, 권리 검수 시그니처, n-gram 유사도
8. 숫자 총수·검증 사실 추적 가능 수·미추적 목록

`assess_script_house_style(...)`의 하드 실패는 투자 지시/과장/금칙 표현, 참조 n-gram 유사도 0.15 이상, 활성화된 숫자 미추적, 숫자-우선 훅 부재, 동일 종결 3회 초과, 반말 비율 0.90 미만이다. D3/D4/D5 부족은 개선 권고로 반환한다.

수동 편집 대본도 `POST /workers/script/quality-gate`를 거친다. `ScriptService.confirm(...)`은 응답의 `passed=false`면 저장과 게이트 승인을 중단하고 실패 코드만 전달한다. 승인된 에셋 메타데이터에는 `house_style_gate` 결과가 남는다.

### 레퍼런스 코퍼스와 비교 CLI

- 입력: `corpus/reference_scripts.jsonl`
- 집계: `python -m app.tools.build_reference_baseline --reference corpus/reference_scripts.jsonl --output corpus/reference_baseline.json`
- 비교: `python -m app.tools.compare_scripts --reference <jsonl> --generated <json> --format shorts|longform --report <md> --json <json>`

레코드는 `source_id`, `channel`, `rights_basis`, `format`, `register`, `transcript`를 가져야 한다. `benchmark_stock`만 반말·2인칭 타깃 밴드에 사용하며, `general_econ`은 비유·리듬 지표에만 사용한다. 비교 리포트에는 원문을 인용하지 않고 p10/p50/p90, 생성값, 밴드 적합 여부, 격차, 조치와 안전 결과만 출력한다.

## 검증 결과

| 검증 | 결과 |
| --- | --- |
| `python -m pytest tests/test_script_pattern_analyzer.py tests/test_script_worker_safety.py -q` | 12 passed |
| Python 문법 검사 | 통과 |
| `backend/spring-app/gradlew.bat compileJava` | BUILD SUCCESSFUL |
| CLI 샘플 | 하드 게이트 통과, 밴드 적합 2/6 |

CLI 샘플은 권리 확인 외부 원문이 아닌 합성 테스트 픽스처이며, 결과는 `artifacts/script_pattern_harness_fixture_report.md`와 JSON에 저장했다. 실제 코퍼스 밴드로 해석하면 안 된다.

## 비용·안전 경계

- 이미지·영상 생성 호출은 추가하지 않았다.
- 기본 플래그는 모두 꺼져 있어 추가 LLM 비용은 없다.
- 활성화 시 P2와 P3은 각각 최대 한 번의 Claude 호출만 추가한다. 분석 라벨도 선택적 1회이며 캐시 재사용한다.
- 금전 수치 생성은 허용하지 않는다. 숫자는 검증 사실에 있는 값만 통과할 수 있다.
- 매수·매도·보유 지시, 수익 보장, 외부 채널 문장·시그니처 모방은 차단한다.

# WO-IMG-01 정확 대조 게이트 — 테스트 선행 커밋과 오프라인 검증

## 1. 결론과 범위

문서 4절 B의 5개 사례를 **수정 코드보다 먼저 테스트만 커밋**했다. 커밋은 `24dd526`이며, 당시 결과는 **2 failed / 3 passed**였다. 이후 최종 프레임의 부분 문자열 검사를 정확 일치 검사로 교체했다. 같은 5개 명세를 변경하지 않고 모두 통과했다.

이번 단계는 **정확 대조 함수와 그 함수의 표면·재독 경계**에 한정한다. 통합 의미 계약 전체, 실제 OCR 정확도, 실제 생성 이미지 품질, WO-IMG-01 완료를 선언하지 않는다. 아래 8절의 상류 사실값 대조 결함도 남아 있다.

- 유료 API 호출 0회. Gemini/Claude/TTS/Fal 호출 및 영상 생성 없음.
- scene42는 `needs_review`, 누적 시도 2, 실패 수 2 상태 유지.
- 운영 `/app/app` 소스 교체, 서비스 재시작, 모델/프롬프트/그림체/목소리 변경 없음.
- 원격 push, force-push, 브랜치 삭제, Git 히스토리 정리 없음.
- 수정은 작업 트리와 별도 Docker 검증 사본에 적용했다. 운영 반영 완료가 아니다.

## 2. 먼저 커밋한 회귀 명세

파일: `backend/fastapi-workers/tests/test_final_frame_text_exact_regression.py`

| 승인 문자열 | 주입 OCR 행 | 기대 결과 | 수정 전 판정 | 수정 후 판정 |
|---|---|---|---|---|
| `4배` | `14배` | 거절 | 잘못 허용 → 테스트 실패 | 거절 |
| `영업이익` | `비영업이익` | 거절 | 잘못 허용 → 테스트 실패 | 거절 |
| `PER` | `per` | 거절 | 거절 → 테스트 통과 | 거절 |
| `현재 전망` | `현력 토공` | 거절 | 거절 → 테스트 통과 | 거절 |
| `143조 원` | `143조\n원` | 허용 | 허용 → 테스트 통과 | 허용 |

5개 모두를 일부러 실패시키지 않았다. 이미 올바르게 동작하던 거절 2개와 공백 허용 1개는 보존해야 할 대조군이다. 각 사례는 보고 함수와 예외를 발생시키는 `require_final_frame_text_integrity`를 함께 검증한다.

**재현의 성격:** OCR 엔진에 이미지를 넣은 실험이 아니다. `ocr_rows=[{"text": ..., "conf": "99"}]`를 실제 대조 함수에 주입했다. 이미지 파일은 존재하지 않고, 픽셀 계보 예외도 사용할 수 없다. 따라서 증명한 것은 **대조 로직 결함과 그 수정**이지, 실제 Gemini 산출물이나 실제 OCR 엔진의 오류율이 아니다.

증거: [수정 전 JUnit 원문](evidence/ocr_exact_gate_20260827/red.xml), [수정 후 집중 검사 JUnit 원문](evidence/ocr_exact_gate_20260827/green-focused.xml).

## 3. 정확한 원인과 기록된 도입 시점

대상: `backend/fastapi-workers/app/services/final_frame_text_integrity.py`.

수정 전 핵심 코드는 다음과 같다.

```python
joined = _normalise(" ".join(recognized))
missing = [text for text in expected if _normalise(text) not in joined]
```

`_normalise`는 공백류만 제거한다. 최종 프레임의 이 함수에서 확인된 연산은 **예정 문구가 OCR 전체 문자열에 포함되는가**라는 단방향 부분 문자열 검사다. 편집거리·유사도 임계값이 아니다. `4배 in 14배`, `영업이익 in 비영업이익`이 모두 참이므로 잘못 통과했다. 다른 텍스트 검사 함수의 양방향 포함 검사와 혼동하지 않는다.

추가로, 이전 판독 함수는 여러 표면과 PSM 6/11/13의 결과 행을 하나로 합쳤다. 한 표면의 일부 글자와 다른 판독의 일부 글자를 조합해 승인 문자열이 있는 것처럼 만들 수 있는 구조였다.

`git log --follow` 및 해당 검사식의 `git log -S`에서 확인되는 최초 기록은 **`6fa5e79`, 2026-08-26 04:58:34 +09:00**이다. 이는 Git에 기록된 시점이다. 커밋 전 작업 트리 수정 시각, 서버 배포 시각, Job52/54 실행 당시 이 함수가 호출됐는지는 이 기록만으로 알 수 없다.

**Job52/54 피해 범위:** 이번에는 두 작업의 원본 프레임·당시 OCR 행·당시 최종 게이트 보고서를 연결해 재감사하지 않았다. 따라서 “두 작업에서 실제 4배/14배 오류가 승인됐다”는 결론은 내리지 않는다. 해당 연결 증거는 별도 확인 대상이다.

## 4. 구현과 변경 경계

현재 소스 기준 주요 위치:

- 25행 `_normalise`: 공백·줄바꿈만 제거. 대소문자, 부호, 소수점, 쉼표, 단위, 유사한 유니코드 글자를 보정하지 않음.
- 54행: 기대 문자열의 중복을 제거하지 않음. 실제로 두 번 써야 할 문구가 한 번만 있는 경우 거절.
- 95행 이후: **표면별·판독별**로 순서를 유지한 전체 문자열을 `==`로 비교.
- 110행: 표면 안의 모든 판독이 정확히 일치해야 `ocr_passed`가 참. 일부가 일치해도 다른 판독이 상충·누락·시간초과이면 OCR 합격 아님.
- 127행: `verification_method`로 `ocr_exact`, `deterministic_pixel_provenance`, `none`을 구분.
- 131행: `ocr_source`로 주입 행과 실제 Tesseract 경로를 구분.
- 187행 이후: 오버레이별 anchor와 해당 label/value를 연결해 별도 crop으로 읽음. 표면 A와 B의 값이 바뀌어도 전체 단어 집합만 맞으면 통과하던 방식을 사용하지 않음.

예를 들어 PSM 6이 `영업이익`, PSM 11이 `4배`만 읽으면 둘을 합쳐 `영업이익 4배`로 합격시키지 않는다. PSM 6이 `4배`, PSM 11이 `14배`를 읽으면 유리한 판독 하나만 선택하지 않는다.

### 보수적 거절이 늘어날 수 있는 부분

정확한 이미지에서도 OCR이 잘못 읽으면 거절이 늘 수 있다. 특히 PSM 13의 단일 행 해석과 여러 줄 표면은 잘 맞지 않을 수 있다. 이번 검사는 상충하는 판독을 성공으로 숨기지 않는 안전 기준이다. 실제 판독률을 높였다고 주장하지 않으며, 후속 표면 계약에서 행/셀별 영역과 적절한 판독 모드를 검증해야 한다. 실패를 이유로 공급자 재생성을 무제한 반복해서는 안 된다.

현재 경로가 이해하지 못하는 복합 추세선(`upward_trend`)은 `unsupported_surface_layout`으로 거절한다. 렌더러나 추세선 표현을 없앤 것은 아니지만, **이 게이트를 사용하는 추세선 장면은 시작값·종료값의 위치 계약이 보완되기 전까지 통과하지 못한다.** 라벨·대표값만 확인해 시작/종료값까지 검증했다고 보고하는 것을 피한 제한이며, 3단계의 명시적 해결 항목이다.

여러 캡션 영역에 문자열이 어떻게 배분되는지 계약이 없는 경우는 `ambiguous_surface_contract`로 거절한다. 잘못된 좌표·누락된 anchor도 통과시키지 않는다. 좌표 없는 단일 캡션의 기존 전체 프레임 읽기 경로는 남아 있지만, 모든 읽힌 문자열이 정확히 일치해야 한다. 이것이 표면 계획 검증을 대신하지는 않는다.

## 5. 픽셀 계보 예외의 유지와 한계

기존 단일 결정론 캡션의 예외는 유지했다. 예정 문자열 SHA-256과 렌더 직후 영역 픽셀 SHA-256이 현재 이미지와 일치하고, 기존 최소 글자 크기 24px 조건을 충족하면 OCR 오판을 보완한다. **24px은 기존 조건이며, 장식성 Gemini 문구의 새 허용 임계값으로 승인한 수치가 아니다.**

이번에는 여러 영역 중 하나의 해시만 맞는 것으로 전체를 승인하지 않도록 범위를 제한했다. 검증 수치 오버레이에 별도의 일반 캡션 해시를 가져와 승인하는 것도 허용하지 않는다.

예외 통과 시 `passed=true`일 수 있지만 `ocr_passed=false`, `verification_method=deterministic_pixel_provenance`로 명확히 남는다. 이를 “OCR 정확 대조 통과”라고 보고하면 안 된다. 픽셀 해시는 **신뢰한 렌더러가 기록한 영역이 바뀌지 않았음**의 증거이지, 글꼴의 가독성·원본 사실의 정확성·화면 전체의 무오류 증거가 아니다. 이번에 그 신뢰 경계를 확대하지 않았다.

## 6. 검증 결과와 재실행

운영 소스가 아닌 `pipeline_fastapi:/tmp/wo_request_verify.vm7YND/backend/fastapi-workers` 사본에서 실행했다. 수정 파일의 작업 트리와 사본 SHA-256을 대조했다.

| 실행 | 결과 | 증거 |
|---|---|---|
| 수정 전 5개 명세 | 2 실패, 3 통과 | [red.xml](evidence/ocr_exact_gate_20260827/red.xml) |
| 수정 후 집중 검사 | 37 통과 | [green-focused.xml](evidence/ocr_exact_gate_20260827/green-focused.xml) |
| 전체 검사, 소켓 접속 차단 | 976 통과, 1 실패 | [full-network-blocked.xml](evidence/ocr_exact_gate_20260827/full-network-blocked.xml) |
| 동일 검사, RSS 외부접속 테스트 1개 제외 | 976 통과, 1 제외 | [offline.xml](evidence/ocr_exact_gate_20260827/offline.xml) |

최초 전체 검사의 실패는 `test_article_discovery_rss.py::TestArticleDiscoveryGoogleRssFallback::test_google_rss_fallback_when_naver_not_configured`가 실제 Google RSS 연결을 시도해 소켓 차단에 걸린 것이다. 그 테스트나 서비스는 이번에 수정하지 않았다. **전체 무조건 통과라고 보고하지 않는다.**

집중 검사는 5개 선행 명세 + 23개 경계 검사 + 기존 9개 검사다. 경계 검사는 숫자 접미어·부호·소수점·단위·쉼표·유사 글자·누락·중복·재독 혼합·재독 상충·표면 뒤바뀜·좌표 오류·판독 시간초과·다중 영역 해시 예외를 다룬다. 기존 검사의 Pillow 캡션 렌더 및 픽셀 변조 검증도 통과했다. 새 경계 검사의 OCR 반환도 mock이며 실제 OCR 엔진 정확도 실험이 아니다.

작업자용 집중 재실행 명령(의존성과 필수 환경이 마련된 worker 디렉터리에서):

```sh
python -m pytest -q tests/test_final_frame_text_exact_regression.py tests/test_final_frame_text_exact_boundaries.py tests/test_final_frame_text_integrity.py
```

선행 커밋의 테스트 파일과 수정 전 함수는 다음 명령으로 독립 확인할 수 있다.

```sh
git show --stat 24dd526
git show 24dd526:backend/fastapi-workers/tests/test_final_frame_text_exact_regression.py
git show 24dd526:backend/fastapi-workers/app/services/final_frame_text_integrity.py
```

기존 CI가 `tests/`를 수집하면 새 회귀도 포함된다. 이번에는 CI 워크플로를 바꾸거나 원격 CI를 실행하지 않았다. 전체 사본 검사는 기존 미커밋 요청 제어 변경도 포함한 작업 트리 검증이며, 그 변경들을 이번 커밋에 섞지 않았다.

## 7. 입력·운영 상태의 불변 확인

[수정 후 오프라인 감사 원문](evidence/ocr_exact_gate_20260827/postfix-readiness.json)은 48개 내레이션 해시 불변, 원본 파일 불변, 다섯 최종 OCR 명세 모두 기대 일치를 기록한다. 이전 준비 감사 증거는 덮어쓰지 않았다.

| 항목 | SHA-256 |
|---|---|
| 수정 전 게이트(`24dd526`) | `06f733c151a59714abe64c15e049df995a95c3cf26fb3c8aee006e2a71801945` |
| 수정 후 게이트(작업 트리 = 검증 사본) | `73922f32610c52a6dbb963fd5e02e903e7bbd06ba0a2a5d4f12a75e78c11e244` |
| 선행 5개 테스트(커밋 후 변경 없음) | `a4028c0bf211829f2ef5bb3be87a99fde5469837de603e5fd2c02852864866e8` |
| 추가 23개 경계 테스트 | `132fdda8f9ffadd056dc9672bb4f97a5548e1139c34cda1704957014f7f8a0c3` |
| 48개 원본 scene 계약 | `72dd95c1f577acca6793d850567d045c28c7a0e5cd05f3229d9d105c8dc8cdf6` |
| 동결 scene42 요청 원장 | `f9f016644e9f4288bd3f754d2d9caeea3a5a6e00c26f1cec6b5f6af9aea9daa3` |

운영 SQLite는 `mode=ro`로 조회했다. `scene:42`, `count=2`, `n=2`, `next=1787762034.2775416`, `active=null`, `status=needs_review`이다. 기존 원장 해시와 동일하며 새 시도·새 usageMetadata는 없다. 예약/청구 추정도 변경하지 않았다.

## 8. 다음 단계에서 반드시 막아야 할 별도 결함

상류의 `app/v5/overlay/diegetic_fact_overlay.py::facts_from_verified_scene`는 여전히 다음 형태로 원본 사실과 오버레이 값을 검사한다.

```python
if not value.strip() or _normalise(value) not in _normalise(evidence):
    raise ValueError(...)
```

이번에 합성 입력으로 실제 함수를 호출하니, `verified_facts[0] = {"figure": "14배", "fact": "PER 14배"}`와 `value="4배"`, 유효한 `source_ref="facts[0]"` 및 monitor anchor 조합이 **허용되어 `4배`를 반환했다.** 이미지나 OCR을 생성한 실험도, 실제 Job52/54 데이터에서 발견한 사건도 아니다.

즉 **틀린 계약의 4배를 정확히 그리면 최종 OCR 정확 대조는 통과할 수 있다.** 이번 수정으로 상류 사실값 검증까지 안전해졌다고 주장하지 않는다. 이 상류 검사는 통합 의미 계약 단계에서 수치 토큰·단위·부호·출처 span을 함께 연결하는 회귀 테스트부터 보완해야 한다. 이 결함을 해결하기 전에 유료 파일럿으로 넘어가지 않는다.

재현 입력은 아래와 같다. 유료 호출 없이 함수만 검사한다.

```python
from app.v5.overlay.diegetic_fact_overlay import facts_from_verified_scene
scene = {
    "verified_facts": [{"figure": "14배", "fact": "PER 14배"}],
    "v5_verified_overlays": [{
        "label": "PER", "value": "4배", "source_ref": "facts[0]",
        "anchor": {"x": .1, "y": .1, "width": .5, "height": .3, "kind": "monitor"},
    }],
}
print(facts_from_verified_scene(scene)[0].value)  # 현재 관측: 4배. 거절해야 할 별도 결함.
```

## 9. 다음 체크포인트

1. **이번 단계:** 최종 정확 대조의 5개 회귀 + 표면/재독 경계 수정 완료, 오프라인 검증 완료. 운영 배포 아님.
2. **통합 의미 계약:** 위 상류 부분 문자열 결함부터 수정. 정보성/장식성 라우팅, 원문 출처, caption/texts/실제 렌더 입력의 동일성을 묶기. 원래 대본·TTS 원문은 바꾸지 않기.
3. **표면 검증:** 행/셀별 문자열 위치, 추세선의 시작·종료값, 다중 영역, 가독성과 실제 OCR 검증 연결. 픽셀 해시의 보장 범위를 과장하지 않기.
4. **8장 명세:** 기존 후보 00·01·05·07·15·26·35·47을 검토 대상으로 유지. scene42 동결을 새 키로 우회하지 않기. 비용과 계보가 검증된 실행 명세 승인 후에만 유료 실행.

수정 후 감사에서도 정보성 문구의 라우팅은 미완료(생성 문자열을 가진 장면 19, 결정론 문자열을 가진 장면 14), 도출 문구가 빈 장면 21, 표면 계획이 있는 장면 0이다. 이 수치는 재생성 결과가 아니라 과거 48개 계약에 현재 계획 함수를 적용한 오프라인 결과다. 전체 WO-IMG-01 및 8장 파일럿 준비 완료로 해석하지 않는다.

Fal의 고정 카메라·고정 문자 표면·사물/배경/캐릭터만 동작 원칙은 변경하지 않았으며 이번에는 Fal 관련 코드를 수정하거나 실행하지 않았다.

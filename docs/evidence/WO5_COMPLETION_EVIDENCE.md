# WO-5 완료 증거 묶음

이 디렉터리는 로컬 `C:\tmp` 경로에만 있던 WO-5 검증 자료를 저장소에서 직접 감사할 수 있도록 보존한다.

## 커밋 계보

| 구분 | 커밋 | 내용 |
|---|---|---|
| WO-5 직전 선행 변경 | `1ebe9ac` | Windows 폰트 경로, ASS 필터의 Windows 드라이브 콜론 이스케이프, Shorts 세로 영상 blur-background/fit-content, Edge TTS 폴백 |
| Phase 1 | `509ac16` | `images_worker.py` narration 키 폴백 3곳 |
| Phase 2 | `32ac8eb` | TTS 속도·문장 쉼·문단 쉼 기본값 통일 |
| Phase 3 | `63fbe5b` | eligible Fal 자동 선택, 실제 롱폼 게이트 보정, 감정→모션 매핑 |
| Phase 4 | `c38b5bf` | 기존 4-튜플 호환성을 유지한 결정론적 포즈 순환 |
| Phase 5 | `b35a1d7` | V5 엔티티 영문 grounding 및 이름·로고 렌더링 금지 |
| Phase 6 | `d5e2026` | Shorts hover 글자색 수정 |

## 원본 증거 파일

| 파일 | 내용 | 줄 수 | SHA-256 |
|---|---|---:|---|
| `WO5_full_pytest_log.txt` | `python -m pytest tests/ -q --tb=short` 전체 출력 | 110 | `0510c0ac7f48c1efd15d0ce8f9332c1c85d53752b9b4fd64d960771dfd0e1df1` |
| `WO5_commits_1ebe9ac_to_d5e2026.diff` | WO-5 Phase 1~6 전체 실제 diff | 241 | `cec373dc55b48ab38ce90f0d1a2c623fc39f807e1fa3e7c66a1c8adcadc6c7bf` |
| `PRE_WO5_commit_e3b989a_to_1ebe9ac.diff` | 완료 보고에서 누락됐던 선행 커밋 전체 diff | 96 | `3bd4bbc1353a8301f75a84a9355cc068f8f15ad2cfb135d14a2236190324376f` |

`WO5_full_pytest_log.txt`는 PowerShell `Tee-Object`가 만든 UTF-16 원본을 저장소용 UTF-8로 변환했다. 원본과 저장소 파일을 줄 단위로 비교한 결과는 `110/110줄`, 차이 `0줄`이다.

## 전체 회귀 결과

```text
13 failed, 510 passed, 13 warnings in 123.85s (0:02:03)
```

실패 13건은 로그에 traceback과 함께 전부 보존했다.

- 검색 공급자 구성 기대 불일치: 1건
- 60초 영상 Fal 최대 클립 수 구현(3)과 테스트 기대(4) 불일치: 1건
- TTS 기본값 기대 불일치: 2건
  - Phase 2가 의도적으로 변경한 문장 쉼 `200 → 350ms`: 1건
  - WO-5 이전부터 존재한 thought-group `110ms`와 테스트 `70ms` 불일치: 1건
- info-surface compositor 상태/플래그 기대 불일치: 6건
- provider request audit 원장 기대 불일치: 2건
- 오래된 이미지 grounding 프롬프트 문구 기대 불일치: 1건

WO-5 직접 검증은 별도로 다음과 같이 통과했다.

- V5 핵심 테스트: 33/33
- Kling/motion: 44/45, 실패 1건은 WO-5가 수정하지 않은 기존 3↔4클립 불일치
- Phase 3 숫자 장면 `ambient_context` 보호: 통과
- Phase 4 V5/archetype 회귀: 18/18
- Phase 5 V5 런타임 회귀: 13/13
- 프론트엔드 Vite 프로덕션 빌드: 성공, 2,273개 모듈 변환

## 재검증 명령

```powershell
git diff --check 1ebe9ac..d5e2026
git diff --stat 1ebe9ac..d5e2026
git diff e3b989a..1ebe9ac

Set-Location backend/fastapi-workers
python -m pytest tests/ -q --tb=short

Set-Location ../../frontend
npm run build
```

이번 증거 제출 커밋은 제품 코드를 변경하지 않는다. 사용자가 별도로 수정한 `logs/pipeline-autostart.log`도 포함하거나 변경하지 않는다.

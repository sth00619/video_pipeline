# V3 구현·검증 보고서

기준 문서: `DEV_PLAN_v3_implementation_directive.md`

## 구현 결과

- 기사 강조는 `EmphasisPlan`을 필수 계약으로 사용한다.
- 본문 정책은 `UNDERLINE`, `RECT`, `HIGHLIGHT`, `HIGHLIGHT_UNDERLINE` 중 하나이며 밑줄과 사각형은 동시에 생성되지 않는다.
- 형광펜 multiply 패스 이후 불투명 빨간 선을 그려 색이 갈색으로 섞이지 않는다.
- `RECT`는 실제 `key_phrase_bboxes`만 사용하며 좌표가 없으면 `HIGHLIGHT`로 강등된다.
- 제목 사각형 여백은 실제 로컬 렌더 글자 범위에서 12px이다.
- `ArticleEvidencePlanner`는 승인 대본 문장을 복사한 뒤 메타데이터만 부착하고 전후 SHA-256 불일치를 하드 실패시킨다.
- 기사 후보는 한국어 allowlist, 수치·방향·출처 문장·유사도 게이트를 모두 통과해야 한다.
- 썸네일은 역할 기반 레이어, 3개 변형, copy fill/대비/피사체 면적/얼굴 선명도/겹침 QA를 provenance에 저장한다.
- 마스코트는 높이 26% 이하이고, 좌우 반전 시 말풍선과 워터마크 예약 영역을 분리한다.
- Spring 채널 프로필의 `watermark_path`가 FastAPI 썸네일 요청까지 전달된다.

## 실제 기사 E2E

- 기사: `https://www.yna.co.kr/view/AKR20260722082100008`
- 채택 문장: `한국거래소에 따르면 오전 11시 현재 코스피는 전 거래일 대비 394.50포인트(5.85%) 상승한 7,142.45다.`
- 핵심 구절: `(5.85%) 상승한`
- 문장 유사도: `0.9038`
- 대본 SHA-256: `b367c10d59cdc20233d986e09785c951940dcd78f621217562482988313477cc`
- 감사 로그: `.artifacts/v3_validation/jobs/990077/evidence/evidence_plan.json`

현재 로컬 환경에는 `NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`이 없다. 따라서 실제 URL 경로 검증은 주입형 discovery로 수행했으며, 운영 자동 검색은 두 값을 설정한 뒤 활성화된다. 자격증명이 없거나 기사 검증에 실패하면 기존 카툰/그래프 씬을 그대로 유지한다.

## 테스트

- 로컬 FastAPI: `105 passed, 1 skipped`
- Playwright 포함 Docker FastAPI: `106 passed`
- Spring Java 17 Docker: `4 passed`, `BUILD SUCCESSFUL`
- Spring/워커 Docker 이미지 빌드 성공
- `git diff --check` 통과

Docker Compose의 현재 `TTS_SPEED=1.05`는 기본값 검증 테스트와 충돌하므로 컨테이너 회귀 테스트에서 `TTS_SPEED=1.0`을 명시했다. 이번 구현은 TTS 속도·문장·문장부호·타이밍 코드를 변경하지 않았다.

## 검증 산출물

- 기사 정책 A/B/C/D: `.artifacts/v3_validation/article_policy_*.png`
- 썸네일 3변형: `.artifacts/v3_validation/thumbnail_v3_v1.png` ~ `v3.png`
- 썸네일 QA·선택 근거: `.artifacts/v3_validation/provenance.json`
- 구현·산출물 해시: `.artifacts/v3_validation/sha256_manifest.txt`

주의: 이미지는 빌드·테스트용으로 생성했으며 실행 중인 로컬 컨테이너는 교체하지 않았다.

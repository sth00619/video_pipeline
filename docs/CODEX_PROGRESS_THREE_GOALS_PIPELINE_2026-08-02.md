# Three Goals Pipeline 진행 현황

마지막 갱신: 2026-08-02  
기준 작업지시서: `C:/Users/song/Downloads/CODEX_WORKORDER_THREE_GOALS_PIPELINE_2026-08-02.md`

## 한눈에 보기

| 구간 | 상태 | 진행 |
|---|---|---:|
| WP-0 정책 충돌 제거 | 구현·회귀 테스트 완료, 실 산출물 증빙 대기 | 90% |
| WP-1 비용·오류 게이트 통합 | 구현·회귀 테스트 완료, 통합 산출물 증빙 대기 | 90% |
| WP-2 실제 통합 E2E | Gemini 4장면 파일럿 실행·검토 완료, diagram 재설계 후보는 Gemini 크레딧 충전 대기 | 60% |
| 전체 | **코드 구현과 파일럿 검증 진행, 실제 통합 실행 전** | **약 78%** |

> 작업지시서 원안의 20분 이상 상한 ₩80,000은 이후 `AGENTS.md` 정책 변경에 따라 **₩70,000**으로 적용한다. 20분 미만은 ₩40,000이다.

## 완료된 작업

| 작업 | 상태 | 근거 |
|---|---|---|
| WP-0-A / A-2 정보형 오버레이 | 완료 | OpenCV 카드 합성 생산 경로 제거, Pillow 텍스트 오버레이·수치 프롬프트 차단 테스트 |
| WP-0-B 인트로 Kling 구간 | 완료 | 45초/60초/600초 정책, Docker 환경 변수 전달, 워커 반영 |
| WP-0-C Fal billing 사전조회 | 완료 | 사전 billing 조회 제거, 실제 요청 전 원장 예약만 사용 |
| WP-0-D Pro-only 이미지 | 완료 | `gemini-3-pro-image` 고정, Flash/hybrid 자동 강등 차단 |
| WP-0-E / F verbatim·OCR 게이트 | 완료 | 수치 불일치 hard reject, OCR 추정 사실은 수동 검토 요구 |
| WP-1-A 비용 원장·길이별 상한 | 완료 | FastAPI 원장 요약을 Spring/UI가 조회, 20분 미만 ₩40,000·이상 ₩70,000 |
| WP-1-B / C 패키지·게시 안전성 | 완료 | 실패 에셋 기록, `PUBLISH_PENDING`, mock URL 제거 |
| WP-1-D Kling 프롬프트 | 완료 | 장면의 action/emotion/edit와 negative prompt를 실제 요청에 전달 |
| 길이별 Kling 운영 UI | 완료 | 정책 조회 API, 편집 화면의 동적 선택 범위, 결과/QC/manifest의 모션 계획 기록 |
| WP-2A 이미지 파일럿 준비 | 완료 | 키·예산·한글 폰트 preflight 및 명시적 `--execute` 실행기 |
| WP-2A 이미지 검토·재생성 절차 | 완료 | 장면별 원본/합성 PNG, review dossier, 승인·사유 없는 재생성 차단 |
| WP-2B Kling 파일럿 준비 | 완료 | 비용 없는 preflight, 실제 롱폼 초반 구간 정책 적용 |

## 현재 진행 단계

**WP-2 — Gemini 파일럿 diagram 재생성 대기**

- FastAPI·Spring·프런트엔드 최신 이미지를 빌드·재기동했다.
- FastAPI 건강 상태, Spring 건강 상태, 프런트엔드 응답, Gemini/Kling 사전검증을 확인했다.
- Gemini Pro 4장면 파일럿은 실제로 생성했고, graph·metric·general은 수동 검토 승인했다.
- diagram attempt-04는 사용자 시각 검토에서 반려됐다. 지도·노드 배경 위에 떠 보이는 수치 대신, 중앙 벽면의 결정론적 상승 그래프와 고정 마스코트 참조를 쓰도록 구현을 교체했다.
- 재생성 attempt-05는 Gemini `HTTP 429 RESOURCE_EXHAUSTED`로 생성 전 거절됐다. AI Studio 프로젝트의 선불 크레딧 충전이 필요하다.

## 다음 작업

1. **Gemini 크레딧 충전 후 diagram 재생성**: 같은 입력·승인 사유로 한 장면만 실행하고, 중앙 벽면 상승선·캐릭터 일관성·OCR 보조 상태를 수동 검토한다.
2. **4장면 파일럿 dossier 재승인**: 새 diagram 후보를 포함해 원본/최종 PNG, 비용 원장, 한글 오버레이를 다시 판정한다.
3. **실제 롱폼 1건 통합 실행**: 선택한 길이의 초반 Kling 구간·최종 MP4·썸네일·YouTube 패키지·비용 원장을 같은 job_id로 검수한다.
4. **완료 증빙 정리 및 커밋/푸시**: 실행 로그와 결과 경로를 개발 문서에 기록하고, 검증된 변경만 커밋한다.

## 매 작업 종료 시 보고 형식

앞으로 모든 작업 종료 보고에는 아래 세 줄을 포함한다.

```text
진행률: 전체 NN% · 현재 WP-X
이번 완료: ...
다음 작업: ...
```

## 2026-08-02 파일럿 검수 준비 완료 내역

- 파일럿 실행마다 `run-id`를 분리했다. 원본·최종 PNG, 후보 회차, `cost_ledger.json`, `review_dossier.json`이 서로 섞이지 않는다.
- 재생성은 `REGENERATE`, 구체적 사유, `reviewed_attempt`가 현재 dossier 회차와 일치할 때만 허용한다. 자동 재생성은 없다.
- 원본/최종 PNG의 SHA-256·1920×1080 검증과 Tesseract 한국어·영어 OCR 상태를 dossier에 남긴다. OCR은 자동 승인에 사용하지 않는다.
- FastAPI 실행 이미지에 `tesseract-ocr`, `tesseract-ocr-kor`, `tesseract-ocr-eng`를 포함했고, 컨테이너에서 `kor`, `eng` 언어팩과 FastAPI health를 확인했다.
- 관련 FastAPI 테스트 43건과 프런트엔드 production build를 통과했다. Gemini Pro·Kling 유료 요청은 아직 보내지 않았다.
- 정적 점검에서 이미지 provider/tier는 Gemini/Pro 이외 값에서 시작 단계에 실패한다. `composite_planar`는 호출처가 없는 `_legacy_info_surface_plan` 정의 안에만 남아 있으며, mock YouTube URL은 production 코드에서 발견되지 않았다.

## 2026-08-02 실제 Gemini Pro 파일럿 및 사용자 재검토

- 한국은행 2026-07-16 통화정책방향의 검증 사실로 graph·diagram·metric과 일반 기준 장면을 실제 생성했다.
- graph attempt-01, metric attempt-02, general attempt-01은 승인했다. diagram attempt-04는 사용자 검토에서 반려하고, 고정 마스코트 참조와 중앙 벽면 상승선 방식으로 재설계했다.
- 재설계 후 Gemini 요청 attempt-05는 `HTTP 429 RESOURCE_EXHAUSTED`로 거절됐다. 생성된 새 PNG는 없으며, 크레딧 충전 후 같은 재생성 승인으로 재개한다.
- 성공 요청 8회는 추정 ₩1,504이고, 429 예약 기록 ₩188을 포함한 원장 누적은 ₩1,692이다. 별도 최초 기술 검증 1회(₩188)는 원본 해상도 규칙 보완 전 중단된 이력으로 보존했다.
- PNG 원본·최종본·OCR 보조 상태·SHA-256·재생성 사유·승인 회차는 `artifacts/gemini_pilot/bok-policy-20260716-v2/`에 보존했다.

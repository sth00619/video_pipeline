# WO-IMG-01-G 결과 — scene07 두 변수 격리 canary

- 작성일: 2026-08-28 KST
- 실행 커밋: `83b1d0b`
- attempt: `f53191be75134394af3ad67b3e8d95ea`
- 모델: `gemini-3-pro-image`, Standard, 2K
- 외부 POST: 1회
- 공급자 결과: HTTP 200
- 최종 상태: `pending_user_visual_review`
- raw 이미지: `artifacts/wo_scene07_surfacefix_canary_v4_20260828/scene_07_raw.png`
- raw SHA-256: `5ea8639dda2a8c2eaba69c725aafab941fff1edbc60eb9252b39f2e88de7944f`
- Fal, TTS, MP4 조립, 썸네일: 실행하지 않음

## 1. 결론

사용자 권고대로 이번 canary에는 두 변경만 넣었다.

1. 결정론 텍스트 표면에 장식 도형을 동시에 요구하던 프롬프트 충돌 제거
2. 현재 활성 참조의 보존 및 scene07 문맥에 맞는 참조 선택

새로 발견한 `semantic_object_id`/`surface_id` 의미 바인딩은 넣지 않았다. 네 문자열을 전부 `main` 표면에 배치하는 기존 파일럿 계획을 의도적으로 그대로 보존했다. 따라서 이번 결과는 해부학·화풍 회귀가 위 두 수정으로 줄었는지를 좁게 보는 자료이며, 의미 표면 문제 해결의 증거가 아니다.

HTTP 200은 이미지 승인과 다르다. 자동 상태는 사용자 실물 검토 전까지 `pending_user_visual_review`, `approval_blocked=true`다.

## 2. 단계별 실제 계보

### 2.1 승인 대본

장면 내레이션:

> 삼성전자와 SK하이닉스를 제외해도요. 코스피 영업이익이 143조 원에 달했죠.

- 내레이션 SHA-256: `143e208a9e08b8b0cd335b3084dd9bf88af17b6ac68576af0ae206ed147a6d23`
- 보존 입력: `artifacts/job52_full_audit_20260824/metadata/scene_generation_contracts.json`
- 보존 입력 SHA-256: `72dd95c1f577acca6793d850567d045c28c7a0e5cd05f3229d9d105c8dc8cdf6`

### 2.2 참조 선택

실제 POST에 들어간 순서와 픽셀 해시는 다음과 같다.

| 순서 | 참조 | 역할 | SHA-256 |
|---:|---|---|---|
| 1 | `channel_character_face_range_v2.png` | 승인 6장 얼굴 범위 | `7e7981e389d07c4c3eca908708365cdcc809226c0f9a039f7ff7f62bbad8e40e` |
| 2 | `channel_character_face_scene05_v1.png` | 고글·연구원 역할의 확대 얼굴 보조 | `7b6c97c2713bb70d34f0a3d71022bda16bd9a032a6d0417457bce6083bfae6e2` |
| 3 | `channel_style_job52_data_lab.png` | Job52 scene04 기반 data-lab 화풍·정보 밀도 | `87c52f3ef3c0bdd0bfddeb3ed08f15f7038c38c48fc5ebf291db625d8aed05e6` |

직전 거절 canary가 사용한 브리핑·시장흐름 참조 대신 현재 공통 선택기가 `data laboratory` 문맥을 인식한 결과다. 참조 파일 이름뿐 아니라 원장 `request_evidence.references`의 바이트 해시와 일치한다.

### 2.3 Gemini 프롬프트

- worker bounded 프롬프트: `artifacts/wo_scene07_surfacefix_canary_v4_20260828/bounded-prompt.txt`
- bounded 프롬프트 SHA-256: `7630d5f5697b20de4f10c67a972b2f39d06345014afba459f47dc62e49a3f984`
- 실제 POST 직전 최종 프롬프트: `artifacts/wo_scene07_surfacefix_canary_v4_20260828/final-gemini-prompt.txt`
- 최종 프롬프트 SHA-256: `5be5bc1982ea2ceed15301a858569634ae17173ee25f785fb8972555dd2ebdec`
- 실제 payload SHA-256: `6c32b65afcc2b277e85530b99c1efac2aa3ba52368e73dffb3f1c21df4a925dc`

프롬프트에는 다음이 확인됐다.

- `calm uniform interior`: 있음
- 과거 충돌 문구 `non-linguistic shapes`: 없음
- `Two unlettered containers`: 있음
- 동전 하나가 머리와 몸통 전체를 이루고 짧은 팔다리가 테두리에 붙는 실루엣 계약: 있음
- 참조의 문자·수치·말풍선·소품·구도를 그대로 복제하지 말라는 최종 참조 계약: 있음

### 2.4 의도적으로 바꾸지 않은 표면 계획

다음 네 항목은 모두 `surface=main`이다.

| 문자열 | 표면 | 영역 |
|---|---|---|
| `삼성전자` | `main` | 좌상 |
| `SK하이닉스` | `main` | 우상 |
| `코스피` | `main` | 좌하 |
| `143조 원` | `main` | 우하 |

- 표면 계획 SHA-256: `2606e0b98cd8d661d86d2f774f225e05122a06a8cf294fada1fd99fe76b1ffa9`
- 전체 장면 계약 SHA-256: `a03ea4cc0335e486235d7e6ffefa5800771929cb8e497928a359ca4f1c86a5ba`

이 결함은 다음 공통 의미 바인딩 트랙의 대상이며, 이번 canary의 독립 변수가 아니다.

## 3. 공급자 응답과 비용 원장

- 요청 시각: 2026-08-28 12:27:14 KST
- 완료 시각: 2026-08-28 12:28:08 KST
- duration: 52.936초
- 외부 요청 원장 항목: 정확히 1건
- 예약액: ₩1,600
- 과거 원장 포함 보수적 누적 노출 상한: ₩11,200
- 비용 상태: `unverified_until_console_reconciliation`

`₩1,600`과 `₩11,200`은 예상 청구액이나 확정 지출이 아니라 중복 요청을 막기 위한 보수적 예약 상한이다.

원문 `usageMetadata`:

```json
{
  "promptTokenCount": 2076,
  "candidatesTokenCount": 1332,
  "totalTokenCount": 3545,
  "promptTokensDetails": [
    {"modality": "TEXT", "tokenCount": 1302},
    {"modality": "IMAGE", "tokenCount": 774}
  ],
  "candidatesTokensDetails": [
    {"modality": "IMAGE", "tokenCount": 1120}
  ],
  "thoughtsTokenCount": 137,
  "serviceTier": "standard"
}
```

합계는 `2076 + 1332 + 137 = 3545`로 내부 정합하다. 청구 콘솔 대조 전 실제 비용을 확정하지 않는다.

## 4. 실물 예비 점검 — 사용자 판정을 대체하지 않음

이 절은 다음 조사 방향을 위한 작성자 예비 소견이다. 승인 판정이 아니다.

| 항목 | 직전 거절 canary | 이번 raw 예비 소견 | 상태 |
|---|---|---|---|
| 해부학 | 동전 아래 긴 인간형 다리 | 하나의 동전 몸체, 테두리에서 이어진 짧은 두 팔·두 다리 | 사용자 판정 대기 |
| 얼굴 | 작은 회청색 홍채, 단층 반사광 | 큰 갈색 홍채, 흰자와 복수 반사광이 보임 | 사용자 판정 대기 |
| 화풍 | 따뜻한 일반 AI 실험실, 가는 선·부드러운 그라데이션 | 굵은 외곽선과 푸른 data-lab 환경이 참조 쪽에 가까움 | 사용자 판정 대기 |
| 말풍선·의사문자 | 그래프 도형 다수 | raw에는 문자·수치·말풍선 없음 | 자동 확인 가능 |
| 소품 | 오른쪽 병 두 개의 의미가 불명확 | 왼쪽 투명 용기 두 개와 동전이 명확히 보임 | 의미 관계는 사용자 판정 대기 |
| 정보 표면 | 장식 그래프로 가득 참 | 큰 빈 모니터가 보임 | 로컬 표면 게이트는 실패 |

해부학과 화풍이 눈에 띄게 달라졌더라도 사용자 확인 전 `개선됨` 또는 `통과`로 기록하지 않는다.

## 5. 새로 확인된 실패와 의미

### 5.1 결정론 표면 검출 실패

raw에는 큰 빈 모니터가 육안으로 보이지만 `render_semantic_surface_text()`는 다음 이유로 fail-closed했다.

> 로컬 픽셀에서 안전한 빈 물리 표면을 찾지 못했습니다.

따라서 이번 raw는 결정론 텍스트 합성까지 통과한 장면이 아니다. 모니터 내부의 푸른 그라데이션, 검출 기하, 기존 `main` 영역 계약 중 무엇이 직접 원인인지는 다음 오프라인 조사에서 분리해야 한다. 표면 검출 임계값을 이번 이미지 하나에 맞춰 완화하지 않는다.

### 5.2 장면 의미는 아직 미완료

두 용기는 존재하지만, raw만으로는 그것들이 `삼성전자`와 `SK하이닉스`를 뜻하고 두 기업을 제외한 `코스피 영업이익 143조 원`이라는 관계가 완전하게 읽히지 않는다. 결정론 텍스트가 정확히 합성되고, 각 문구가 의미 오브젝트 및 표면과 연결된 뒤에만 평가할 수 있다.

즉 이번 결과가 답한 좁은 질문은 해부학·화풍 회귀의 재발 여부뿐이다. `surface_semantic_mismatch`는 그대로 남아 있다.

## 6. 다음 순서

1. 사용자가 raw 실물을 해부학·화풍·장면 의미·예상 밖 결함 기준으로 판정한다.
2. 판정과 무관하게, 빈 모니터가 로컬 표면 검출에서 거절된 원인을 오프라인에서 조사한다.
3. 별도 트랙에서 `semantic_object_id`와 `surface_id` 공통 계약을 설계하고 파일럿 전용 `main` 단일화를 제거한다.
4. 두 작업을 한 번에 다음 canary에 섞지 않는다. 선행 실패 테스트와 최소 수정으로 각각 격리한다.
5. 텍스트·표면·사용자 육안 승인이 끝나기 전 Fal, TTS, MP4 조립으로 진행하지 않는다.

## 7. 검증 자료

- 실행 명세: `docs/evidence/wo_img01_g_surfacefix_canary_20260828/scene07-surfacefix-canary-spec.json`
- 집중 preflight: 13 passed
- preflight JUnit: `docs/evidence/wo_img01_g_surfacefix_canary_20260828/focused-preflight.xml`
- 실행 원장: `artifacts/wo_scene07_surfacefix_canary_v4_20260828/request_ledger.json`
- 실행 manifest: `artifacts/wo_scene07_surfacefix_canary_v4_20260828/manifest.json`
- 직전 거절 결과: `docs/WO_IMG_01_F_SCENE07_VISUAL_REGRESSION_RESULT_2026-08-28.md`

scene42는 동결 상태를 유지했다. 이번 호출은 새 scene key `wo-img01-g-surfacefix:7`의 새 원장만 사용했다.

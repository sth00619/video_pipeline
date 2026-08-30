# WO-PROVIDER-02 — scene00 Flash 격리 재현 결과

작성: 2026-08-29

## 1. 판정 정정

Stage2 콘택트시트의 scene00 Flash 칸은 검은색 결과 이미지가 아니다. 원장상 해당 요청은 HTTP 503이었고 raw 이미지가 없어서, 콘택트시트가 어두운 실패 칸과 작은 `생성 실패/보류` 문구를 표시했다. 따라서 기존 칸만으로 `Flash 생성물이 완전히 붕괴했다`고 판정할 수 없다.

## 2. 격리 실행 계약

- 모델: `gemini-3.1-flash-image`
- 장면: Job52 보존 입력 scene00
- 프롬프트와 참조: Stage2 공통 계약과 동일
- 독립 POST: 2회
- 자동 재시도: 0회
- scene42: 호출 0회, 동결 유지
- TTS/Fal/조립: 실행하지 않음

두 요청의 payload SHA-256은 모두 `62727d47db1f2d5cf68b805f5f2c97c07857e78d028493e36a80068dfecb997c`로 같고, 두 요청 모두 HTTP 200이었다.

## 3. 실물 판정

### attempt 1

- 정상적인 교실, 저울, 동전 캐릭터 구도
- `삼성전자`, `SK하이닉스` 정확 표기
- 비승인 `KOSPI`가 칠판에 추가됨
- 결정론 레이어 대상 `PER 4배`는 base raster에 없음
- 판정: 구조 붕괴는 없지만 generated-text 계약 위반으로 거절

### attempt 2

- 정상적인 교실, 저울, 동전 캐릭터 구도
- `삼성전자`, `SK하이닉스` 정확 표기
- 결정론 레이어 대상인 `PER 4배`를 모델이 직접 그림
- 승인되지 않은 `들어보셨나요?`까지 붙여 `PER 4배, 들어보셨나요?`로 생성
- 판정: 구조 붕괴는 없지만 수치 라우팅과 generated-text 계약 위반으로 거절

## 4. 결론

동일 계약의 두 HTTP 200 결과에서 검은 화면·깨진 문자 형태의 완전 붕괴는 0/2였다. 따라서 `Flash가 scene00 유형에서 구조적으로 완전히 무너진다`는 가설은 이번 표본으로 지지되지 않는다. Stage2의 원래 scene00 Flash는 이미지 품질 실패가 아니라 공급자 503이었다.

반대로 임의·비승인 문자 생성은 2/2에서 재현됐다. Flash의 주요 위험은 이번 표본에서는 장면 구도 붕괴보다 **텍스트 계약 미준수**다. 이 결과만으로 Flash를 기본 모델로 선택하지 않는다.

## 5. 실행기 사후 정정

두 raw 이미지는 정상 저장됐지만, 실증 스크립트가 `ImageResult.usage_metadata`라는 존재하지 않는 속성을 사후 참조해 최초 manifest에 두 결과를 실패로 잘못 표시했다. 공급자 원장은 두 요청을 HTTP 200으로 정확히 기록했고 이미지 SHA-256도 보존했다. 실행기는 usage metadata를 `ProviderRequestAudit` 원장에서 읽도록 수정했으며, manifest는 raw와 원장을 근거로 정정했다. 추가 외부 호출은 하지 않았다.

## 6. 증거

- `artifacts/wo_provider_02_scene00_flash_reproduction_20260829/manifest.json`
- `artifacts/wo_provider_02_scene00_flash_reproduction_20260829/request_ledger.json`
- `artifacts/wo_provider_02_scene00_flash_reproduction_20260829/scene_00_flash_attempt_1.png`
- `artifacts/wo_provider_02_scene00_flash_reproduction_20260829/scene_00_flash_attempt_2.png`
- `artifacts/wo_provider_02_scene00_flash_reproduction_20260829/scene00_flash_reproduction_contact_sheet.png`

# NAVER API HUB 뉴스·검색어 트렌드 설정

이 프로젝트는 2026년 NAVER API HUB 규격으로 뉴스 검색과 검색어 트렌드를 사용합니다. 이전 NAVER Developers 키와 `X-Naver-*` 헤더는 사용하지 않습니다.

## 콘솔 등록

1. NAVER Cloud Platform 콘솔의 **NAVER API HUB > Application 등록**에서 `검색어트렌드`와 `뉴스`를 선택합니다.
2. Application 이름에 `video-pipeline-news-trend`처럼 용도를 알 수 있는 이름을 입력하고 **완료**를 누릅니다.
3. 생성된 Application 상세 화면에서 Client ID와 해당 Client Secret을 확인합니다. 키는 채팅, 소스 코드, Git에 올리지 않습니다.

## 로컬 환경 변수

저장소 루트의 개인 `.env` 파일에 아래 세 값을 설정합니다. `.env.example`은 예시 파일이므로 실제 키를 넣지 않습니다.

```dotenv
NAVER_API_HUB_ENABLED=true
NAVER_API_HUB_CLIENT_ID=콘솔에서_발급한_Client_ID
NAVER_API_HUB_CLIENT_SECRET=Client_ID에_연결된_Client_Secret
```

`NAVER_API_HUB_ENABLED=true`인데 두 인증 값 중 하나라도 없으면 FastAPI 워커는 시작 단계에서 실패합니다. 키가 아직 없을 때는 `false`로 두면 RSS와 Google News 보조 경로만 사용합니다.

설정 후 FastAPI 워커 컨테이너를 재생성합니다.

```powershell
docker compose up -d --build fastapi-workers
```

## 프로젝트 내 사용 방식

| 기능 | API HUB 요청 | 파이프라인 적용 |
| --- | --- | --- |
| 뉴스 검색 | `GET /search/v1/news` | 키워드 수집, 최근 뉴스 근거, 기사 근거 후보 수집 |
| 검색어 트렌드 | `POST /search-trend/v1/search` | 상위 다섯 키워드에 최근 28일 주간 상대 추이 원본을 첨부 |

두 API 모두 기본 주소는 `https://naverapihub.apigw.ntruss.com`이며 인증 헤더는 아래와 같습니다.

```text
X-NCP-APIGW-API-KEY-ID: Client ID
X-NCP-APIGW-API-KEY: Client Secret
```

검색어 트렌드의 `ratio`는 절대 검색량이 아니라 해당 요청 결과의 최댓값을 100으로 둔 상대값입니다. 프로젝트는 이 값을 금융 수치·가격 변동 원인·사실 주장으로 사용하지 않고, 키워드 후보의 출처 정보로만 보관합니다.

## 확인 절차

키를 설정한 뒤 다음 테스트를 실행하면 실제 키를 출력하지 않고 요청 URL·헤더 이름·입력값 검증을 확인할 수 있습니다.

```powershell
docker run --rm -v "${PWD}\backend\fastapi-workers:/workspace" -w /workspace video_pipeline-fastapi-workers pytest tests/test_naver_api_hub.py tests/test_article_discovery.py -q
```

실제 API 호출 검증은 Application 등록과 키 설정이 끝난 후에만 수행합니다. 401/403이면 Application에 뉴스와 검색어트렌드가 모두 선택됐는지, 해당 API HUB Client ID/Secret인지 먼저 확인합니다.

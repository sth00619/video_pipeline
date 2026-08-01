# V5 신규 4개 Archetype 사전조사와 프롬프트 검토

작성일: 2026-07-31  
상태: **코드 미반영 · 이미지 API 미호출**  
전제: 기존 7개 archetype은 모두 primary-surface 검증을 통과했다.

## 1. P2를 텍스트와 형태로 분리

신규 archetype에서는 primary 외의 소품을 아래 두 기준으로 함께 판정한다.

| 기준 | 통과 조건 |
|---|---|
| P2-T (텍스트) | primary 외 소품에 읽을 수 있는 문자·숫자·축·라벨이 없다. |
| P2-F (형태) | 새 비문자 소품도 아래 세 질문에 모두 **예**여야 한다. |

P2-F의 세 질문:

1. 그 장소에 실제로 있을 법한 무대 고유 소품인가?
2. 배경으로 자연스러운 크기·위치인가? 캐릭터나 primary와 시선을 다투지 않는가?
3. 나중에 글자가 생겼을 때 primary의 대체 정보 표면으로 혼동될 수 없는가?

하나라도 아니오면 P2-F 실패다. 글자가 없는 모니터·명패·카드라도 예외가 아니다.

`retail_shock`의 비문자 안내 화면은 매장 고유 장비이고, 가장자리 배경에 있으며, 매립 영수증 창과 경쟁하는 정보 구조가 아니어서 경계 통과로 기록했다. 신규 검증에서는 이보다 큰 화면·중앙 화면·텍스트가 있는 화면을 허용하지 않는다.

## 2. 신규 무대 공통 계약 초안

아래는 아직 코드에 넣지 않은 **프롬프트 검토용 계약 문자열**이다. 실제 구현 시 `ARCHETYPES`, `ARCHETYPE_SURFACES`, `DIEGETIC_TEXT_GUIDANCE`, `_primary_substitute_ban()`이 같은 계약을 공유해야 한다.

```text
IN-SCENE FACT-SURFACE CONTRACT:
The only permitted information-bearing prop is [PRIMARY SURFACE].
It MUST contain two or three short, clearly readable decorative English labels or sample figures,
plus one simple chart silhouette or diagram line, physically integrated into that exact material.
Every other object must remain rich only through color blocks, abstract shapes, needles,
non-writing material texture, and non-linguistic silhouettes.
No readable text, digits, labels, axis ticks, or chart annotations may appear outside the primary.
All AI-drawn writing is decorative only; verified facts are composited later by Pillow/FFmpeg
inside the same physical surface.
```

## 3. 소품 전수조사와 P2-F 위험

| archetype | 무대와 명시 소품 | 제안 primary 1개 | primary 외 비문자 소품 | 테마상 텍스트/형태 누출 위험 |
|---|---|---|---|---|
| `earnings_stage` | 기업 실적 발표 무대, 중앙 발표대, 벽 매립 실적 브리핑 벽, 마이크, 객석, 카메라, 천장 조명, 바닥 라인, 비문자 막대·추이 실루엣 | **발표대 뒤 중앙 벽에 매립된 하나의 넓은 실적 브리핑 표면** | 발표대 정면, 마이크, 카메라, 객석, 조명, 바닥 라인, 보조 차트 실루엣 | 독립 LED 보드, 발표대 명패, 객석 이름표, 카메라 로고, 별도 슬라이드 카드. 큰 보조 화면은 P2-F 고위험. |
| `briefing_podium` | 정책·CEO 브리핑실, 중앙 연단, 연단 뒤 벽 매립 브리핑 표면, 고정 마이크, 기자석, 카메라, 조명, 국기 색 리본, 바닥 케이블 | **중앙 연단 바로 뒤 벽에 매립된 하나의 넓은 브리핑 표면** | 연단 명패, 마이크, 기자증, 카메라, 조명, 리본, 케이블, 보조 스크린 | 연단 명패·기자증·국기 로고·텔레프롬프터·독립 기자회견 보드. 연단 명패는 작아도 primary 대체물이라 금지. |
| `real_estate_office` | 부동산/금리 상담 사무실, 상담 책상, 벽 고정 시세·대출 안내 보드, 집 모형, 서류·파일, 계산기, 창문과 주택 실루엣, 스탠드 조명 | **상담 책상 뒤 벽에 고정된 하나의 넓은 시세·대출 안내 보드** | 책상, 서류, 파일, 계산기(액정은 반드시 비어 있음), 집 모형, 창문, 주택 실루엣, 램프, 안내 아이콘 | 창문 매물 카드, 책상 계산기 액정, 부동산 간판, 서류·가격표, 독립 가격 카드. 작은 종이·명패가 특히 P2-F 고위험. |
| `job_market_hall` | 공공 고용 상담 공간, 중앙 상담대, 벽 고정 고용 동향 보드, 상담 칸막이, 구직자, 번호표 기계, 이력서 서류, 가방, 안내 조명, 비문자 직업 아이콘 | **중앙 상담대 뒤 벽에 고정된 하나의 넓은 고용 동향 안내 보드** | 상담대, 칸막이, 번호표 기계, 이력서, 가방, 조명, 구직자, 직업 아이콘 | 채용 공고·회사 로고·번호표·이력서 글자·독립 취업 키오스크·게시물 묶음. 추가 안내판은 P2-F 최고 위험. |

## 4. Archetype별 검토용 프롬프트 핵심 문자열

### earnings_stage

```text
PRIMARY: the single broad earnings-briefing surface embedded flush into the center back wall directly behind the presentation podium.
MUST: Put two or three short decorative English earnings callouts and sample figures only inside that flush wall surface; integrate them with the wall illumination, perspective, and chart silhouettes.
BAN: Do not substitute it with an independent LED board, podium nameplate, freestanding slide, side screen, audience badge, camera label, ticker strip, or separate report card.
NON-PRIMARY: podium front, microphones, cameras, audience seating, ceiling lights, floor lines, and every secondary chart silhouette must remain non-textual.
```

### briefing_podium

```text
PRIMARY: the single broad policy-briefing surface embedded flush into the center back wall immediately behind the central podium.
MUST: Put two or three short decorative English policy callouts and one simple diagram only inside that wall surface; inherit the room lighting and perspective.
BAN: Do not substitute it with a podium nameplate, teleprompter, press badge, microphone logo, flag emblem, freestanding briefing board, side screen, lower-third banner, or floating alert panel.
NON-PRIMARY: podium plaque, microphones, press seating, cameras, ceiling lights, flag-color ribbons, floor cables, and all secondary screens must remain non-textual.
```

### real_estate_office

```text
PRIMARY: the single broad market-and-loan guidance board fixed flush to the wall directly behind the consultation desk.
MUST: Put two or three short decorative English market callouts and sample figures only on that wall-fixed board, painted or printed into its material and perspective.
BAN: Do not substitute it with a window listing, desk calculator display, property sign, sale card, loose paper, clipboard, desk monitor, price tag, or freestanding rate panel.
BLANK DEVICE RULE: The desk calculator display must remain completely blank and empty, showing no digits, symbols, labels, bars, chart marks, or pseudo-writing. It is a physical calculator, not a second information surface.
NON-PRIMARY: consultation desk, loose papers, file folders, calculator, house model, window, exterior homes, lamp, and every desk device must remain non-textual.
```

### job_market_hall

```text
PRIMARY: the single broad employment-trend guidance board fixed flush to the wall directly behind the central consultation counter.
MUST: Put two or three short decorative English employment callouts and one simple chart silhouette only inside that wall-fixed board.
BAN: Do not substitute it with a job-posting sheet, company logo, queue-ticket display, résumé text, kiosk screen, counter placard, vacancy card, freestanding hiring board, or separate notice cluster.
NON-PRIMARY: consultation counter, booth dividers, queue-ticket machine, résumés, bags, guide lights, people, career icons, and every secondary wall notice must remain non-textual.
```

## 5. 구현 전 확인 항목

1. 네 무대 모두 primary가 작은 명패나 독립 카드가 아닌 **벽 매립형·벽 고정형 큰 표면**인가?
2. stage/props/visual detail에 있는 모든 소품이 non-primary 목록 또는 대체물 금지 목록에 포함되었는가?
3. P2-F의 세 질문을 생성 결과 검토 양식에 별도 기록하는가?
4. `scene_type` 후보 매핑은 코드 반영 전에 별도 테스트로 검증하는가?
5. `real_estate_office`의 계산기처럼 화면/액정이 필연적으로 있는 비-primary 소품은 `must remain completely blank and empty` 규칙을 별도로 갖는가?
6. 실제 생성은 archetype별 프롬프트 문자열 검토와 비용 승인이 끝난 뒤, 하나씩 `max_attempts=1`로 하는가?

이 문서는 설계·검토 산출물이며 API 호출, 키 사용, 비용 발생, 실제 수치 삽입을 수행하지 않는다.

## 6. 첫 실제 검증 후보

첫 후보는 **`earnings_stage`**로 정한다. 네 후보 중 primary가 발표대 뒤의 단일 벽 매립 표면으로 가장 단순하고, `weather_map`·`data_lab`에서 통과한 "큰 고정 벽 표면" 구조와 가장 가깝다.

- `briefing_podium`은 연단 명패·텔레프롬프터·기자증·국기 로고 등 대체물 위험이 더 많다.
- `real_estate_office`는 계산기 액정·매물 카드·서류 등 작은 정보 표면이 밀집되어 있으며, 이번에 빈 액정 규칙을 추가했다.
- `job_market_hall`은 이력서·번호표·게시물·키오스크처럼 텍스트로 새기 쉬운 소품이 가장 많다.

따라서 코드 반영 및 첫 이미지 생성은 `earnings_stage`부터 하되, 실제 호출은 이 사전검토 결과에 대한 별도 비용 승인을 받은 뒤에만 수행한다.

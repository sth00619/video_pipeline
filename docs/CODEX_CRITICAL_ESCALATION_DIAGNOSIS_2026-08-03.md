# 긴급 에스컬레이션 진단 — E2E 산출물 품질 실패

작성일: 2026-08-03  
범위: 조사·진단 전용. 코드 수정, Gemini/TTS/Kling/MP4/썸네일 생성 없음.

## 분석 대상과 증거 한계

- 대상 파일: `C:\Users\song\Downloads\final.mp4`
- 실제 확인: 509.3초, 1920×1080, H.264/AAC, SHA-256 `9FC306A26E8B16CB6DE54029D3BE99388AE3EAC465C8AEA9C38FD089389EDC93`
- 이 바이트 해시는 워크스페이스의 어떤 MP4와도 일치하지 않았다.
- 따라서 이 파일을 조립한 정확한 manifest, 최종 ASS, TTS 입력, Forced Alignment 결과, 요청 원장은 보존되어 있지 않다. 이 문서는 확정 가능한 코드·배치 증거와, 확정 불가능한 산출물 계보를 구분한다.

### 실제 프레임 증거

| 지점 | 파일 | 관찰 |
|---|---|---|
| 0:30 | `artifacts/diagnostics/critical_escalation_20260803/frames/00m30s.png` | 교실·칠판 배경, 캐릭터 안경/교수형 외관 |
| 1:30 | `artifacts/diagnostics/critical_escalation_20260803/frames/01m30s.png` | 상단 좌측 불투명 검정 `caption_chip`형 박스, 끝줄 말줄임표 |
| 3:00 | `artifacts/diagnostics/critical_escalation_20260803/frames/03m00s.png` | 항만 배경, 상단 흰 정보 박스와 하단 검정 자막 박스 |
| 5:00 | `artifacts/diagnostics/critical_escalation_20260803/frames/05m00s.png` | 교실 반복, 흰 말풍선형 요약문과 하단 검정 자막 박스 |
| 7:00 | `artifacts/diagnostics/critical_escalation_20260803/frames/07m00s.png` | 항만 반복, 흰 말풍선형 요약문과 말줄임표 |

32×18 회색조 지문 비교 결과, 다섯 프레임은 같은 래스터의 단순 재사용은 아니었다(쌍별 해밍 거리 225~349/576). 그러나 사람 검수로 분류한 배경은 교실 3회, 항만 2회여서 다섯 표본이 두 archetype에 과도하게 집중됐다. 이 파일의 표본에서는 `risk_control_room` 4/4 반복은 확인되지 않았다.

## [결함 1] 검은 불투명 자막/텍스트 박스

- 확인 결과: 1:30, 3:00, 5:00 프레임에서 검은 불투명 박스가 보인다. 5:00과 7:00에는 별도 흰 말풍선도 보인다.
- 현재 ASS 코드: `app/workers/longform_worker.py`의 `_generate_ass()`는 `BorderStyle=1`이다. 따라서 현재 소스만으로는 ASS `BorderStyle=3`이 원인이라고 확정할 수 없다.
- 확정 원인: `app/services/overlay/editorial_overlay.py`는 `caption_chip`·`title_card`·`date_stamp`에 `(0,0,0,238)`의 불투명 검정 배경을 직접 렌더링한다. `app/services/overlay/editorial_director.py`는 배경/결론/액션 씬에 `caption_chip`을 선택하고, `app/workers/longform_worker.py`는 이를 조립 단계에서 영상에 합성한다.
- 추가 근거: `kospi_august_2026_e2e_final/script_result.json`의 93개 섹션은 전부 `bubble_text`를 갖고, 전부 `---`로 끝난 미완성 문구다. typed editorial 경로는 이 미완성 문구를 차단하지 않아 프레임의 말줄임표와 일치한다.
- 판정: **확정 — 자막 외 요약 텍스트 오버레이가 허용되어 있고, 검은 박스를 직접 만드는 렌더링 경로가 존재한다.**
- 이 영상의 버전: 정확한 manifest가 없으므로 미확정. 다만 2026-08-02 E2E 스크립트 배치의 구조와 결과가 강하게 일치한다.

## [결함 2] archetype 반복과 장면 다양성 실패

- 확인 결과: 실제 5개 표본은 교실 3회, 항만 2회다. 동일 배경 래스터는 아니지만, 장르·공간·구도가 두 archetype에 집중됐다.
- 배치 근거: 원본 E2E 스크립트는 93개 섹션 중 `metric` 76개, `diagram` 13개, `graph` 4개다. 장면의 art family는 다양하게 계획되어 있으나, 실제 6개 선택 후보만 만들도록 축소되어 있다.
- 근본 원인: 수치·등락 표현을 만나면 `metric`으로 우선 분류하는 과거 배치의 분류 결과가 장면 수를 압도했다. 현재 소스의 `_rebalance_scene_type_distribution()`은 지표형을 최대 12장/18%로 낮추도록 되어 있지만, 이 93개 기록은 그 재균형 결과가 아니다.
- 보조 근거: 같은 E2E 배치의 비용 원장은 선택 이미지 6건 모두 `http_429`로 종료됐음을 기록한다. 따라서 실제 영상이 이 배치에서 나왔다면, 선택된 6장도 정상 Gemini 산출물 대신 대체·기존 자산을 사용했을 가능성이 있으나, 정확한 최종 조립 manifest 부재로 확정하지 않는다.
- 판정: **배경 편중은 확정, `risk_control_room` 고정값은 이 파일에서 반증, 과거 배치의 지표형 과분류는 확정.**

## [결함 3] 정보형 씬의 대본 의미·물리 소품 결합 부재

- 확인 결과: E2E 원본 93개 섹션의 `caption_en`은 0개이며, 83개는 `editorial_text_surface`가 없다.
- 코드 근거: `app/v5/scene/prompt_builder.py`의 `_build_prop_prompt()`는 유효한 `caption_en`이 있어야만 “실제 소품 표면에 정확히 한 번” 쓰도록 프롬프트를 만든다.
- 근본 원인: 당시 원본 씬 계약은 `no text` 생성 프롬프트와 사후 오버레이를 중심으로 구성돼 있었고, 대본 의미를 영어 핵심 문구·비수치 그래프·물리 표면으로 옮기는 V5 계약이 입력부터 비어 있었다.
- 판정: **확정 — 프롬프트 모델의 불이행 이전에 입력 계약이 결손돼 있었다.**

## [결함 4] 캐릭터 화풍·의상·정체성 불일치

- 확인 결과: 0:30/1:30은 안경·교수형, 3:00/7:00은 안전모·현장 기자형, 5:00은 또 다른 비율과 표정이다. 영상 내부에서 고정 캐릭터가 아니다.
- 배치 근거: 원본 93개 씬의 의상은 13종이며 `field_reporter`, `anchor`, `professor`, `analyst`, `referee` 역할이 혼재한다. 같은 원본 프롬프트 93개에는 `bold ink outlines`, `cel shading`은 있으나 `brown fedora`, `navy suit`, `character_reference`, `style_reference`는 모두 0회다.
- 근본 원인: 화풍 지시만 있고 캐릭터 정체성·모자·슈트·참조 자산을 모든 호출에 강제하는 계약이 없었다. 역할별 의상 변경 지시가 오히려 캐릭터의 통일성을 깨뜨렸다.
- 참조 자산 전달 여부: 정확한 최종 이미지 요청 원장이 없으므로 이 영상 호출별 전수 판정은 불가하다. 다만 원본 scene payload에 `reference_image_paths`가 0개인 것은 확인했다.
- 판정: **확정 — 입력 설계가 고정 마스코트 목표와 충돌한다. 최종 API 호출 단위 누락 여부는 미확정.**

## [결함 5] 기사형·일반형 부재

- 확인 결과: 원본 93개 씬에서 `article_capture` 0개, `article_evidence` scene type 0개, `article_scene` visual kind 0개, 검증 사실 참조도 0개다.
- 근본 원인: 기사형을 별도 선택·렌더링하는 계약이 원본 E2E 입력에 없었다. `news_context`라는 일반적 시각 유형이 15개 있어도 실제 기사 캡처·출처·밑줄·하이라이트는 아니다.
- 판정: **확정 — 기사형이 “계획상 표현”에 그쳤고 실제 장면 유형으로는 생성되지 않았다.**

## [별도 지적] TTS·자막·스크립트 100% 일치

- 배치 입력 확인: 93개 섹션의 `content/text`와 `text_for_tts`는 공백을 제외하면 모두 일치한다. 문장 단위 `text`와 `text_for_tts`도 불일치 0개다.
- 그러나 최종 검증 불가: `final.mp4`와 연결된 TTS 입력 전문, MP3, ASS/SRT, Forced Alignment 결과, quality report가 보존되어 있지 않다. 따라서 이 영상의 실제 음성·자막이 원문과 100% 일치한다고 주장할 근거는 없다.
- 현재 코드 상태: `tts_worker.py`는 ElevenLabs 문자 단위 정렬을 얻지 못하면 최종 조립을 실패시키고, 공백을 제외한 원문·자막 일치도 검사한다. 다만 이것은 현재 코드의 계약이며, 계보가 없는 기존 결과물의 증명은 아니다.
- 판정: **입력 단계는 통과, 실제 E2E 산출물은 미검증.**

## [별도 지적] 범위 통제

- 이번 진단에서는 Gemini, TTS, Kling, MP4, 썸네일 실행을 전혀 수행하지 않았다.
- 코드 변경은 없으며, 프레임 캡처와 이 진단 문서만 만들었다.

## 재개 전 필수 품질 게이트

1. 자막 외 `caption_chip`·말풍선·제목 카드의 자동 합성을 비활성화하거나, 화면 문구를 원문 스크립트와 동일한 자막 계약으로 통합한다.
2. 대본→씬 단계에서 기사형 3·상황형 3·정보형 3의 실제 장면 계약을 먼저 확정하고, 일반 장문에서는 연속 동일 archetype 금지와 분포 상한을 강제한다.
3. 모든 캐릭터 씬에 동일 참조 이미지와 고정 정체성(갈색 페도라, 네이비 슈트, 큰 갈색 눈, 홍조, 굵은 검정 윤곽선)을 전달한다. 역할 의상 변경은 금지한다.
4. 정보형에는 대본 의미에 맞는 짧은 영어 문구를 하나만 선택해 물리 소품 표면에 넣고, 수치·보조 UI·공중 부유 텍스트는 금지한다.
5. 실행 산출물마다 최종 MP4 SHA-256, manifest, 전송 프롬프트, 참조 이미지 목록, TTS 입력 SHA-256, ASS/SRT, alignment mode, 균등 프레임 5장, archetype 분포를 함께 보존한다.

이 다섯 항목의 코드·계약 수정은 별도 작업 지시와 승인 후에만 수행한다.

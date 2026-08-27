# 참조 자산 분류

| 파일 | 분류 | Git 보존 |
|---|---|---|
| `channel_character_face_range_v1.png` | superseded_face_reference | 보존 |
| `channel_style_job52_briefing.png` | runtime_required | 보존 |
| `channel_style_job52_data_lab.png` | runtime_required | 보존 |
| `channel_style_job52_market_flow.png` | runtime_required | 보존 |
| `channel_style_job52_risk_map.png` | runtime_required | 보존 |
| `channel_style_job52_semiconductor.png` | runtime_required | 보존 |
| `channel_style_semiconductor_growth_scene_v1.png` | runtime_required | 보존 |
| `channel_style_semiconductor_production_scene_v1.png` | runtime_required | 보존 |
| `character_reference.png` | no_static_consumer | 조건부 정리 후보 |
| `character_reference_v2_textless.png` | legacy_generated | 조건부 정리 후보 |
| `character_reference_v4_identity_clean.png` | tool_input | 보존 |
| `layout_reference.png` | no_static_consumer | 조건부 정리 후보 |
| `layout_reference_v2_textless.png` | tool_input | 보존 |
| `source_05s.png` | rebuild_input | 보존 |
| `source_20s.png` | unused_rebuild_output | 조건부 정리 후보 |
| `source_35s.png` | unused_rebuild_output | 조건부 정리 후보 |
| `source_50s.png` | unused_rebuild_output | 조건부 정리 후보 |
| `style_reference.png` | no_static_consumer | 조건부 정리 후보 |
| `style_reference_v2_textless.png` | legacy_generated | 조건부 정리 후보 |
| `style_reference_v4_medium_clean.png` | tool_input | 보존 |
| `style_scene_ref_01_port.png` | legacy_generated | 조건부 정리 후보 |
| `style_scene_ref_02_split.png` | legacy_generated | 조건부 정리 후보 |
| `style_scene_ref_03_retail.png` | legacy_generated | 조건부 정리 후보 |
| `style_scene_ref_04_weather.png` | legacy_generated | 조건부 정리 후보 |
| `style_scene_ref_05_weather_v2.png` | legacy_generated | 조건부 정리 후보 |
| `channel_character_face_range_v2.png` | runtime_required | 보존 |

- 정적 이름 검색 결과는 읽기/쓰기/매니페스트 항목을 모두 포함한다. 역할 분류는 해당 호출 코드와 대조했다.
- app/main.py character_image_path와 CLI 명시 경로는 동적이다. 운영 DB/진행 중 요청의 전체 참조를 조회하지 않았다.
- 후보 13개는 삭제 승인이나 확정된 죽은 파일이 아니다. 백업 및 동적 참조 대조 후에만 이력 제거 가능.
- 기존 filter-generated-binary-paths.txt는 위험한 역사 초안으로 그대로 보존했다. 실행하면 안 된다.

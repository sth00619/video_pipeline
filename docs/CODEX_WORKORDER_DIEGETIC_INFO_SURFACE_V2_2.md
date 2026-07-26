# Codex 작업지침서 보완 — Diegetic Info Surface v2.2 (구현 확정본)

이 문서는 `CODEX_WORKORDER_DIEGETIC_INFO_SURFACE_V2_1.md`의 구현 확정 보완본이다. v2.1의 완료 조건과 금지 규칙은 유지하며, 아래 항목이 우선한다.

## 1. 모션 QA — 절대 좌표 비교 금지

`zoompan`은 프레임마다 crop/scale이 달라지므로, 표면과 글자의 화면상 절대 좌표를 1px로 비교하면 정상적인 동일 transform도 실패한다. 테스트 목적은 “정보 레이어가 이미지와 별도로 고정돼 움직이는지”를 검출하는 것이다.

`test_info_surface_motion.py`는 아래 둘 중 하나를 사용한다. 기본 구현은 **역변환 방식**이다.

1. 렌더러가 기록한 각 프레임의 zoompan affine/crop transform을 역적용하여, 표면 꼭짓점과 글자 기준점 모두를 원본 PNG 좌표로 되돌린다. 역변환 후 3개 표본 프레임에서 상대 거리가 1px 이하이면 통과한다.
2. 역변환을 기록할 수 없는 FFmpeg 경로는 표면 대각선으로 정규화한다. `distance(text_anchor, surface_anchor) / surface_diagonal`의 프레임 간 편차가 `0.002` 이하이면 통과한다.

```python
# 우선 규칙: 역변환 가능 시 원본 공간에서 비교
assert max_inverse_mapped_anchor_delta_px <= 1.0

# fallback: transform을 읽을 수 없는 경우만 정규화 거리 비교
assert max_normalized_anchor_delta <= 0.002
```

최소 글자 획 3px, 축/수치 가는 선 2px, 숫자 x-height 24px이라는 v2.1 QA 하한은 최종 1080p 인코딩 프레임에서 계속 검사한다.

## 2. DATA_CUTAWAY 타임라인 계약

P0의 `DATA_CUTAWAY`는 **실패한 원 씬의 이미지를 1:1로 대체**하는 결정론적 데이터 인서트다.

- 원 씬의 index, 시작/종료 시간, TTS 오디오, 자막 cue, scene duration을 절대 변경하지 않는다.
- 씬을 둘로 쪼개거나, extra duration을 추가하거나, Ken Burns·TTS 타임라인을 재계산하지 않는다.
- `final_image_path`만 cutaway PNG로 교체하고, 동일한 clip/motion 파이프라인에 넣는다.
- manifest에는 `replacement_of_scene_id`, `timeline_mode="one_to_one_replace"`, `chart_semantics_reduced`를 기록한다.
- `METRIC_SUMMARY`는 chart source refs와 원래 차트 종류를 유지한다. `chart_semantics_reduced=true`일 때만 축/계열이 생략되었다는 검수 경고를 노출한다.

```python
def apply_data_cutaway(scene: Scene, cutaway_path: str) -> Scene:
    # duration, TTS timing, subtitle cue는 보존한다.
    scene.final_image_path = cutaway_path
    scene.info_surface_plan.timeline_mode = "one_to_one_replace"
    return scene
```

## 3. 가림 마스크의 질감 노이즈 제거

`delta_e > threshold`만으로 가림을 계산하면 종이의 얼룩·조명 그라데이션·안티앨리어싱 가장자리를 체인/손으로 오판한다. `detector.py`의 가림 마스크는 다음 순서로 정제한다.

```python
raw_occluder = quad_interior_mask & (delta_e_map > contract.marker_delta_e_max)
opened = cv2.morphologyEx(raw_occluder.astype("uint8"), cv2.MORPH_OPEN, kernel_3x3)
min_component_area = 0.005 * quad_area  # quad 면적의 0.5%
occluder_mask = keep_connected_components(opened, min_area=min_component_area)
composite_mask = quad_interior_mask & ~dilate(occluder_mask, 2)
```

- `quad_interior_mask` 경계 2px 이내의 안티앨리어싱 픽셀은 가림 판정에서 제외한다.
- 60% 가용 면적 검사는 정제된 `occluder_mask` 이후에만 계산한다.
- `dilate(..., 2)`는 실제 전경 윤곽 주변의 합성 누수를 막기 위해 유지한다.
- fixture에는 종이결, 그림자 그라데이션, 미세 얼룩만 있는 표면(가림 0으로 판정되어야 함)과 체인/손이 표면을 가로지르는 표면(가림으로 판정되어야 함)을 각각 넣는다.

## 4. 재생성·resume 호출 의무

반자동 게이트의 ‘이미지만 재생성’과 ‘텍스트 기반 이미지 재생성’, 그리고 중단 작업의 resume은 모두 새 원본 PNG에 대해 `_apply_info_surface_plan(scene, image_path)`를 반드시 다시 실행한다.

```python
def finalize_regenerated_scene(scene, generated_source_path):
    # 어떤 재생성 진입점에서도 이 공통 경로만 사용한다.
    scene.source_image_path = generated_source_path
    scene.final_image_path = _apply_info_surface_plan(scene, generated_source_path)
    persist_info_surface_manifest(scene)
    return scene
```

- resume의 유효성 판단은 `source_image_path`가 아니라 `final_image_path`의 SHA-256과 `InfoSurfacePlan`/detector/compositor/style 버전 fingerprint로 한다.
- source PNG가 바뀌거나 surface contract, marker, chart payload, compositor 버전 중 하나가 바뀌면 기존 final PNG는 무효다.
- 재생성 실패·quad 실패·fallback 결과도 동일한 manifest에 누적하고, 이전 실패를 성공으로 덮어쓰지 않는다.

## 5. 실제 생성 팔레트 이탈에 대한 보수 규칙

생성 전 `marker_scene_delta_e_min >= 20`을 만족해도 실제 생성물의 지배색이 marker에 가까워질 수 있다. 따라서 검출 단계에서 다음 보수 규칙을 적용한다.

1. 후보 표면 내부와 후보 주변 20px ring의 실제 Lab 분포를 측정한다.
2. 주변 ring의 지배색과 marker의 ΔE가 20 미만이면 `palette_collision=true`를 기록한다.
3. `palette_collision=true`일 때 `border_match` 가중치를 0.35로 높이고 `color_purity` 가중치를 0.25로 낮춘다.
4. 테두리 일치가 `0.70` 미만이면 즉시 `ambiguous_surface` 실패로 처리한다. 근처의 비슷한 크림 포스터를 추정 선택하지 않는다.
5. 이 실패는 재생성이 아니라 역할별 P0 fallback으로 처리한다.

```text
normal score:     color .40 + border .20 + position .25 + area .15
palette collision: color .25 + border .35 + position .25 + area .15
```

## 6. 완료 조건 갱신

v2.1의 G절 6개 완료 조건은 그대로 유지하고, 다음을 추가/치환한다.

1. 저울 장면의 체인 가림 및 원근 합성 후, **역변환 원본 공간**에서 표면-글자 기준점 차이가 1px 이하이거나 역변환 불가 경로에서 정규화 편차 0.002 이하이다.
2. 크림 표면 4개 fixture와 실제 팔레트 충돌 fixture에서 올바른 표면만 선택하거나 `ambiguous_surface`로 안전하게 실패한다.
3. DATA_CUTAWAY는 원 씬을 1:1로 대체하며 TTS·자막·duration을 변경하지 않는다.
4. 종이결/조명만 있는 fixture는 가림 면적 0으로, 체인/손 fixture는 연결 성분 기준 가림으로 판정한다.
5. 모든 재생성/resume 진입점은 final PNG를 다시 합성하고 final fingerprint로 캐시를 판정한다.
6. 기존 수치 무결성·예산·구형 카드 경로 CI 게이트를 전부 통과한다.

이 문서까지 반영되면 P0 구현을 시작할 수 있다. `BAKED_LABEL`은 계속 기본 비활성이고, P0에서 생성 모델의 한글/수치 렌더를 승인하지 않는다.

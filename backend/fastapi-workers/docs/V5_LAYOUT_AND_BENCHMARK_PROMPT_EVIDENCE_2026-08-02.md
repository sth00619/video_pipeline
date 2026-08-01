# LayoutSketcher 및 benchmark 스타일 원문 대조

## 1. LayoutSketcher의 원래 전달 방식

결론: **처음부터 텍스트 계약 방식이다.** 이미지 참조 방식이 텍스트로 대체된 것이 아니다.

`app/v5/scene/layout_sketcher.py`의 원래 주석과 메서드는 다음을 명시한다.

- 모듈 상단: SVG는 개발 검토용이며 이미지 모델의 참조 이미지로 전달하지 않는다. 래스터 가이드가 장면 테두리로 복제되는 것을 막기 위한 설계다.
- `LayoutPlan.prompt_instruction()`: 문자·선·프레임을 만들지 않도록 상대 배치만 언어로 전달한다.
- `LayoutPlan.to_svg()`: 사람 검토용 무문자 SVG를 만든다. 이 SVG는 공급자 입력에 사용하지 않는다.

7월 30일 benchmark의 `_request_ledger.json`도 이를 독립적으로 증명한다.

| 항목 | bench_08_datalab 기록 |
|---|---|
| `reference_contract` | `v3_textless_no_layout_raster` |
| 참조 자산 | character v2 + style v2, 2장 |
| `layout_contract` | `keep the mascot in the center foreground ... Do not draw any layout guide ...` |
| 텍스트 정책 | `strict_textless` |

따라서 R1의 `<layout_contract>` 복원은 원래 benchmark 방식의 복원이다. API 입력 참조 이미지는 2장에서 3장으로 늘지 않는다.

## 2. benchmark 스타일 지시 원문 증거의 범위

benchmark 요청 원문의 전체 prompt는 원장에 영속 저장되지 않았다. 따라서 “7월 30일에 API로 전송된 완전한 문자열”을 파일에서 바이트 단위로 복구할 수는 없다.

다만 benchmark 직전 코드 기반인 Git 초기 커밋 `34bfb8e`의 `build_prompt()`에는 아래 스타일 지시가 있다.

```text
ART STYLE: bold thick black ink outlines, flat cel-shading, high contrast,
rich prop density, theatrical composition, editorial cartoon quality, limited
vivid palette.
```

이 한 줄은 현재 R1에도 그대로 포함된다. 그러나 benchmark 원장에는 data_lab의 center layout이 남아 있고 초기 커밋의 scene 설정은 그와 완전히 같지 않으므로, 초기 커밋 전체가 7월 30일 실행 소스와 바이트 단위로 동일했다고 주장하지 않는다.

## 3. benchmark 스타일 문자열과 현재 R1의 diff

```diff
  ART STYLE: bold thick black ink outlines, flat cel-shading, high contrast,
  rich prop density, theatrical composition, editorial cartoon quality, limited
  vivid palette.
+ Build one continuous full-bleed illustrated stage with clear foreground,
+ midground, and background depth.
+ Preserve hard, readable cel-shadow boundaries and strong localized red, gold,
+ cyan, or storm-light accents chosen by the stage.
+ Do not render a smooth vector-dashboard illustration, a glossy 3D toy, a
+ corporate UI illustration, or an airbrushed premium concept-art finish.
```

즉 현재 R1은 **benchmark 핵심 한 줄을 보존했지만, 완전한 원문 롤백은 아니다.** 위 세 문장은 현재 미감 실패를 겨냥해 새로 추가한 보정이다.

## 4. 실제 생성 전 결정이 필요한 선택지

### 선택 A: 현재 R1 유지

- 장점: benchmark 핵심 문구 + 현 관찰에 대응한 벡터/UI 억제 + LayoutSketcher 복원
- 한계: benchmark보다 지시가 길어, 여전히 프롬프트 비중 변화라는 변수가 남는다.

### 선택 B: R1-B 엄격 benchmark 복원

- art direction을 아래 한 줄로 정확히 축소한다.
- `LayoutSketcher` 복원, 정보형 중복 라벨 제거, primary 계약은 유지한다.
- `FRAME CONTINUITY`는 art direction에서 제거하되, 기존 exclusions의 split/collage 금지는 유지한다.

```text
ART STYLE: bold thick black ink outlines, flat cel-shading, high contrast,
rich prop density, theatrical composition, editorial cartoon quality, limited
vivid palette.
```

선택 B가 benchmark와 더 직접적인 미감 비교 실험이다. 다만 모델 출력이 비결정적이므로, 동일 문구가 과거 이미지의 픽셀 단위 재현을 보장하지는 않는다.

## 5. 이번 R1 판정 범위

다음 2장 재생성에서는 Gemini 배경의 무대 밀도·명암·셀 셰이딩·장식 라벨만 판정한다. Pillow가 사후 합성하는 검증 수치 카드의 재질은 이 판정에서 제외한다.


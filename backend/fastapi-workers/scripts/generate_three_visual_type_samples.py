#!/usr/bin/env python3
"""V5 3종 이미지(일반형/정보형/기사형)를 실제 파이프라인 코드로 생성해
``final plan/`` 폴더에 저장한다.

2026-08-04 재검토: 사용자가 첫 결과물을 보고 "정보형 이미지의 정확 수치
오버레이가 따로 붙은 것처럼 보인다, 숫자에 집착할 필요 없다"고 명확히
피드백했다. 이에 따라 정보형은 더 이상 Pillow 정확 수치 오버레이를 쓰지
않고, 이미지 생성과 같은 패스에서 원근·조명이 자연스럽게 녹아드는 네이티브
방향성 그래프(상승=빨강/하락=파랑, 한국 관행과 일치) + 근사 파이차트 등
``script_visual_plan``의 소품 계획만 사용한다.

- 일반형(semantic_illustration): Gemini 3 Pro Image 실제 호출. 텍스트 없음.
- 정보형(archetype_explainer, 2종): Gemini 3 Pro Image 실제 호출.
  (1) 방향성 사례 — 마트 물가 상승을 빨강 상승 그래프로 근사 표현.
  (2) 비중 사례 — 라면 시장점유율을 파이차트 실루엣으로 근사 표현
  (정확한 숫자 없이, 형태만으로 이해 가능하게).
- 기사형(article_evidence): 실제 연합뉴스(yna.co.kr) 기사면을 Playwright로
  캡처하고 실제 ``annotate.render_annotations`` 프리미티브(밑줄+하이라이트)로
  근거 표시. 임의 URL을 새로 만들지 않고 evidence_capture.py가 이미
  허용하는 발행사(yna.co.kr)의 실제 기사만 사용한다.

이미지 API 호출(일반형·정보형)과 실제 기사 캡처는 ``--execute``일 때만 발생한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent.parent / ".env")

OUT_DIR = ROOT.parent.parent / "final plan"


def _reference_paths() -> list[str]:
    from app.v5.providers.gemini_provider import GeminiProviderError

    reference_root = ROOT / "out" / "references"
    manifest_path = reference_root / "reference_manifest_v4_identity_style_clean.json"
    paths = [
        reference_root / "character_reference_v4_identity_clean.png",
        reference_root / "style_reference_v4_medium_clean.png",
    ]
    if any(not path.is_file() for path in paths):
        raise GeminiProviderError("V5 참조 자산이 없어 생성을 시작할 수 없습니다.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {item["role"]: item["sha256"] for item in manifest["artifacts"]}
    for role, path in zip(("character", "style"), paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected.get(role):
            raise GeminiProviderError(f"참조 자산 해시가 일치하지 않습니다: {role}")
    return [str(path) for path in paths]


def _planned_scenes() -> list[dict[str, Any]]:
    """일반형 1씬 + 정보형(검증 수치 포함) 1씬을 실제 계약 경로로 계획한다."""
    from app.v5.scene.runtime_contract import attach_v5_scene_contracts
    from app.workers.script_worker import _classify_scene_types

    raw_scenes = [
        {
            "scene_id": "sample_general_port",
            "title": "",
            "content": "코인 마스코트가 항구를 걸으며 컨테이너와 화물선을 지나간다.",
            "text": "코인 마스코트가 항구를 걸으며 컨테이너와 화물선을 지나간다.",
            "visual_intent": "Character-focused harbor story with a continuous cartoon set.",
        },
        {
            "scene_id": "sample_info_retail_direction",
            "title": "",
            "content": "마트 계산대에서 확인한 소비자물가지수가 크게 상승했다.",
            "text": "마트 계산대에서 확인한 소비자물가지수가 크게 상승했다.",
            "visual_intent": "Retail checkout scene with an approximate rising price display near the mascot.",
        },
        {
            "scene_id": "sample_info_market_share",
            "title": "",
            "content": "농심과 삼양라면의 국내 라면 시장점유율 비율 구도를 살펴봅니다.",
            "text": "농심과 삼양라면의 국내 라면 시장점유율 비율 구도를 살펴봅니다.",
            "visual_intent": "An approximate pie-chart comparison of two ramen brands, no exact numbers.",
        },
    ]
    classified = _classify_scene_types(raw_scenes)
    planned = attach_v5_scene_contracts(classified)
    types = [scene["v5_render_contract"]["scene_type"] for scene in planned]
    if types[0] != "general" or any(kind not in {"metric", "graph", "diagram", "text"} for kind in types[1:]):
        raise ValueError(f"샘플 씬 분류가 예상과 다릅니다: {types}")
    return planned


def _generate_general_and_info(execute: bool) -> dict[str, Any]:
    from app.v5.cost_ledger import Bucket, CostLedger, FxProvider
    from app.v5.providers.gemini_provider import GeminiModel, GeminiProvider

    scenes = _planned_scenes()
    provider = GeminiProvider(use_batch=False)
    unit_usd = provider.estimate_cost_usd(GeminiModel.PRO, 2048, 1152)
    rate = FxProvider().usd_to_krw()
    labels = {
        "sample_general_port": "일반형",
        "sample_info_retail_direction": "정보형_방향성",
        "sample_info_market_share": "정보형_비중",
    }

    summary: dict[str, Any] = {
        "status": "preflight_only" if not execute else "running",
        "model": GeminiModel.PRO.value,
        "estimated_total_krw": round(unit_usd * rate) * len(scenes),
        "scenes": [
            {
                "scene_id": scene["scene_id"],
                "scene_type": scene["v5_render_contract"]["scene_type"],
                "archetype": scene["v5_render_contract"]["selection"]["archetype"],
                "surface_caption": (scene["v5_render_contract"].get("surface_caption") or {}),
            }
            for scene in scenes
        ],
    }
    if not execute:
        return summary

    references = _reference_paths()
    ledger = CostLedger(video_id="three_visual_type_sample", fx=FxProvider())
    results = []
    for index, scene in enumerate(scenes):
        contract = scene["v5_render_contract"]
        ledger.guard(Bucket.IMAGE_FINAL, unit_usd)
        started = time.monotonic()
        result = provider.generate(
            contract["prompt_en"], model=GeminiModel.PRO, width=2048, height=1152,
            seed=901 + index, reference_image_paths=references,
        )
        label = labels[scene["scene_id"]]
        out_path = OUT_DIR / f"09_생성확인_{label}.png"
        out_path.write_bytes(result.image_bytes)
        ledger.record(
            scene_id=scene["scene_id"], provider="gemini", model=GeminiModel.PRO.value,
            request_kind="generate", bucket=Bucket.IMAGE_FINAL, estimated_usd=unit_usd,
            actual_usd=None, rate=rate, status="ok",
            cost_status="unverified_until_console_reconciliation", metadata=result.meta,
        )
        results.append({
            "scene_id": scene["scene_id"], "label": label,
            "seconds": round(time.monotonic() - started, 1), "output_path": str(out_path),
        })
    summary.update({"status": "completed", "results": results, "ledger": ledger.summary()})
    return summary


_DEFAULT_DISCOVERY_TOPIC = "코스피 반도체"

# source_policy.py의 발행사별 검수된 containers/excludes를 그대로 받아 그
# 범위 안에서만 문단을 찾는다. 언론사마다 공유 도구·광고·관련기사 위젯의
# 마크업이 달라, 우리가 즉석에서 만든 선택자보다 이미 검수된 규칙이 안전하다.
# 문단의 화면상 줄 단위 사각형(getClientRects)도 함께 반환한다 — 밑줄은
# 문단 전체를 감싸는 사각형이 아니라 실제 글자가 있는 줄마다 그어야 마지막
# 줄 뒤 빈 공간까지 빨간 줄이 삐져나가지 않는다.
_FIND_REAL_PARAGRAPH_JS = """([containers, excludes]) => {
    const excludeSelector = excludes.join(', ');
    const scopes = containers.length
        ? containers.flatMap((sel) => Array.from(document.querySelectorAll(sel)))
        : [document.body];
    const items = [];
    const seen = new Set();
    scopes.forEach((scope) => {
        scope.querySelectorAll('p').forEach((p) => {
            if (seen.has(p)) return;
            seen.add(p);
            const text = (p.innerText || '').trim();
            if (text.length < 40) return;
            const r = p.getBoundingClientRect();
            if (r.width < 300 || r.height < 10) return;  // 화면에 실제로 보이는 문단만
            if (excludeSelector && p.closest(excludeSelector)) return;
            const lineRects = Array.from(p.getClientRects()).map((rect) => ({
                top: rect.top + window.scrollY, left: rect.left, width: rect.width, height: rect.height,
            }));
            items.push({
                top: r.top + window.scrollY, left: r.left, width: r.width, height: r.height,
                text, lineRects,
            });
        });
    });
    items.sort((a, b) => a.top - b.top);
    return items[0] || null;
}"""


def _discover_article_url(topic: str) -> tuple[str, str]:
    """실제 NAVER 뉴스 검색으로 주제에 맞는 기사를 찾는다.

    특정 언론사(예: yna.co.kr)로 고정하지 않는다 — evidence_planner.py가
    실제로 쓰는 것과 같은 ``ArticleDiscoveryService``로 검색해, 주제에 가장
    맞고 점수가 높은 결과를 고른다. 이미 허용된 발행사(``source_policy.py``)
    범위 안에서 검색되므로 검증되지 않은 매체로 새지 않는다.
    """
    from app.services.article_discovery import ArticleDiscoveryService, ArticleDiscoveryUnavailable

    try:
        candidates = ArticleDiscoveryService().discover(topic, terms=topic.split(), limit=10)
    except ArticleDiscoveryUnavailable as exc:
        raise RuntimeError(f"기사 검색을 사용할 수 없습니다: {exc}") from exc
    if not candidates:
        raise RuntimeError(f"'{topic}' 주제에 맞는 허용 발행사 기사를 찾지 못했습니다.")
    top = candidates[0]
    return top.url, top.publisher


def _capture_article_sample(topic: str = _DEFAULT_DISCOVERY_TOPIC) -> dict[str, Any]:
    """주제에 맞는 실제 기사를 검색해 캡처하고, 실제 annotate 프리미티브
    (밑줄+하이라이트)로 근거를 표시한다.

    사용자 피드백 3건을 함께 반영한다: (1) 전체 페이지 캡처는 글자가 너무
    작아 읽기 어렵다 — CSS zoom으로 실제 렌더 글자를 키운다. (2) 임의로 지어낸
    기사가 아니라 실제 기사를 보여줘야 한다 — 첫 문단을 DOM에서 직접 찾아 그
    위치로 스크롤한 뒤 캡처한다. (3) 특정 언론사(yna.co.kr)로 고정하지 않는다
    — 실제 evidence_planner.py와 같은 NAVER 뉴스 검색으로 주제에 맞는 기사를
    고른다. (4) 빨간 밑줄은 문단 전체 폭이 아니라 실제 글자가 있는 줄까지만.
    """
    from playwright.sync_api import sync_playwright

    from app.services.annotate import render_annotations
    from PIL import Image, ImageDraw, ImageFont
    import io

    from app.services.article.source_policy import publisher_for_url

    article_url, publisher = _discover_article_url(topic)
    rule = publisher_for_url(article_url)
    containers = list(rule.containers) if rule else []
    excludes = list(rule.excludes) if rule else ["header", "nav", "aside", "footer", ".ad"]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page.goto(article_url, wait_until="domcontentloaded", timeout=30000)

        # og:title은 거의 모든 한국 언론사가 SEO용으로 채워 두므로, 언론사마다
        # 다른 h1 마크업보다 신뢰도가 높다. 없을 때만 페이지 <title>로 보완한다.
        headline_text = (
            page.locator('meta[property="og:title"]').get_attribute("content")
            or page.title()
            or ""
        ).strip()
        if not headline_text:
            raise RuntimeError(f"기사 헤드라인을 찾지 못했습니다: {article_url}")

        page.evaluate("document.body.style.zoom = '1.7'")
        # 공유 도구·안내 배너 같은 sticky/fixed 오버레이는 스크롤해도 항상
        # 화면에 남아 캡처 영역을 가린다. 언론사마다 클래스명이 달라 개별
        # 선택자로 걸러내기 어려우므로, 계산된 위치가 fixed/sticky인 요소는
        # 일괄 숨긴다 — 기사 본문 레이아웃 자체는 static 배치라 영향이 없다.
        page.evaluate("""
            document.querySelectorAll('*').forEach((el) => {
                const pos = getComputedStyle(el).position;
                if (pos === 'fixed' || pos === 'sticky') el.style.setProperty('display', 'none', 'important');
            });
            // 텍스트 드래그 시 뜨는 '공유/스크랩' 팝업류는 fixed가 아니라
            // absolute + JS 스크롤 추적으로 흉내낸 sticky인 경우가 많아
            // 클래스명 패턴으로 추가 제거한다(mk.co.kr의 "menu-container fix" 등).
            document.querySelectorAll(
                '[class*="share" i], [class*="tool" i], [class*="popup" i], [class*="tooltip" i], ' +
                '[class*="menu-container" i], [class*="floating" i], [class~="fix"]'
            ).forEach((el) => { el.style.setProperty('display', 'none', 'important'); });
        """)
        page.wait_for_timeout(400)

        paragraph = page.evaluate(_FIND_REAL_PARAGRAPH_JS, [containers, excludes])
        if not paragraph:
            raise RuntimeError(f"실제로 렌더된 본문 문단을 찾지 못했습니다: {article_url}")

        # 문단이 화면에 보이도록 스크롤한 뒤 좌표를 뷰포트 기준으로 다시 읽는다.
        page.evaluate(f"window.scrollTo(0, {max(0.0, paragraph['top'] - 260)})")
        page.wait_for_timeout(200)
        body = page.evaluate(_FIND_REAL_PARAGRAPH_JS, [containers, excludes])
        if not body:
            raise RuntimeError(f"스크롤 후 본문 문단 좌표를 다시 읽지 못했습니다: {article_url}")
        # window.scrollTo 이후 top은 다시 documentElement 기준 절대좌표이므로
        # 실제 스크롤량을 빼서 뷰포트 기준 좌표로 되돌린다.
        scroll_y = page.evaluate("window.scrollY")
        viewport_box = {
            "x": body["left"], "y": body["top"] - scroll_y,
            "width": body["width"], "height": body["height"],
        }
        line_boxes = [
            {"x": rect["left"], "y": rect["top"] - scroll_y, "width": rect["width"], "height": rect["height"]}
            for rect in body["lineRects"]
            if rect["width"] > 10 and rect["height"] > 5
        ] or [viewport_box]

        clip_top = max(0.0, viewport_box["y"] - 70)
        clip_bottom = min(1080.0, viewport_box["y"] + viewport_box["height"] + 40)
        clip = {"x": 0.0, "y": clip_top, "width": 1920.0, "height": max(160.0, clip_bottom - clip_top)}
        screenshot_bytes = page.screenshot(clip=clip)
        browser.close()

    base = Image.open(io.BytesIO(screenshot_bytes)).convert("RGBA")
    canvas_size = base.size  # 실제 반환된 픽셀 크기(디바이스 반올림 오차 포함)를 그대로 쓴다.

    def _norm(box: dict[str, float]) -> dict[str, float]:
        return {
            "x": max(0.0, box["x"]) / canvas_size[0],
            "y": max(0.0, box["y"] - clip_top) / canvas_size[1],
            "width": min(box["width"], canvas_size[0] - max(0.0, box["x"])) / canvas_size[0],
            "height": min(box["height"], canvas_size[1] - max(0.0, box["y"] - clip_top)) / canvas_size[1],
        }

    annotations = [
        {"type": "highlighter", "bbox": _norm(viewport_box), "color": "#FFE146"},
        # 밑줄은 줄 단위 사각형마다 따로 그어, 문단 마지막 줄의 빈 공간까지
        # 밑줄이 삐져나가지 않고 실제 글자 폭까지만 그어지게 한다.
        {"type": "underline", "bboxes": [_norm(box) for box in line_boxes], "color": "#E60023"},
    ]
    overlay = render_annotations(canvas_size, annotations)
    composed = Image.alpha_composite(base, overlay)

    # evidence_capture.py의 실제 관행과 동일하게, 캡처가 어느 기사에서 왔는지
    # 출처 헤드라인을 하단에 남긴다(사실을 지어내지 않고, 실제 원문을 인용).
    draw = ImageDraw.Draw(composed)
    font = None
    for candidate in (
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",  # 컨테이너(Dockerfile)
        "C:/Windows/Fonts/malgunbd.ttf",  # 이 스크립트를 로컬 Windows에서 돌릴 때
    ):
        try:
            font = ImageFont.truetype(candidate, 22)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    credit = f"출처: {publisher or '확인된 발행사'} — {headline_text[:40]}"
    draw.rectangle((0, canvas_size[1] - 34, canvas_size[0], canvas_size[1]), fill=(0, 0, 0, 200))
    draw.text((16, canvas_size[1] - 30), credit, font=font, fill=(255, 255, 255, 255))

    out_path = OUT_DIR / "09_생성확인_기사형.png"
    composed.convert("RGB").save(out_path, "PNG")
    return {
        "output_path": str(out_path), "source_url": article_url, "publisher": publisher,
        "headline": headline_text, "quote_preview": paragraph["text"][:60],
        "annotations": len(annotations), "underline_line_count": len(line_boxes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Gemini 실제 호출 + 기사형 캡처를 모두 수행")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = _generate_general_and_info(args.execute)
    if args.execute:
        summary["article_sample"] = _capture_article_sample()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

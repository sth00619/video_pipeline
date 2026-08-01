#!/usr/bin/env python3
"""실제 증거를 사용해 KOSPI 7월 전망 V5 파일럿 입력을 만든다.

이 스크립트는 숫자를 만들지 않는다. NAVER API HUB의 기사 원문 URL과 원문
본문에 실제로 있는 값만 Claude 교차검증 후보로 보내며, Claude가 반환한 값도
원문 본문에서 다시 찾을 수 있을 때에만 V5 오버레이 입력으로 채택한다.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(REPO_ROOT / ".env")

from app.services.naver_api_hub import NaverApiHubClient
from app.workers.script_worker import FACT_CHECK_SYSTEM_PROMPT, ScriptWorker


KST = timezone(timedelta(hours=9))
TOPIC = "코스피 7월 전망"
QUERIES = ("코스피 7월 전망", "코스피 7월 증시 전망", "코스피 7월 증권사 전망")
HTML_TAG = re.compile(r"<[^>]+>")
NUMERIC_FIGURE = re.compile(r"\d")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", HTML_TAG.sub("", html.unescape(value or ""))).strip()


def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _article_text(url: str) -> str:
    """기사 원문을 가져와 눈에 보이는 본문만 남긴다.

    원문을 받지 못하면 검색 스니펫만으로 수치 오버레이를 승인하지 않는다.
    """
    response = httpx.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; V5EvidenceBot/1.0)"},
        timeout=15,
        follow_redirects=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise ValueError("HTML 기사 원문이 아닙니다.")
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "iframe"]):
        element.decompose()
    text = " ".join(soup.stripped_strings)
    if len(text) < 400:
        raise ValueError("기사 본문이 너무 짧습니다.")
    return text


def _published_at(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(KST) if parsed.tzinfo else parsed.replace(tzinfo=KST)


def collect_evidence(client: NaverApiHubClient, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """중복·비주제·원문 미확인 기사를 제외하고 URL 고정 증거를 만든다."""
    now = now or datetime.now(KST)
    cutoff = now - timedelta(days=14)
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for query in QUERIES:
        response = client.search_news(query, display=30, sort="date")
        for item in response.get("items", []):
            title = _clean_text(str(item.get("title") or ""))
            description = _clean_text(str(item.get("description") or ""))
            url = str(item.get("originallink") or item.get("link") or "").strip()
            published = _published_at(str(item.get("pubDate") or ""))
            searchable = f"{title} {description}"
            if not url.startswith(("https://", "http://")) or url in seen_urls:
                continue
            if "코스피" not in searchable or published is None or published < cutoff:
                continue
            seen_urls.add(url)
            candidates.append({
                "title": title,
                "description": description,
                "source_url": url,
                "published_at": published.isoformat(),
                "query": query,
            })

    evidence: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            article = _article_text(candidate["source_url"])
        except (httpx.HTTPError, ValueError) as exc:
            # 원문을 검증할 수 없는 후보는 이후의 수치/문자 오버레이에 쓰지 않는다.
            continue
        evidence.append({
            **candidate,
            "source_id": f"news[{len(evidence)}]",
            "source_excerpt": article[:12000],
        })
        if len(evidence) == 6:
            break
    if len(evidence) < 3:
        raise RuntimeError("원문까지 확인된 최근 코스피 증거가 3건 미만입니다. 파일럿을 차단합니다.")
    return evidence


def _content_json(worker: ScriptWorker, *, system: str, messages: list[dict[str, str]], max_tokens: int) -> Any:
    text = worker._call_llm_with_fallback(system, messages, max_tokens=max_tokens)
    parsed = worker._parse_verified_facts(text)
    if not parsed:
        raise ValueError("Claude 응답에서 JSON 배열을 읽지 못했습니다.")
    return parsed


def cross_check(worker: ScriptWorker, evidence: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """3회 Claude 교차검증 후 원문에 값이 존재하는 사실만 확정한다."""
    compact = [{
        "source_id": row["source_id"],
        "title": row["title"],
        "published_at": row["published_at"],
        "source_url": row["source_url"],
        "article_text": row["source_excerpt"],
    } for row in evidence]
    source_ids = [row["source_id"] for row in evidence]
    r1 = f"""주제: {TOPIC}
아래 기사 원문만 증거로 사용하세요.
{json.dumps(compact, ensure_ascii=False)}

각 사실은 하나의 source_id에만 연결하고, 원문에 있는 수치·날짜·고유명사를 바꾸지 마세요.
전망은 사실이 아니라 기사에 명시된 분석 주체의 견해로만 표기하세요.
후보 사실을 번호 목록으로 정리하세요."""
    messages: list[dict[str, str]] = [{"role": "user", "content": r1}]
    r1_text = worker._call_llm_with_fallback(FACT_CHECK_SYSTEM_PROMPT, messages, max_tokens=3500)
    messages.append({"role": "assistant", "content": r1_text})
    r2 = "각 후보에서 원문에 직접 없는 인과관계·수치·전망 확정을 삭제하세요. 수치 단위와 날짜가 원문과 정확히 같은지 비판적으로 재검토하세요."
    messages.append({"role": "user", "content": r2})
    r2_text = worker._call_llm_with_fallback(FACT_CHECK_SYSTEM_PROMPT, messages, max_tokens=3000)
    messages.append({"role": "assistant", "content": r2_text})
    r3 = f"""최종 결과를 JSON 배열 하나로만 반환하세요.
허용 source_field: {source_ids}
형식: [{{"fact":"원문에 직접 있는 사실 또는 명시적 전망 주체의 견해","figure":"원문에 그대로 있는 숫자/날짜/비율 문자열","source_field":"news[n]","confidence":0.0,"overlay_label":"짧은 한국어 라벨"}}]
figure에는 숫자가 반드시 포함되어야 하며, source_field 하나의 원문에서 figure를 그대로 찾을 수 있어야 합니다. 확신이 없으면 항목을 제외하세요."""
    messages.append({"role": "user", "content": r3})
    raw = _content_json(worker, system=FACT_CHECK_SYSTEM_PROMPT, messages=messages, max_tokens=4000)
    by_id = {row["source_id"]: row for row in evidence}
    facts: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_field") or "")
        figure = str(item.get("figure") or "").strip()
        fact = str(item.get("fact") or "").strip()
        source = by_id.get(source_id)
        if source is None or not fact or not NUMERIC_FIGURE.search(figure):
            rejected.append({"candidate": item, "reason": "형식 또는 source_id가 유효하지 않습니다."})
            continue
        if _normalise(figure) not in _normalise(source["source_excerpt"]):
            rejected.append({"candidate": item, "reason": "figure가 기사 원문에 없습니다."})
            continue
        facts.append({
            "fact": fact,
            "figure": figure,
            "source_field": source_id,
            "source_url": source["source_url"],
            "source_title": source["title"],
            "published_at": source["published_at"],
            "overlay_label": str(item.get("overlay_label") or "검증 정보").strip()[:24],
            "confidence": float(item.get("confidence") or 0),
        })
    if len(facts) < 3:
        raise RuntimeError("원문 수치까지 재확인된 사실이 3건 미만입니다. 파일럿을 차단합니다.")
    return facts[:6], rejected


def generate_script(worker: ScriptWorker, facts: list[dict[str, Any]]) -> dict[str, Any]:
    """검증 완료 사실만 이용한 3씬 파일럿용 대본을 만든다."""
    facts_for_prompt = [{
        "fact": row["fact"], "figure": row["figure"], "source_field": row["source_field"],
        "source_url": row["source_url"], "source_title": row["source_title"],
    } for row in facts]
    prompt = f"""주제는 '{TOPIC}'입니다.
검증 완료 사실은 아래뿐입니다.
{json.dumps(facts_for_prompt, ensure_ascii=False)}

60~90초 한국어 경제 설명 대본을 JSON 객체 하나로 작성하세요.
형식: {{"title":"...","script":"...","scenes":[{{"scene_id":"kospi_july_01","narration":"...","visual_intent":"...","fact_indices":[0]}}]}}
scenes는 정확히 3개입니다. 각 scene의 fact_indices는 위 배열의 인덱스를 하나 이상 참조합니다.
숫자·날짜·비율·지수·금액은 반드시 검증 완료 사실에 문자 그대로 포함된 경우에만 쓰세요.
전망을 확정적으로 말하지 말고, 기사에 명시된 주체의 분석/관찰 포인트임을 드러내세요.
출처 URL·새 수치·투자 권유를 대본 문장에 넣지 마세요."""
    text = worker._call_llm_with_fallback(
        "당신은 검증 사실만 사용하는 한국 금융 영상 대본 작가입니다. 사실을 추가하거나 숫자를 추정하지 마세요.",
        [{"role": "user", "content": prompt}],
        max_tokens=4000,
    )
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    payload = json.loads(match.group(1) if match else text)
    scenes = payload.get("scenes") if isinstance(payload, dict) else None
    if not isinstance(scenes, list) or len(scenes) != 3:
        raise ValueError("Claude 대본은 정확히 3개 씬이어야 합니다.")
    if not isinstance(payload.get("script"), str) or not payload["script"].strip():
        raise ValueError("Claude 대본 본문이 비어 있습니다.")
    return payload


def build_pilot_input(facts: list[dict[str, Any]], script: dict[str, Any]) -> dict[str, Any]:
    """기존 최종 후보 배경에 검증 수치만 결정론적으로 합성할 파일럿 계약을 만든다."""
    backgrounds = (
        ROOT / "out/benchmark/gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_08_datalab.png",
        ROOT / "out/benchmark/gemini_pro_strict_textless_v5_composition_8_scene_v3/bench_06_split.png",
        ROOT / "out/benchmark/gemini_pro_strict_textless_v5_identity_continuity_07_trade/bench_07_trade.png",
    )
    anchors = (
        {"x": 0.06, "y": 0.12, "width": 0.27, "height": 0.16, "kind": "monitor"},
        {"x": 0.06, "y": 0.14, "width": 0.27, "height": 0.16, "kind": "placard"},
        {"x": 0.66, "y": 0.12, "width": 0.27, "height": 0.16, "kind": "gauge_caption"},
    )
    output_scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(script["scenes"]):
        requested = scene.get("fact_indices") if isinstance(scene, dict) else None
        fact_index = next((int(value) for value in (requested or []) if isinstance(value, int) and 0 <= value < len(facts)), index % len(facts))
        fact = facts[fact_index]
        output_scenes.append({
            "scene_id": str(scene.get("scene_id") or f"kospi_july_{index + 1:02d}"),
            "background_path": str(backgrounds[index].relative_to(ROOT)).replace("\\", "/"),
            "narration": str(scene.get("narration") or ""),
            "visual_intent": str(scene.get("visual_intent") or ""),
            "verified_facts": [fact],
            "v5_verified_overlays": [{
                "label": fact["overlay_label"],
                "value": fact["figure"],
                "source_ref": "facts[0]",
                "anchor": anchors[index],
            }],
        })
    return {
        "topic": TOPIC,
        "generated_at": datetime.now(KST).isoformat(),
        # 이번 단계는 승인된 배경으로 사실-오버레이 결합을 검증한다. 새 Gemini
        # 이미지가 필요한 실제 영상 렌더링과 비용을 혼동하지 않도록 명시한다.
        "requires_image_generation": False,
        "scenes": output_scenes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="KOSPI 7월 전망 V5 검증 파일럿 생성")
    parser.add_argument("--output-dir", default=str(ROOT / "out/v5_pilot/kospi_july_2026"))
    args = parser.parse_args()
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY가 필요합니다.")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    worker = ScriptWorker()
    worker._llm_provider_log = []
    worker._llm_call_count = 0
    evidence = collect_evidence(NaverApiHubClient())
    facts, rejected = cross_check(worker, evidence)
    script = generate_script(worker, facts)
    pilot = build_pilot_input(facts, script)
    (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "verified_facts.json").write_text(json.dumps({"facts": facts, "rejected": rejected}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "v5_pilot_input.json").write_text(json.dumps(pilot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "verified_script_and_pilot_input_created",
        "output_dir": str(output),
        "evidence_count": len(evidence),
        "verified_fact_count": len(facts),
        "rejected_fact_count": len(rejected),
        "claude_model": "claude-sonnet-4-6",
        "claude_call_count": worker._llm_call_count,
        "next_command": f"python scripts/validate_v5_pilot_input.py --input {output / 'v5_pilot_input.json'}",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

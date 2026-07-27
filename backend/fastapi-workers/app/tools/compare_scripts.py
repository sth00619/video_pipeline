"""레퍼런스 밴드와 생성 대본의 8축 격차를 비교하는 CLI."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from app.tools.build_reference_baseline import build_reference_baseline, load_reference_rows
from app.utils.script_pattern_analyzer import analyze_script


COMPARISONS = {
    "D3 가짜 독자 질문/1k자": ("fake_reader_q_per_1k", ("axis2_retention", "per_1k_chars", "fake_reader_q"), "P3 질문 삽입 강화"),
    "D4 비유/1k자": ("analogy_per_1k", ("axis2_retention", "per_1k_chars", "analogy"), "P2 비유 보강"),
    "D4 비유 커버리지": ("analogy_coverage", ("axis5_analogy", "coverage"), "P2 개념 비유 재생성"),
    "반말 비율": ("banmal_ratio", ("axis4_register", "banmal_ratio"), "레지스터 프롬프트 점검"),
    "2인칭/1k자": ("second_person_per_1k", ("axis4_register", "second_person_per_1k"), "D8 스테이크 연결 보강"),
    "짧은 강조문 비율": ("short_emphasis_ratio", ("axis3_rhythm", "short_emphasis_ratio"), "짧은 강조문과 설명문 비율 조정"),
}


def _nested(value: dict[str, Any], path: tuple[str, ...]) -> float:
    current: Any = value
    for key in path:
        current = current[key]
    return float(current)


def _generated_payload(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {"script": str(value)}


def compare_scripts(reference_rows: list[dict[str, Any]], generated: dict[str, Any], format_name: str) -> dict[str, Any]:
    baseline = build_reference_baseline(reference_rows)
    generated_profile = analyze_script(generated.get("script", ""), {
        "format": format_name,
        "verified_facts": generated.get("verified_facts", []),
        "kind": "generated",
        "reference_texts": [str(row.get("transcript") or "") for row in reference_rows],
    }).to_dict()
    target_key = f"benchmark_stock:{format_name}"
    target = baseline["groups"].get(target_key, {"metrics": {}})["metrics"]
    rows: list[dict[str, Any]] = []
    for label, (metric_name, path, action) in COMPARISONS.items():
        if metric_name not in target:
            continue
        band = target[metric_name]
        value = _nested(generated_profile, path)
        in_band = band["p10"] <= value <= band["p90"]
        gap = 0.0 if in_band else round(value - band["p50"], 4)
        rows.append({"label": label, "metric": metric_name, "reference": band, "generated": round(value, 4), "in_band": in_band, "gap": gap, "action": action})
    hard = generated_profile["axis7_safety"]
    fact = generated_profile["axis8_fact"]
    hard_failures = []
    if hard["buy_sell_directive_count"] or hard["hype_count"] or hard["banned_phrase_count"]:
        hard_failures.append("투자 지시·과장·금칙 표현")
    if hard["reference_ngram_similarity"] >= .15:
        hard_failures.append("참조 n-gram 유사도 임계 초과")
    if fact["numbers_total"] != fact["numbers_traceable"]:
        hard_failures.append("추적 불가 숫자")
    if generated_profile["axis3_rhythm"]["max_same_ender_run"] > 2:
        hard_failures.append("동일 종결 3회 이상 연속")
    gaps = sorted((row for row in rows if not row["in_band"]), key=lambda row: abs(row["gap"]), reverse=True)[:3]
    devices = generated_profile["axis1_structure"]["devices_present"]
    axis_summary = [
        {"axis": "축1 구조", "value": "장치 " + ", ".join(name for name, present in devices.items() if present)},
        {"axis": "축2 유지", "value": f"질문 {generated_profile['axis2_retention']['fake_reader_q_count']} · 비유 {generated_profile['axis2_retention']['analogy_count']}"},
        {"axis": "축3 리듬", "value": f"평균 {generated_profile['axis3_rhythm']['sent_len_mean']}자 · 연속 종결 {generated_profile['axis3_rhythm']['max_same_ender_run']}"},
        {"axis": "축4 레지스터", "value": f"반말 {generated_profile['axis4_register']['banmal_ratio']} · 2인칭/1k {generated_profile['axis4_register']['second_person_per_1k']}"},
        {"axis": "축5 비유", "value": f"커버리지 {generated_profile['axis5_analogy']['coverage']}"},
        {"axis": "축6 훅", "value": f"{generated_profile['axis6_hook']['type']} · 숫자 {generated_profile['axis6_hook']['has_number']}"},
        {"axis": "축7 안전", "value": f"지시 {hard['buy_sell_directive_count']} · 유사도 {hard['reference_ngram_similarity']}"},
        {"axis": "축8 사실", "value": f"추적 {fact['numbers_traceable']}/{fact['numbers_total']}"},
    ]
    return {"format": format_name, "baseline": baseline, "generated_profile": generated_profile, "hard_gate": {"passed": not hard_failures, "failures": hard_failures}, "rows": rows, "top_gaps": gaps, "axis_summary": axis_summary}


def render_markdown(report: dict[str, Any]) -> str:
    hard = report["hard_gate"]
    rows = report["rows"]
    in_band = sum(bool(row["in_band"]) for row in rows)
    lines = [f"# 대본 비교 리포트 ({report['format']}) — {date.today().isoformat()}", "", "## 요약", ""]
    lines.append(f"- 하드 게이트: {'통과' if hard['passed'] else '실패 — ' + ', '.join(hard['failures'])}")
    lines.append(f"- 밴드 적합 지표: {in_band}/{len(rows)}")
    lines.append("- 상위 격차 3: " + (" · ".join(f"{row['label']}={row['generated']}" for row in report["top_gaps"]) or "없음"))
    lines.extend(["", "## 축별 상세", "", "| 축·지표 | 레퍼런스 p10–p50–p90 | 생성값 | 밴드 | 격차 | 조치 |", "| --- | --- | ---: | --- | ---: | --- |"])
    for row in rows:
        band = row["reference"]
        lines.append(f"| {row['label']} | {band['p10']}–{band['p50']}–{band['p90']} | {row['generated']} | {'✓' if row['in_band'] else '✗'} | {row['gap']} | {row['action']} |")
    lines.extend(["", "## 8축 분석 요약", "", "| 축 | 생성 분석값 |", "| --- | --- |"])
    for axis in report["axis_summary"]:
        lines.append(f"| {axis['axis']} | {axis['value']} |")
    safety = report["generated_profile"]["axis7_safety"]
    fact = report["generated_profile"]["axis8_fact"]
    lines.extend(["", "## 안전·법적", "", f"- 매수/매도 지시: {safety['buy_sell_directive_count']}", f"- LLM 생성 추정 숫자: {len(fact['untraceable'])}", f"- 참조 n-gram 유사도: {safety['reference_ngram_similarity']}", f"- 금칙 시그니처: {safety['banned_phrase_count']}"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="레퍼런스 대본과 생성 대본을 8축으로 비교합니다.")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--generated", required=True)
    parser.add_argument("--format", choices=("shorts", "longform"), required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--json", required=True, dest="json_path")
    args = parser.parse_args()
    report = compare_scripts(load_reference_rows(Path(args.reference)), _generated_payload(Path(args.generated)), args.format)
    report_path = Path(args.report)
    json_path = Path(args.json_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

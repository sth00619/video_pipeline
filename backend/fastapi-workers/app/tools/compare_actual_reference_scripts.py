"""사용자가 제공한 실제 전사본과 생성 대본을 원문 비노출 방식으로 비교한다."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from app.tools.build_reference_baseline import build_reference_baseline
from app.utils.script_pattern_analyzer import analyze_script


def _named_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("입력은 이름=파일경로 형식이어야 합니다.")
    name, raw_path = value.split("=", 1)
    path = Path(raw_path)
    if not name.strip() or not path.is_file():
        raise argparse.ArgumentTypeError(f"전사본을 읽을 수 없습니다: {value}")
    return name.strip(), path


def _profile_row(name: str, text: str, channel: str) -> dict[str, Any]:
    profile = analyze_script(text, {"format": "longform", "kind": "reference"}).to_dict()
    devices = profile["axis1_structure"]["devices_present"]
    return {
        "name": name,
        "channel": channel,
        "character_count": profile["meta"]["char_count"],
        "hook": profile["axis6_hook"]["type"],
        "sent_len_mean": profile["axis3_rhythm"]["sent_len_mean"],
        "sent_len_p90": profile["axis3_rhythm"]["sent_len_p90"],
        "banmal_ratio": profile["axis4_register"]["banmal_ratio"],
        "number_density_per_100_chars": profile["axis6_hook"]["number_density_per_100_chars"],
        "devices": {name: bool(devices[name]) for name in ("D1", "D3", "D4", "D5", "D6", "D8", "twist")},
        "safety": profile["axis7_safety"],
    }


def _generated_row(generated: dict[str, Any]) -> dict[str, Any]:
    profile = analyze_script(generated.get("script", ""), {
        "format": generated.get("format", "shorts"),
        "verified_facts": generated.get("verified_facts", []),
        "kind": "generated",
    }).to_dict()
    devices = profile["axis1_structure"]["devices_present"]
    return {
        "name": "이번 실제 생성 대본",
        "channel": "generated",
        "character_count": profile["meta"]["char_count"],
        "hook": profile["axis6_hook"]["type"],
        "sent_len_mean": profile["axis3_rhythm"]["sent_len_mean"],
        "sent_len_p90": profile["axis3_rhythm"]["sent_len_p90"],
        "banmal_ratio": profile["axis4_register"]["banmal_ratio"],
        "number_density_per_100_chars": profile["axis6_hook"]["number_density_per_100_chars"],
        "devices": {name: bool(devices[name]) for name in ("D1", "D3", "D4", "D5", "D6", "D8", "twist")},
        "safety": profile["axis7_safety"],
    }


def _format_devices(row: dict[str, Any]) -> str:
    return ", ".join(name for name, present in row["devices"].items() if present) or "감지 없음"


def _band_text(band: dict[str, Any] | None) -> str:
    if not band:
        return "해당 없음"
    return f"{band['p10']}–{band['p50']}–{band['p90']}"


def _numeric_band(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)

    def at(position: float) -> float:
        return round(ordered[round((len(ordered) - 1) * position)], 4)

    return {"p10": at(.1), "p50": at(.5), "p90": at(.9)}


def _band_result(value: float, band: dict[str, float]) -> str:
    if value < band["p10"]:
        return "범위보다 낮음"
    if value > band["p90"]:
        return "범위보다 높음"
    return "범위 안"


def build_actual_reference_report(
    benchmark_inputs: list[tuple[str, Path]],
    general_inputs: list[tuple[str, Path]],
    generated: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    for name, path in benchmark_inputs:
        text = path.read_text(encoding="utf-8")
        rows.append(_profile_row(name, text, "benchmark_stock"))
        baseline_rows.append({
            "source_id": name,
            "channel": "benchmark_stock",
            "rights_basis": "user_provided_internal_comparison",
            "format": "longform",
            "register": "banmal",
            "transcript": text,
        })
    for name, path in general_inputs:
        text = path.read_text(encoding="utf-8")
        rows.append(_profile_row(name, text, "general_econ"))
        baseline_rows.append({
            "source_id": name,
            "channel": "general_econ",
            "rights_basis": "user_provided_internal_comparison",
            "format": "longform",
            "register": "jondaetmal",
            "transcript": text,
        })
    baseline = build_reference_baseline(baseline_rows)
    generated_row = _generated_row(generated)
    stock_metrics = baseline["groups"].get("benchmark_stock:longform", {}).get("metrics", {})
    fit = {
        "sent_len_mean": _numeric_band([row["sent_len_mean"] for row in rows if row["channel"] == "benchmark_stock"]),
        "short_emphasis_ratio": stock_metrics.get("short_emphasis_ratio"),
        "banmal_ratio": stock_metrics.get("banmal_ratio"),
        "second_person_per_1k": stock_metrics.get("second_person_per_1k"),
    }
    return {
        "report_date": date.today().isoformat(),
        "reference_input": {
            "benchmark_stock_count": len(benchmark_inputs),
            "general_econ_count": len(general_inputs),
            "handling": "원문은 보고서 JSON과 Markdown에 저장하지 않고 메모리에서 수치만 분석",
        },
        "reference_samples": rows,
        "generated": generated_row,
        "generated_script": generated.get("script", ""),
        "baseline": baseline,
        "stock_bands": fit,
    }


def render_markdown(report: dict[str, Any]) -> str:
    generated = report["generated"]
    stock = [row for row in report["reference_samples"] if row["channel"] == "benchmark_stock"]
    general = [row for row in report["reference_samples"] if row["channel"] == "general_econ"]
    bands = report["stock_bands"]
    lines = [
        f"# 실제 대본 비교 보고서 — {report['report_date']}",
        "",
        "## 비교 범위",
        "",
        f"- 주식 타깃 실제 전사본: {report['reference_input']['benchmark_stock_count']}개",
        f"- 일반 경제 설명형 실제 전사본: {report['reference_input']['general_econ_count']}개",
        f"- 처리 방식: {report['reference_input']['handling']}",
        "- 생성 대본은 실제 Claude 생성 후 사실 경계 편집 및 품질 게이트를 통과한 버전입니다.",
        "",
        "## 실제 주식 타깃 전사본 vs 이번 생성 대본",
        "",
        "| 대본 | 글자 수 | 훅 | 평균 문장 | 반말 비율 | 숫자/100자 | 감지된 장치 |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for row in stock:
        lines.append(f"| {row['name']} | {row['character_count']} | {row['hook']} | {row['sent_len_mean']}자 | {row['banmal_ratio']} | {row['number_density_per_100_chars']} | {_format_devices(row)} |")
    lines.append(f"| **{generated['name']}** | **{generated['character_count']}** | **{generated['hook']}** | **{generated['sent_len_mean']}자** | **{generated['banmal_ratio']}** | **{generated['number_density_per_100_chars']}** | **{_format_devices(generated)}** |")
    lines.extend([
        "",
        "## 레퍼런스 밴드 대비 생성값",
        "",
        "| 지표 | 실제 주식 타깃 전사본 p10–p50–p90 | 이번 생성 대본 | 해석 |",
        "| --- | --- | ---: | --- |",
        f"| 반말 비율 | {_band_text(bands['banmal_ratio'])} | {generated['banmal_ratio']} | 주식 타깃의 직접 대화체와 비교 |",
        f"| 평균 문장 길이 | {_band_text(bands['sent_len_mean'])}자 | {generated['sent_len_mean']}자 | {_band_result(generated['sent_len_mean'], bands['sent_len_mean'])} |",
        f"| 2인칭/1k자 | {_band_text(bands['second_person_per_1k'])} | {analyze_script(report['generated_script'], {'format': 'shorts'}).axis4_register['second_person_per_1k']} | 시청자 연결 강도 비교 |",
        f"| 짧은 강조문 비율 | {_band_text(bands['short_emphasis_ratio'])} | {analyze_script(report['generated_script'], {'format': 'shorts'}).axis3_rhythm['short_emphasis_ratio']} | 문장 호흡 비교 |",
        "",
        "## 일반 경제 설명형 실제 전사본 참고",
        "",
        "| 대본 | 글자 수 | 훅 | 평균 문장 | 반말 비율 | 비유 장치 |",
        "| --- | ---: | --- | ---: | ---: | --- |",
    ])
    for row in general:
        lines.append(f"| {row['name']} | {row['character_count']} | {row['hook']} | {row['sent_len_mean']}자 | {row['banmal_ratio']} | {'있음' if row['devices']['D4'] else '없음'} |")
    lines.extend([
        "",
        "## 이번 생성 대본",
        "",
        report["generated_script"],
        "",
        "## 안전성",
        "",
        f"- 생성 대본 매수/매도 지시: {generated['safety']['buy_sell_directive_count']}건",
        f"- 생성 대본 과장 표현: {generated['safety']['hype_count']}건",
        "- 실제 레퍼런스 원문은 비교 입력으로만 사용하며, 이 보고서에는 재수록하지 않았습니다.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="실제 레퍼런스 전사본과 생성 대본을 구조 지표로 비교합니다.")
    parser.add_argument("--benchmark", action="append", type=_named_path, required=True)
    parser.add_argument("--general", action="append", type=_named_path, required=True)
    parser.add_argument("--generated", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--json", required=True, dest="json_path")
    args = parser.parse_args()
    generated = json.loads(Path(args.generated).read_text(encoding="utf-8"))
    report = build_actual_reference_report(args.benchmark, args.general, generated)
    report_path = Path(args.report)
    json_path = Path(args.json_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(report), encoding="utf-8")
    # JSON에도 저작권 원문을 넣지 않는다.
    report_for_json = dict(report)
    report_for_json.pop("generated_script", None)
    json_path.write_text(json.dumps(report_for_json, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

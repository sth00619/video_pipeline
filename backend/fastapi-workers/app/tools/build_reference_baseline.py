"""권리 확인 레퍼런스 JSONL에서 집계 밴드를 만드는 CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.utils.script_pattern_analyzer import analyze_script


METRICS = {
    "fake_reader_q_per_1k": ("axis2_retention", "per_1k_chars", "fake_reader_q"),
    "analogy_per_1k": ("axis2_retention", "per_1k_chars", "analogy"),
    "analogy_coverage": ("axis5_analogy", "coverage"),
    "banmal_ratio": ("axis4_register", "banmal_ratio"),
    "second_person_per_1k": ("axis4_register", "second_person_per_1k"),
    "stake_framing_count": ("axis4_register", "stake_framing_count"),
    "short_emphasis_ratio": ("axis3_rhythm", "short_emphasis_ratio"),
    "connective_variety": ("axis3_rhythm", "connective_variety"),
}


def _value(profile: dict[str, Any], path: tuple[str, ...]) -> float:
    current: Any = profile
    for key in path:
        current = current[key]
    return float(current)


def _band(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "p10": 0.0, "p50": 0.0, "p90": 0.0}
    def percentile(position: float) -> float:
        index = round((len(ordered) - 1) * position)
        return round(ordered[index], 4)
    return {"count": len(ordered), "p10": percentile(.1), "p50": percentile(.5), "p90": percentile(.9)}


def load_reference_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not str(row.get("rights_basis") or "").strip():
            raise ValueError(f"rights_basis 누락: {path}:{line_number}")
        if not str(row.get("transcript") or "").strip():
            raise ValueError(f"transcript 누락: {path}:{line_number}")
        if row.get("format") not in {"shorts", "longform"}:
            raise ValueError(f"format 값 오류: {path}:{line_number}")
        rows.append(row)
    return rows


def build_reference_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """반말 주식 밴드와 일반경제 비유 밴드를 분리해 계산한다."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        channel = str(row.get("channel") or "")
        if channel not in {"benchmark_stock", "general_econ"}:
            raise ValueError(f"허용되지 않은 channel 분류: {channel}")
        profile = analyze_script(row["transcript"], {"format": row["format"], "kind": "reference"}).to_dict()
        groups.setdefault((channel, row["format"]), []).append(profile)

    result: dict[str, Any] = {"version": "reference_baseline.v1", "groups": {}}
    for (channel, format_name), profiles in groups.items():
        metrics = {}
        for name, path in METRICS.items():
            # general_econ은 비유/리듬만 참고하고 반말·2인칭 밴드에는 포함하지 않는다.
            if channel == "general_econ" and name in {"banmal_ratio", "second_person_per_1k", "stake_framing_count"}:
                continue
            metrics[name] = _band([_value(profile, path) for profile in profiles])
        result["groups"][f"{channel}:{format_name}"] = {"sample_count": len(profiles), "metrics": metrics}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="권리 확인 레퍼런스 대본의 p10/p50/p90 밴드를 산출합니다.")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    baseline = build_reference_baseline(load_reference_rows(Path(args.reference)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

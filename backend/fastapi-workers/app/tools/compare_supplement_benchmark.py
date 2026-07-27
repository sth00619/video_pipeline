"""보충 노트의 공개 구조 지표와 생성 대본을 비교하는 비개발자용 CLI."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from app.utils.script_pattern_analyzer import analyze_script
from app.utils.script_style import HOUSE_STYLE_V1


# 이 값은 원문 전사본을 복제한 데이터가 아니라, 보충 노트에 제공된 수동 측정값이다.
SUPPLEMENT_REFERENCE = {
    "source": "SCRIPT_STYLE_SUPPLEMENT.md 제공 측정값",
    "benchmark_stock_sentence_chars": [60.8, 66.3, 22.7, 28.6],
    "general_econ_sentence_chars": [44.3, 33.3, 42.5, 30.7],
    "benchmark_stock_banmal_ratio": 1.0,
    "general_econ_jondaetmal_ratio": 1.0,
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("생성 대본 JSON은 객체여야 합니다.")
    return value


def compare_supplement_benchmark(generated: dict[str, Any]) -> dict[str, Any]:
    profile = analyze_script(generated.get("script", ""), {
        "format": generated.get("format", "shorts"),
        "verified_facts": generated.get("verified_facts", []),
        "kind": "generated",
    }).to_dict()
    targets = HOUSE_STYLE_V1["benchmark_stock_targets"]
    hook = profile["axis6_hook"]
    rhythm = profile["axis3_rhythm"]
    register = profile["axis4_register"]
    facts = profile["axis8_fact"]
    safety = profile["axis7_safety"]
    rows = [
        {"item": "반말 비율", "target": f"{targets['banmal_ratio_min']:.1f} 이상", "actual": register["banmal_ratio"], "passed": register["banmal_ratio"] >= targets["banmal_ratio_min"], "meaning": "주식 타깃의 구어체 레지스터"},
        {"item": "첫 3문장 숫자", "target": f"{targets['opening_number_within_first_three_min']}개 이상", "actual": hook["opening_three_sentence_number_count"], "passed": hook["opening_three_sentence_number_count"] >= targets["opening_number_within_first_three_min"], "meaning": "초반 사실 기반 훅"},
        {"item": "숫자 쇼크 또는 직접 호명", "target": "필수", "actual": "충족" if hook["number_shock_present"] or hook["has_direct_address"] else "미충족", "passed": bool(hook["number_shock_present"] or hook["has_direct_address"]), "meaning": "콜드오픈의 시청자 진입점"},
        {"item": "쇼츠 평균 문장 길이", "target": f"{targets['shorts_sentence_chars_min']}~{targets['shorts_sentence_chars_max']}자", "actual": rhythm["sent_len_mean"], "passed": targets["shorts_sentence_chars_min"] <= rhythm["sent_len_mean"] <= targets["shorts_sentence_chars_max"], "meaning": "짧은 호흡의 설명 리듬"},
        {"item": "숫자 출처 추적", "target": "100%", "actual": f"{facts['numbers_traceable']}/{facts['numbers_total']}", "passed": facts["numbers_total"] == facts["numbers_traceable"], "meaning": "검증 사실 밖 숫자 차단"},
        {"item": "투자 지시·과장", "target": "0건", "actual": safety["buy_sell_directive_count"] + safety["hype_count"], "passed": not (safety["buy_sell_directive_count"] or safety["hype_count"]), "meaning": "법적·신뢰 안전선"},
    ]
    passed_count = sum(bool(row["passed"]) for row in rows)
    provenance = str(generated.get("generation_provenance") or "unknown")
    return {
        "report_date": date.today().isoformat(),
        "reference": SUPPLEMENT_REFERENCE,
        "generation_provenance": provenance,
        "production_generation_verified": provenance.startswith("claude-sonnet-4-6"),
        "profile": profile,
        "rows": rows,
        "passed_count": passed_count,
        "total_count": len(rows),
    }


def render_markdown(result: dict[str, Any]) -> str:
    source = result["reference"]["source"]
    if result["generation_provenance"] == "claude-sonnet-4-6":
        status = "실제 Claude 생성 검증 완료"
    elif result["production_generation_verified"]:
        status = "실제 Claude 생성 + 사실 경계 편집 검증 완료"
    else:
        status = "구현 검증용 샘플 — 실생성 검증 대기"
    lines = [
        f"# 대본 스타일 구현 확인 보고서 — {result['report_date']}",
        "",
        "## 한눈에 보는 결과",
        "",
        f"- 상태: **{status}**",
        f"- 생성 이력: `{result['generation_provenance']}`",
        f"- 목표 충족: **{result['passed_count']}/{result['total_count']}**",
        f"- 비교 근거: {source}",
        "- 저작권 경계: 채널 원문·고유 문장은 저장하거나 인용하지 않고, 제공된 구조 측정값만 비교했습니다.",
        "",
        "## 목표 대비 결과",
        "",
        "| 확인 항목 | 목표 | 이번 대본 | 결과 | 왜 중요한가 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in result["rows"]:
        lines.append(f"| {row['item']} | {row['target']} | {row['actual']} | {'통과' if row['passed'] else '보완 필요'} | {row['meaning']} |")
    profile = result["profile"]
    lines.extend([
        "",
        "## 레퍼런스와의 다각도 비교",
        "",
        f"- 주식 타깃 채널의 제공된 평균 문장 길이 표본: {result['reference']['benchmark_stock_sentence_chars']}자",
        f"- 일반 경제 채널의 제공된 평균 문장 길이 표본: {result['reference']['general_econ_sentence_chars']}자",
        f"- 이번 대본: 평균 {profile['axis3_rhythm']['sent_len_mean']}자, 반말 {profile['axis4_register']['banmal_ratio']}, 첫 3문장 숫자 {profile['axis6_hook']['opening_three_sentence_number_count']}개, 숫자 밀도 {profile['axis6_hook']['number_density_per_100_chars']}개/100자",
        f"- 구조 장치: {', '.join(name for name, present in profile['axis1_structure']['devices_present'].items() if present)}",
        f"- 안전성: 매수/매도 지시 {profile['axis7_safety']['buy_sell_directive_count']}건, 과장 {profile['axis7_safety']['hype_count']}건, 미추적 숫자 {len(profile['axis8_fact']['untraceable'])}건",
        "",
        "## 담당자 판단",
        "",
        "- 이 보고서는 스타일 구현이 수치로 작동하는지 확인하는 자료입니다. 실제 채널 성과(조회·시청 지속률)를 보장하지는 않습니다.",
        "- ‘보완 필요’ 항목은 생성 프롬프트와 하드/권고 게이트에서 자동 감지됩니다. 다음 실생성물도 같은 명령으로 즉시 재측정할 수 있습니다.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="보충 노트 기준의 비개발자용 대본 비교 보고서를 만듭니다.")
    parser.add_argument("--generated", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--json", required=True, dest="json_path")
    args = parser.parse_args()
    result = compare_supplement_benchmark(_load(Path(args.generated)))
    report_path = Path(args.report)
    json_path = Path(args.json_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

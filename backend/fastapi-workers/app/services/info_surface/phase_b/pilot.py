"""Manual B-0 pilot CLI. Codex integration uses only its dry-run path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from .contracts import HarmonizeRequest
from .harmonizer import harmonize_surface
from .ocr_readers import GeminiVisionReader, MockReader, TesseractReader
from .providers import FalCannyProvider, GeminiEditProvider, IdentityProvider


def _reader(name: str, plan: HarmonizeRequest):
    if name == "tesseract": return TesseractReader()
    if name == "gemini": return GeminiVisionReader()
    return MockReader([item.text for item in plan.expected_texts])


def _provider(name: str, dry_run: bool):
    if dry_run: return IdentityProvider()
    return {"fal_canny": FalCannyProvider, "gemini_edit": GeminiEditProvider}[name]()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True); parser.add_argument("--out", default="pilot_report.md")
    parser.add_argument("--providers", default="fal_canny"); parser.add_argument("--reader", default="mock", choices=["tesseract", "gemini", "mock"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plans = sorted(Path(args.samples).glob("*.plan.json"))
    if not plans:
        print("no samples: expected {scene_id}.png and {scene_id}.plan.json"); return 2
    providers = [item.strip() for item in args.providers.split(",") if item.strip()]
    rows: list[tuple[str, str, str, str, int, float]] = []
    for plan_path in plans:
        scene_id = plan_path.name.removesuffix(".plan.json")
        frame = cv2.imread(str(plan_path.with_name(f"{scene_id}.png")))
        if frame is None:
            rows.append((scene_id, "-", "LOAD_FAIL", "", 0, 0.0)); continue
        plan = HarmonizeRequest.model_validate(json.loads(plan_path.read_text(encoding="utf-8")))
        for name in providers:
            request = plan.model_copy(update={"provider": name})
            result, _ = harmonize_surface(request, frame, _provider(name, args.dry_run), _reader(args.reader, request), output_path=str(Path(args.samples) / "accepted" / f"{scene_id}.{name}.png"))
            gates = " ".join(f"{gate.name}={'P' if gate.passed else 'F'}" for gate in result.gates) or result.fallback_reason[:60]
            rows.append((scene_id, name, "ACCEPT" if result.accepted else "FALLBACK", gates, result.latency_ms, result.cost_estimate_krw))
    lines = ["# Phase B pilot report", "", f"- samples={len(plans)}, providers={providers}, reader={args.reader}, dry_run={args.dry_run}", "", "| scene | provider | decision | gates | latency ms | cost KRW |", "| --- | --- | --- | --- | ---: | ---: |"]
    lines.extend(f"| {scene} | {provider} | {decision} | {gates} | {latency} | {cost:.1f} |" for scene, provider, decision, gates, latency, cost in rows)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"report written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""기존 실패 프레임을 보존한 채 이미지 모델의 국소 보정 성능만 시험한다."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.providers.real.image import NanaBananaProvider
from app.utils.budget import ProviderRequestAudit


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--scene-index", type=int, required=True)
    parser.add_argument("--model", default="gemini-3.1-flash-image")
    parser.add_argument("--image-size", default="2K")
    parser.add_argument("--approved-text", action="append", default=[])
    parser.add_argument("--malformed-text", action="append", default=[])
    parser.add_argument("--face-reference")
    parser.add_argument("--style-reference")
    return parser.parse_args()


def _prompt(*, approved: list[str], malformed: list[str]) -> str:
    approved_line = ", ".join(approved) if approved else "none"
    malformed_line = ", ".join(malformed) if malformed else "all invented or malformed writing"
    return f"""LOCAL CORRECTION OF ATTACHED IMAGE 1 ONLY.
IMAGE 1 is the exact failed full frame. Edit that same frame locally; do not redesign or redraw the whole scene.
IMAGE 2, when supplied, is only a range reference for the established round gold-coin face construction.
IMAGE 3, when supplied, is only a Job-52 style reference for bold variable ink, cel shading, and colorful finance-comic rendering.

Preserve IMAGE 1's successful 16:9 composition, camera, background, physical props, mascot body, face, expression, costume, pose, palette, lighting, and linework.
Correct only the failed text surfaces. Completely remove these malformed strings: {malformed_line}.
Remove all other invented letters, microprint, serial numbers, dates, and numerals. Keep affected paper or equipment visually detailed but unlettered, using borders, seals, icons, chart strokes, and material texture only.
Preserve each already-correct approved string exactly once: {approved_line}.
Do not add any new words, numbers, signs, captions, speech bubbles, thought bubbles, detached cards, logos, or a second character.
The final frame may contain only these readable strings: {approved_line}.
This is a localized restoration of IMAGE 1, not a new illustration."""


def main() -> int:
    args = _arguments()
    job_root = Path(f"/app/data/jobs/{args.job_id}")
    image_dir = job_root / "images"
    rejected = image_dir / f"scene_{args.scene_index:03d}_rejected.png"
    source = rejected if rejected.is_file() else image_dir / f"scene_{args.scene_index:03d}.png"
    if not source.is_file():
        raise FileNotFoundError(f"국소 보정 원본을 찾을 수 없습니다: {source}")

    pilot_dir = job_root / "pilots"
    pilot_dir.mkdir(parents=True, exist_ok=True)
    model_slug = args.model.replace(".", "_").replace("-", "_")
    output = pilot_dir / f"scene_{args.scene_index:03d}_{model_slug}_local_edit.png"
    output.unlink(missing_ok=True)

    references = [str(source)]
    for reference in (args.face_reference, args.style_reference):
        if reference and Path(reference).is_file():
            references.append(reference)

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 또는 GOOGLE_API_KEY가 필요합니다.")

    audit = ProviderRequestAudit.for_job(
        job_id=args.job_id,
        scene_key=f"pilot:{args.model}:scene_{args.scene_index:03d}",
        model=args.model,
    )
    ok = NanaBananaProvider()._generate_gemini_api(
        _prompt(approved=args.approved_text, malformed=args.malformed_text),
        str(output),
        api_key,
        references,
        model=args.model,
        image_size=args.image_size,
        service_tier="standard",
        max_attempts=1,
        retry_base_seconds=5,
        request_audit=audit,
        reference_contract_declared=True,
    )
    print(json.dumps({
        "ok": ok,
        "job_id": args.job_id,
        "scene_index": args.scene_index,
        "model": args.model,
        "source": str(source),
        "output": str(output),
        "size_bytes": output.stat().st_size if output.exists() else 0,
        "approved_texts": args.approved_text,
        "malformed_texts": args.malformed_text,
        "request_audit": audit.summary(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

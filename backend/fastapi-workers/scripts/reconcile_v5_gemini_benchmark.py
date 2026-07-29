#!/usr/bin/env python3
"""Gemini 콘솔 청구액을 P1-b 부분 원장에 명시적으로 대조 기록한다."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "out" / "benchmark" / "gemini_pro" / "_manifest.partial.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual-total-usd", type=float, required=True)
    parser.add_argument("--confirmed-request-count", type=int, required=True)
    args = parser.parse_args()
    if args.actual_total_usd < 0 or args.confirmed_request_count < 0:
        parser.error("실비와 요청 건수는 음수가 될 수 없습니다.")
    if not MANIFEST.exists():
        parser.error(f"부분 원장이 없습니다: {MANIFEST}")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    recovered = [scene for scene in payload["scenes"] if scene["status"] == "recovered_saved_output"]
    payload["reconciliation"] = {
        "actual_total_usd": round(args.actual_total_usd, 6),
        "confirmed_request_count": args.confirmed_request_count,
        "saved_output_count": len(recovered),
        "reconciled_at_utc": datetime.now(timezone.utc).isoformat(),
        "operator_action": "console total entered manually; missing scene retry remains a separate approval decision",
    }
    payload["cost_status"] = "console_reconciled"
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS 콘솔 대조 기록: ${args.actual_total_usd:.6f}, 요청 {args.confirmed_request_count}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

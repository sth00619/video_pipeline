"""원장 HTTP 결과와 독립 QA 스냅샷을 분리한 읽기 전용 시계열 감사."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--scene-index", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--container", help="과거 로그가 남아 있는 읽기 전용 Docker 컨테이너")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source = args.job_dir / "cost_ledger.json"
    ledger = json.loads(source.read_text())
    rows = sorted(
        (item for item in ledger["items"] if item.get("scene_key") == f"image:{args.scene_index}"),
        key=lambda item: item["reserved_at"],
    )
    qa = []
    for path in sorted((args.job_dir / "images").glob("visual_qa_cache.json*")):
        record = json.loads(path.read_text()).get(str(args.scene_index))
        if record:
            qa.append({"source": path.name, "source_sha256": sha256(path), "record": record})
    events = []
    retry_lines = []
    if args.container:
        result = subprocess.run([
            "docker", "logs", "--timestamps", "--since", rows[0]["reserved_at"],
            "--until", (datetime.fromisoformat(rows[-1].get("completed_at", rows[-1]["reserved_at"])) + timedelta(seconds=2)).isoformat(),
            args.container,
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
        logs = result.stdout.splitlines()
        for index, line in enumerate(logs):
            if f"Image scene {args.scene_index} attempt" in line or f"scene={args.scene_index} error=" in line:
                retry_lines.append(line)
            if "app.providers.real.image:Gemini image" not in line or "HTTP" not in line:
                continue
            parts = line.split(" ", 1)
            if not line.endswith("{"):
                continue
            body = ["{"]
            for following in logs[index + 1:index + 7]:
                body.append(following.split(" ", 1)[-1])
            try:
                error = json.loads("\n".join(body))["error"]
                events.append({"timestamp": parts[0], "error": {k: error.get(k) for k in ("code", "status", "message")}})
            except (ValueError, KeyError):
                continue
        for row in rows:
            completed = row.get("completed_at")
            if not completed:
                continue
            matches = [e for e in events if e["error"]["code"] == row.get("status_code") and
                       abs((datetime.fromisoformat(e["timestamp"]) - datetime.fromisoformat(completed)).total_seconds()) < 2]
            if len(matches) == 1:
                row["correlated_provider_log"] = matches[0]
                row["log_linkage"] = "same_status_and_completion_within_2s_not_request_id"
    # 요청에 image_sha256/QA event ID가 없어 과거 성공 응답과 캐시를 임의 결합하지 않는다.
    report = {
        "source_sha256": sha256(source),
        "source_path": f"/app/data/jobs/54/cost_ledger.json",
        "scene_key": f"image:{args.scene_index}",
        "request_count": len(rows), "http_status_counts": dict(Counter(r["status"] for r in rows)),
        "qa_attempt_linkage": "unavailable",
        "ledger_amount_krw": sum(r["amount_krw"] for r in rows),
        "billing_verified": False,
        "ledger_excerpt": rows, "qa_snapshots": qa,
        "provider_error_events": events, "worker_retry_log_lines": retry_lines,
    }
    (args.output_dir / "scene-request-timeline.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = [
        f"# Job 54 scene {args.scene_index:02d} 요청 시계열",
        "", f"원장 SHA-256: `{sha256(source)}`", "",
        f"전체 {len(rows)}회: `{dict(Counter(r['status'] for r in rows))}`.", "",
        "HTTP 200은 공급자 응답 성공일 뿐 QA 통과/거절을 뜻하지 않는다. reserved는 결과 미상이다.",
        "503/504는 HTTP 단계 실패다. 공급자 로그 오류 본문은 상태·완료 시각 ±2초로 연결했으며 요청 ID로 연결한 것은 아니다. payload hash·응답 이미지 hash·QA event 연결은 없다.",
        "금액은 로컬 추정 원장이고 공급자 청구 확정액이 아니다. 실패 0원 처리도 공급자 청구가 없었다는 증거가 아니다.", "",
        "| 순서 | 시작 KST | 소요 초 | 호출 내부 attempt | HTTP 결과/공급자 사유 | QA 연결 | 원장 원 | attempt_id |",
        "|---:|---|---:|---:|---|---|---:|---|",
    ]
    for index, row in enumerate(rows, 1):
        start = datetime.fromisoformat(row["reserved_at"])
        end = datetime.fromisoformat(row["completed_at"]) if row.get("completed_at") else None
        seconds = f"{(end - start).total_seconds():.3f}" if end else "미상"
        qa_state = "미기록" if row["status"] == "http_200" else "판정 불가/응답 없음"
        provider_reason = row.get("correlated_provider_log", {}).get("error", {}).get("status", "미기록")
        lines.append(f"| {index} | {start.astimezone(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')} | {seconds} | {row['attempt']} | {row['status']} / {provider_reason} | {qa_state} | {row['amount_krw']} | `{row['attempt_id']}` |")
    lines.extend(["", "## 별도 QA 증거", ""])
    for snapshot in qa:
        record = snapshot["record"]
        lines.extend([
            f"- 파일: `{snapshot['source']}`",
            f"- 정책 {record.get('policy_version')}, 점수 {record.get('score')}, 판정 `{record.get('raw', {}).get('decision')}`, retry={record.get('retry_recommended')}",
            f"- 이미지 SHA-256: `{record.get('image_sha256')}`",
            f"- 사유: {record.get('reason')}", "",
        ])
    lines.extend([
        "이 스냅샷은 장면별 품질 판정이 존재한다는 증거지만 요청 ID와 연결되지 않으므로 47회 중 어느 요청의 QA인지 확정하지 않는다.", "",
        "## 해석과 우선 조치", "",
        "- 반복의 대부분은 QA 거절이 아니라 503/504다. 품질 거절이 47회를 유발했다는 가설은 입증되지 않았다.",
        "- attempt=1/2가 반복되므로 호출 내부 한도만으로 상위 재실행을 제한하지 못했다. 동일 장면/계약의 누적 한도와 재개 승인 게이트가 필요하다.",
        "- 503 로그는 UNAVAILABLE/high demand, 504 로그는 DEADLINE_EXCEEDED다. 워커 로그의 attempt 1/4와 공급자 attempt 1/2는 중첩 재시도를 입증한다. 이는 payload가 원인이라는 증거는 아니다.",
        "- 횟수 한도 도달 시 장면을 needs_review로 격리하고 다른 장면으로 진행할 수 있으나 누락 장면을 승인하거나 조립해서는 안 된다.",
        "- 공급자 HTTP 실패, 시각 QA 실패, surface 실패의 카운터와 원인을 분리한다. Job 54는 이력 보존만 하고 재개하지 않는다.", "",
    ])
    (args.output_dir / "scene-request-timeline.md").write_text("\n".join(lines))
    print(json.dumps({k: v for k, v in report.items() if k not in {"ledger_excerpt", "qa_snapshots", "provider_error_events", "worker_retry_log_lines"}}, ensure_ascii=False, indent=2))
    print(f"공급자 오류 로그 연결: {sum('correlated_provider_log' in r for r in rows)}회")


if __name__ == "__main__":
    main()

"""스프링 작업에 저장된 실제 스크립트의 장면 유형만 안전하게 재균형화한다.

대본과 검증 사실은 변경하지 않으며, ``script/confirm`` 게이트를 다시 통과시켜
운영과 동일한 하우스스타일 검증을 유지한다. 비밀번호와 토큰은 파일에 남기지
않고 실행 인자로만 받는다.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys

import httpx

from app.workers.script_worker import _classify_scene_types


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="스프링 작업 스크립트 장면 유형 재균형화")
    parser.add_argument("--spring-url", required=True)
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _distribution(sections: list[dict]) -> dict[str, int]:
    return dict(sorted(Counter(str(section.get("scene_type") or "unknown") for section in sections).items()))


def main() -> int:
    args = _parse_args()
    base_url = args.spring_url.rstrip("/")

    with httpx.Client(timeout=120.0) as client:
        login = client.post(
            f"{base_url}/api/auth/login",
            json={"username": args.username, "password": args.password},
        )
        login.raise_for_status()
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        assets_response = client.get(
            f"{base_url}/api/jobs/{args.job_id}/assets",
            params={"type": "SCRIPT"},
            headers=headers,
        )
        assets_response.raise_for_status()
        assets = assets_response.json()
        if not assets:
            raise RuntimeError(f"SCRIPT 자산이 없습니다: job_id={args.job_id}")

        # API의 반환 순서는 저장소 구현에 따라 달라질 수 있다. 가장 늦게 저장된
        # 대본만 대상으로 해야 오래된 초안을 확정하는 사고를 막을 수 있다.
        latest_asset = max(assets, key=lambda asset: str(asset.get("createdAt") or ""))
        source = latest_asset.get("metaJson")
        if not source:
            raise RuntimeError(f"SCRIPT 자산 메타데이터가 비어 있습니다: job_id={args.job_id}")
        payload = json.loads(source)
        sections = payload.get("sections") or []
        script = payload.get("script") or payload.get("fullScript")
        if not sections or not script:
            raise RuntimeError("재균형화에 필요한 script 또는 sections가 없습니다.")

        rebalanced = _classify_scene_types(sections)
        result = {
            "job_id": args.job_id,
            "script_asset_id": latest_asset.get("id"),
            "before": _distribution(sections),
            "after": _distribution(rebalanced),
            "section_count": len(rebalanced),
            "dry_run": args.dry_run,
        }
        print(json.dumps(result, ensure_ascii=False))
        if args.dry_run:
            return 0

        confirm = client.post(
            f"{base_url}/api/jobs/{args.job_id}/script/confirm",
            headers=headers,
            json={
                "finalScript": script,
                "sections": rebalanced,
                "comment": "장문 시각 유형 분포 재균형화",
            },
        )
        confirm.raise_for_status()
        print(json.dumps({"confirm": confirm.json()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as error:
        print(f"재균형화 실패: {error}", file=sys.stderr)
        raise SystemExit(1)

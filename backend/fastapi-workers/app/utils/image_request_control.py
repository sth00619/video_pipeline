"""이미지 POST의 단일 재시도 소유자. 동일 공유 볼륨의 프로세스 간 예약을 직렬화한다."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import sqlite3
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from app import runtime_config


class ImageRequestHeld(RuntimeError):
    """새 POST 없이 영속 상태를 보존하고 호출자를 반환한다."""

    def __init__(self, reason: str, *, status: str = "needs_review", next_allowed_at: float = 0):
        self.reason = reason
        self.status = status
        self.next_allowed_at = next_allowed_at
        super().__init__(f"이미지 요청 보류: {reason}; 상태={status}; 재개가능시각={next_allowed_at:.3f}")


def canonical_scene(key: str) -> str:
    """원본·배경·표면 재생성이 동일 장면 상한을 공유한다. 계약 hash는 키에 넣지 않는다."""
    # 보조 파일럿도 scene_021 형식을 사용한다. 구분자나 0 채움으로 한도가
    # 분리되지 않게 하되, 임의 이름의 끝 숫자를 다른 장면으로 합치지 않는다.
    match = re.search(r"(?:^|:)(?:image|background|template_regen|scene)[:_-](\d+)(?::variation:\d+)?$", key)
    return f"scene:{int(match[1])}" if match else key


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_request_review(job_dir: Path, job_id: int, held: list[dict]) -> None:
    """이미지 요청 단계의 미완료 상태를 남긴다. cleared는 전체 영상 승인과 다르다."""
    path = job_dir / "image_request_review.json"
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps({"job_id": job_id, "requires_manual_review": bool(held),
        "request_gate_cleared": not held, "assembly_allowed": not held, "scenes": held}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(staged, path)


def assert_request_review_cleared(job_id: int, root: Path = Path("/app/data/jobs")) -> None:
    """조립을 직접 호출해 보류 장면을 우회하지 못하게 한다. 기존 작업은 기존 검증을 유지한다."""
    path = root / str(job_id) / "images" / "image_request_review.json"
    if not path.exists():
        return
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ImageRequestHeld("이미지 보류 상태 파일을 검증할 수 없음") from exc
    if not isinstance(review, dict) or review.get("job_id") != job_id or review.get("request_gate_cleared") is not True or review.get("scenes"):
        raise ImageRequestHeld("미완료 이미지 요청 존재; Fal/조립 진입 차단")


def payload_evidence(payload: dict, *, endpoint: str, model: str, tier: str) -> dict:
    """전송 본문을 그대로 해시하되 키·base64·프롬프트 원문은 저장하지 않는다."""
    import base64
    parts = payload["contents"][0]["parts"]
    return {
        "endpoint": endpoint, "model": model, "service_tier": tier,
        "payload_hash_basis": "canonical_json_utf8_sorted_keys",
        "payload_sha256": digest(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()),
        "prompt_sha256": digest("\n".join(p["text"] for p in parts if "text" in p).encode()),
        "references": [
            {"sha256": digest(base64.b64decode(p["inlineData"]["data"])),
             "byte_count": len(base64.b64decode(p["inlineData"]["data"])),
             "mime_type": p["inlineData"]["mimeType"]}
            for p in parts if "inlineData" in p
        ],
    }


def retry_after_seconds(value: str | None, now: float) -> float:
    if not value:
        return 0.0
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            dt = parsedate_to_datetime(value)
            seconds = dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp() - now
        except (ValueError, TypeError, OverflowError):
            return 0.0
    return max(0.0, seconds) if math.isfinite(seconds) else 0.0


class ImageRequestControl:
    """BEGIN IMMEDIATE로 검사와 점유를 원자화한다. 예약의 자동 만료/카운터 초기화는 없다."""

    def __init__(self, *, path: Path | None = None, clock=None, uniform=None):
        cfg = runtime_config.get()
        from app import config
        self.path = path or Path(cfg.get("gemini_request_state_path", config.GEMINI_REQUEST_STATE_PATH))
        self.project = str(cfg.get("gemini_project_scope", "default"))
        self.limit = min(3, max(1, int(cfg.get("gemini_scene_request_limit", 3))))
        self.base = max(1.0, float(cfg.get("gemini_pro_retry_base_seconds", 20)))
        self.clock = clock or time.time
        self.uniform = uniform or random.uniform

    def _db(self):
        db = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS scenes (scope TEXT, scene TEXT, count INTEGER, n INTEGER, next REAL, active TEXT, status TEXT, PRIMARY KEY(scope, scene))")
            db.execute("CREATE TABLE IF NOT EXISTS projects (name TEXT PRIMARY KEY, n INTEGER, next REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, scope TEXT, scene TEXT, project TEXT, completed INTEGER DEFAULT 0)")
            db.execute("BEGIN IMMEDIATE")
            return db
        except (OSError, sqlite3.Error) as exc:
            if db is not None:
                db.close()
            raise ImageRequestHeld("영속 요청 상태 저장소를 사용할 수 없음") from exc

    def reserve(self, *, scope: str, scene: str, token: str, legacy_count: int = 0,
                review_retry_of: str | None = None, expected_failure_n: int | None = None) -> dict:
        scene = canonical_scene(scene)
        db = self._db()
        try:
            row = db.execute("SELECT count,n,next,active,status FROM scenes WHERE scope=? AND scene=?", (scope, scene)).fetchone()
            count, n, deadline, active, status = row or (0, 0, 0, None, "ready")
            count = max(count, legacy_count)
            if count >= self.limit:
                db.execute("INSERT OR REPLACE INTO scenes VALUES (?,?,?,?,?,?,?)", (scope, scene, count, n, deadline, active, "needs_review"))
                db.commit()
                raise ImageRequestHeld("장면 누적 요청 상한 도달")
            if active:
                raise ImageRequestHeld("응답 미확정 예약 존재; 자동 재요청 금지")
            if review_retry_of:
                # 감사 원장이 검증한 단일 승인만 받는다. 상태 삭제/카운터 리셋 없이
                # 직전 완료 요청의 다음 슬롯을 같은 트랜잭션에서 점유한다.
                previous = db.execute(
                    "SELECT id,completed,project FROM attempts WHERE scope=? AND scene=? ORDER BY rowid DESC LIMIT 1",
                    (scope, scene)).fetchone()
                if (previous != (review_retry_of, 1, self.project) or count != legacy_count
                        or n != expected_failure_n or n < 1):
                    raise ImageRequestHeld("승인 재시도의 직전 요청/실패 이력 불일치")
            if status == "needs_review" and not review_retry_of:
                raise ImageRequestHeld("영구 오류 또는 검수 차단 상태")
            project = db.execute("SELECT n,next FROM projects WHERE name=?", (self.project,)).fetchone()
            deadline = max(deadline, project[1] if project else 0)
            if self.clock() < deadline:
                raise ImageRequestHeld("냉각시간 미경과", status="deferred", next_allowed_at=deadline)
            db.execute("INSERT OR REPLACE INTO scenes VALUES (?,?,?,?,?,?,?)", (scope, scene, count + 1, n, deadline, token, "reserved"))
            db.execute("INSERT INTO attempts(id,scope,scene,project) VALUES (?,?,?,?)", (token, scope, scene, self.project))
            db.commit()
            return {"scene_attempt": count + 1, "failure_n": n, "scene": scene, "project_scope": self.project}
        finally:
            db.close()

    def finish(self, token: str, *, retryable: bool, permanent: bool = False, retry_after: str | None = None) -> dict:
        db = self._db()
        try:
            attempt = db.execute("SELECT scope,scene,project,completed FROM attempts WHERE id=?", (token,)).fetchone()
            if not attempt:
                raise ImageRequestHeld("영속 예약 식별자 없음")
            scope, scene, project, completed = attempt
            count, n, deadline, active, status = db.execute("SELECT count,n,next,active,status FROM scenes WHERE scope=? AND scene=?", (scope, scene)).fetchone()
            if not completed:
                if active != token:
                    raise ImageRequestHeld("예약 소유권 불일치")
                if retryable:
                    pn, pnext = db.execute("SELECT n,next FROM projects WHERE name=?", (project,)).fetchone() or (0, 0)
                    # 프로젝트 연쇄 실패도 영속화한다. 상한 이후에도 equal jitter를 유지한다.
                    b = min(300.0, self.base * 2 ** min(max(n, pn), 20))
                    delay = max(self.uniform(b / 2, b), retry_after_seconds(retry_after, self.clock()))
                    deadline = max(deadline, pnext, self.clock() + delay)
                    n += 1
                    db.execute("INSERT OR REPLACE INTO projects VALUES (?,?,?)", (project, pn + 1, deadline))
                status = "needs_review" if permanent or (retryable and count >= self.limit) else ("deferred" if retryable else "ready")
                db.execute("UPDATE scenes SET n=?,next=?,active=NULL,status=? WHERE scope=? AND scene=?", (n, deadline, status, scope, scene))
                db.execute("UPDATE attempts SET completed=1 WHERE id=?", (token,))
                db.commit()
            return {"scene_attempt": count, "failure_n": n, "next_allowed_at": deadline, "status": status}
        finally:
            db.close()

    def assert_dispatchable(self, token: str) -> None:
        """예약 후 다른 워커가 503을 받은 경우에도 POST 직전에 공유 냉각을 확인한다."""
        db = self._db()
        try:
            row = db.execute("SELECT project,completed FROM attempts WHERE id=?", (token,)).fetchone()
            if not row or row[1]:
                raise ImageRequestHeld("유효한 미완료 예약 없음")
            project = db.execute("SELECT next FROM projects WHERE name=?", (row[0],)).fetchone()
            if project and self.clock() < project[0]:
                raise ImageRequestHeld("공유 프로젝트 냉각", status="deferred", next_allowed_at=project[0])
        finally:
            db.close()

"""
Job 중지/프로세스 관리.

[버그 수정 - 중요] 기존에는 stopped_job_ids가 순수 파이썬 프로세스 메모리 안의
set()이었습니다. FastAPI(uvicorn)가 워커를 여러 개(--workers N, N>1)로 띄우면
각 워커가 완전히 독립된 메모리 공간을 가지므로, 정지 요청을 받은 워커의
stopped_job_ids에는 job_id가 추가되지만, 실제로 이미지 생성 루프를 돌리고
있는 다른 워커는 그 사실을 전혀 알 수 없었습니다. 그 결과 "정지" 버튼을
눌러도 실제 작업은 계속 돌아가는 문제가 있었습니다.

이제 정지 플래그는 Redis에 저장합니다. Redis는 모든 워커 프로세스가 공유하는
외부 저장소라, 워커가 몇 개든 상관없이 정지 신호가 확실히 전파됩니다.

active_processes(실행 중인 subprocess 핸들)는 여전히 프로세스 로컬 메모리에
둡니다 — 어차피 subprocess.Popen 객체 자체는 그 프로세스를 실제로 만든
워커만 kill()할 수 있고, 다른 워커로 넘길 수 없는 성격이라 Redis로 옮겨봐야
의미가 없습니다. 대신 is_job_stopped()를 폴링하는 모든 루프(images_worker,
tts_worker, longform_worker 등)가 Redis를 통해 정지 여부를 정확히 알 수
있으므로, "새 작업을 시작하지 않는다"는 동작은 워커 전체에서 보장됩니다.

Redis 연결 자체가 실패하는 예외 상황에서는 in-memory 폴백으로 동작합니다
(그 경우 멀티 워커 환경에서는 정지가 불완전할 수 있다는 점을 로그로 경고합니다).
"""
import os
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STOP_KEY_PREFIX = "job:stopped:"
STOP_KEY_TTL_SECONDS = 60 * 60 * 24  # 1일 후 자동 정리 (좀비 플래그 방지)

_redis_client = None
_redis_unavailable = False  # 한 번 연결 실패하면 매번 재시도하지 않도록 캐시


def _get_redis():
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is None:
        try:
            import redis as redis_lib
            _redis_client = redis_lib.Redis(
                host=REDIS_HOST, port=REDIS_PORT,
                decode_responses=True, socket_connect_timeout=2,
            )
            _redis_client.ping()
            logger.info(f"process_manager: Redis 연결 성공 ({REDIS_HOST}:{REDIS_PORT})")
        except Exception as e:
            logger.error(
                f"process_manager: Redis 연결 실패 — in-memory 폴백 사용. "
                f"멀티 워커 환경이면 정지 신호가 일부 워커에 전파 안 될 수 있습니다: {e}"
            )
            _redis_unavailable = True
            return None
    return _redis_client


# in-memory 폴백 (Redis 연결 실패 시에만 사용됨. 단일 워커 환경에서만 완전히 유효)
_local_stopped_job_ids = set()

# 실행 중인 subprocess 핸들 — 프로세스 로컬로 유지 (Redis로 옮길 수 없는 성격)
active_processes = defaultdict(list)


def is_job_stopped(job_id: int) -> bool:
    """해당 작업이 중지되었는지 확인 (모든 워커 프로세스에서 동일하게 조회됨)"""
    if not job_id:
        return False
    j_id = int(job_id)

    r = _get_redis()
    if r is not None:
        try:
            return r.exists(f"{STOP_KEY_PREFIX}{j_id}") == 1
        except Exception as e:
            logger.warning(f"Job {j_id} 정지 상태 Redis 조회 실패, in-memory 폴백: {e}")

    return j_id in _local_stopped_job_ids


def register_process(job_id: int, process):
    """실행 중인 프로세스 등록 (이 워커 프로세스 내에서만 유효)"""
    if job_id:
        active_processes[int(job_id)].append(process)
        logger.debug(f"Job {job_id} 프로세스 등록 완료 (PID: {process.pid})")


def unregister_process(job_id: int, process):
    """프로세스 제거"""
    if job_id and int(job_id) in active_processes:
        try:
            active_processes[int(job_id)].remove(process)
            logger.debug(f"Job {job_id} 프로세스 제거 완료 (PID: {process.pid})")
        except ValueError:
            pass


def stop_job_processes(job_id: int):
    """
    작업 중지 플래그를 Redis에 기록하고(모든 워커 프로세스가 즉시 조회 가능),
    이 워커 프로세스에서 등록된 활성 프로세스가 있으면 강제 종료합니다.
    """
    if not job_id:
        return
    j_id = int(job_id)

    r = _get_redis()
    if r is not None:
        try:
            r.setex(f"{STOP_KEY_PREFIX}{j_id}", STOP_KEY_TTL_SECONDS, "1")
            logger.info(f"Job {j_id} 중지 플래그 Redis에 기록 완료 (모든 워커에 공유됨).")
        except Exception as e:
            logger.error(f"Job {j_id} 정지 플래그 Redis 기록 실패, in-memory 폴백: {e}")
            _local_stopped_job_ids.add(j_id)
    else:
        _local_stopped_job_ids.add(j_id)
        logger.warning(f"Job {j_id} 정지 플래그를 in-memory에만 기록함 (Redis 사용 불가 상태).")

    processes = active_processes.get(j_id, [])
    if processes:
        logger.info(f"Job {j_id} 활성 프로세스 {len(processes)}개 강제 종료 시작 (이 워커 프로세스 내)...")
        for p in list(processes):
            try:
                p.kill()
                logger.info(f"Job {j_id} 프로세스 강제 종료 성공 (PID: {p.pid})")
            except Exception as e:
                logger.error(f"Job {j_id} 프로세스 종료 중 오류: {e}")
        active_processes[j_id] = []

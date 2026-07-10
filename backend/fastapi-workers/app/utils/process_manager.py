import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# 전역 중지 관리 저장소
stopped_job_ids = set()
active_processes = defaultdict(list)

def is_job_stopped(job_id: int) -> bool:
    """해당 작업이 중지되었는지 확인"""
    if not job_id:
        return False
    return int(job_id) in stopped_job_ids

def register_process(job_id: int, process):
    """실행 중인 프로세스 등록"""
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
    """작업에 속한 모든 프로세스를 중지하고 강제 종료"""
    if not job_id:
        return
    j_id = int(job_id)
    stopped_job_ids.add(j_id)
    logger.info(f"Job {j_id} 중지 상태 등록 완료.")
    
    processes = active_processes.get(j_id, [])
    if processes:
        logger.info(f"Job {j_id} 활성 프로세스 {len(processes)}개 강제 종료 시작...")
        for p in list(processes):
            try:
                p.kill()
                logger.info(f"Job {j_id} 프로세스 강제 종료 성공 (PID: {p.pid})")
            except Exception as e:
                logger.error(f"Job {j_id} 프로세스 종료 중 오류: {e}")
        # 리스트 클리어
        active_processes[j_id] = []

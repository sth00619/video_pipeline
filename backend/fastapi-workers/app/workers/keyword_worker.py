"""
Phase 3-1 — 키워드 탐색 워커
"""
import logging
from app.providers.factory import get_keyword_tool_provider

logger = logging.getLogger(__name__)


class KeywordWorker:
    def __init__(self):
        self.provider = get_keyword_tool_provider()

    def search(self, seed: str, limit: int = 5, job_id: int = 0) -> dict:
        logger.info(f"키워드 탐색 시작: seed={seed}, limit={limit}, job_id={job_id}")
        items = self.provider.search(seed, limit)

        candidates = [
            {
                "keyword": it.keyword,
                "search_volume": it.search_volume,
                "competition": it.competition,
                "reason": it.reason,
            }
            for it in items
        ]
        logger.info(f"키워드 후보 {len(candidates)}개 생성 완료")

        return {
            "job_id": job_id,
            "seed": seed,
            "candidates": candidates,
        }

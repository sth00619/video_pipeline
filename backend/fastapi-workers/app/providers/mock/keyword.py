"""
Mock 키워드 탐색 — 실제 KeywordTool.io API 대신 더미 데이터 반환
Phase 3-1 단계에서 흐름 테스트용. Phase 3 실가동 시 RealKeywordToolProvider로 교체.
"""
import random
from app.providers.base import KeywordToolProvider, KeywordItem


# 영상 주제별 흔한 suffix 패턴
KO_SUFFIXES = [
    "완벽 가이드", "방법 정리", "추천 BEST", "초보자용", "꿀팁 10가지",
    "총정리", "후기", "비교", "어떻게 시작할까", "가장 쉬운"
]
COMPETITION_LEVELS = ["LOW", "MEDIUM", "HIGH"]


class MockKeywordToolProvider(KeywordToolProvider):

    def search(self, seed: str, limit: int = 5) -> list[KeywordItem]:
        if not seed or not seed.strip():
            seed = "AI"

        random.seed(hash(seed) % (2**32))
        suffixes = random.sample(KO_SUFFIXES, k=min(limit, len(KO_SUFFIXES)))

        result = []
        for i, suffix in enumerate(suffixes):
            keyword = f"{seed} {suffix}"
            search_volume = random.randint(800, 50000)
            competition = random.choice(COMPETITION_LEVELS)
            reason = self._reason(competition, search_volume)
            result.append(KeywordItem(
                keyword=keyword,
                search_volume=search_volume,
                competition=competition,
                reason=reason
            ))

        # 검색량 내림차순 정렬
        result.sort(key=lambda x: x.search_volume, reverse=True)
        return result

    @staticmethod
    def _reason(competition: str, volume: int) -> str:
        if competition == "LOW" and volume > 5000:
            return "경쟁 낮고 수요 충분 — 우선 추천"
        if competition == "MEDIUM" and volume > 10000:
            return "수요 높음, 적정 경쟁도"
        if competition == "HIGH":
            return "경쟁 치열 — 차별화 필요"
        return "보조 키워드로 활용 가능"

"""
Phase 3-1 — 키워드 탐색 워커 (주식 콘텐츠 특화)

7단계 흐름 (Mock과 Real이 동일한 구조):
  1. 트렌딩 영상 풀 수집 (analyzer.collect)
  2-3. 통계 통합 (Mock은 collect에서 일괄, Real은 videos.list + channels.list)
  4. 평가 지표 계산 (구독자 대비 / 채널 평균 대비 / 시간당 조회수)
  5. 종합 점수 기준 정렬
  6. 제목에서 키워드 패턴 추출
  7. outperformer 표시 + 후보 생성
"""
import logging
import re
from app.providers.factory import get_trending_video_analyzer

logger = logging.getLogger(__name__)


class KeywordWorker:
    def __init__(self):
        self.analyzer = get_trending_video_analyzer()

    def search(self, category: str, seed: str, limit: int = 5,
               outperformer_count: int = 1, job_id: int = 0) -> dict:

        logger.info(f"키워드 탐색: category={category}, seed={seed}, "
                    f"limit={limit}, outperformer={outperformer_count}, job_id={job_id}")

        # 1-3. 트렌딩 영상 풀 수집 (Mock은 통계까지 일괄)
        videos = self.analyzer.collect(category, seed or "", limit=30)

        # 4. 평가 지표 계산
        scored = []
        for v in videos:
            engagement_ratio = round(v.views / max(v.subscribers, 1), 3)
            outperformance_index = round(v.views / max(v.channel_avg_views, 1), 2)
            velocity_vph = round(v.views / max(v.hours_since_publish, 0.1), 1)

            # 종합 점수: 3지표 가중 평균 (정규화 후)
            composite_score = (
                min(engagement_ratio * 0.3, 3.0) +
                min(outperformance_index * 0.4, 4.0) +
                min(velocity_vph / 100, 3.0) * 0.3
            )

            scored.append({
                "video": v,
                "engagement_ratio": engagement_ratio,
                "outperformance_index": outperformance_index,
                "velocity_vph": velocity_vph,
                "composite_score": composite_score,
            })

        # 5. 점수 내림차순 정렬
        scored.sort(key=lambda x: x["composite_score"], reverse=True)

        # 6-7. 상위 영상에서 키워드 후보 추출 + outperformer 표시
        candidates = []
        seen = set()
        for idx, item in enumerate(scored):
            if len(candidates) >= limit:
                break

            keyword = self._extract_keyword(item["video"].title)
            if keyword in seen:
                continue
            seen.add(keyword)

            is_outperformer = idx < outperformer_count

            candidates.append({
                "keyword": keyword,
                "search_volume": int(item["video"].views * 1.5),  # 추정치
                "competition": self._estimate_competition(item["composite_score"]),
                "reason": self._build_reason(item, is_outperformer),
                "engagement_ratio": item["engagement_ratio"],
                "outperformance_index": item["outperformance_index"],
                "velocity_vph": item["velocity_vph"],
                "is_outperformer": is_outperformer,
                "source_videos": [{
                    "title": item["video"].title,
                    "channel_title": item["video"].channel_title,
                    "views": item["video"].views,
                    "subscribers": item["video"].subscribers,
                    "hours_since_publish": item["video"].hours_since_publish,
                }],
            })

        logger.info(f"키워드 후보 {len(candidates)}개 생성, outperformer={outperformer_count}개")

        return {
            "job_id": job_id,
            "seed": seed,
            "category": category,
            "candidates": candidates,
        }

    @staticmethod
    def _extract_keyword(title: str) -> str:
        """제목에서 키워드 추출 (Mock은 제목 그대로, Real은 NLP)"""
        return title.strip()

    @staticmethod
    def _estimate_competition(composite_score: float) -> str:
        if composite_score >= 5.0:
            return "HIGH"
        if composite_score >= 2.5:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _build_reason(item: dict, is_outperformer: bool) -> str:
        marker = "⭐ Outperformer · " if is_outperformer else ""
        return (
            f"{marker}채널 평균 대비 {item['outperformance_index']:.1f}배 조회수, "
            f"시간당 {item['velocity_vph']:.0f}회 시청, "
            f"구독자 대비 {item['engagement_ratio']:.2f}배"
        )

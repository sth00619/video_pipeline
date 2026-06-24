package com.pipeline.video.service;

import com.pipeline.video.domain.Autonomy;
import com.pipeline.video.domain.GateName;
import com.pipeline.video.domain.VideoJob;
import org.springframework.stereotype.Service;

import java.util.Set;

/**
 * 자율성 다이얼 분기 결정 헬퍼.
 *
 *  MANUAL : 모든 게이트 사람 승인
 *  GUIDED : 콘텐츠 결정 + 미리보기만 사람 (KEYWORD, PREVIEW, SHORTS_SEGMENTS, SHORTS_PREVIEW)
 *  AUTO   : 모든 게이트 자동 승인
 */
@Service
public class AutonomyService {

    private static final Set<GateName> GUIDED_HUMAN_GATES = Set.of(
            GateName.KEYWORD,
            GateName.PREVIEW,
            GateName.SHORTS_SEGMENTS,
            GateName.SHORTS_PREVIEW
    );

    public boolean shouldAutoApprove(VideoJob job, GateName gate) {
        Autonomy autonomy = job.getAutonomy();
        if (autonomy == null) return false;
        return switch (autonomy) {
            case AUTO -> true;
            case MANUAL -> false;
            case GUIDED -> !GUIDED_HUMAN_GATES.contains(gate);
        };
    }

    public boolean isAuto(VideoJob job) {
        return job.getAutonomy() == Autonomy.AUTO;
    }
}

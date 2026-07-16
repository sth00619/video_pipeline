package com.pipeline.video.service;

import com.pipeline.video.domain.Autonomy;
import com.pipeline.video.domain.GateName;
import com.pipeline.video.domain.VideoJob;
import org.springframework.stereotype.Service;

import java.util.Set;

/**
 * 자율성 다이얼 분기 결정 헬퍼.
 *
 *  GUIDED : 키워드·스크립트·TTS·이미지·미리보기를 사람 승인
 *  AUTO   : 모든 게이트 자동 승인
 */
@Service
public class AutonomyService {

    private static final Set<GateName> GUIDED_HUMAN_GATES = Set.of(
            GateName.KEYWORD,
            GateName.SCRIPT,
            GateName.TTS,
            GateName.IMAGES,
            GateName.PREVIEW,
            GateName.SHORTS_SEGMENTS,
            GateName.SHORTS_PREVIEW
    );

    public boolean shouldAutoApprove(VideoJob job, GateName gate) {
        Autonomy autonomy = job.getAutonomy();
        if (autonomy == null) return false;
        return switch (autonomy) {
            case AUTO -> true;
            // Legacy rows are treated as GUIDED after the two-mode migration.
            case MANUAL -> !GUIDED_HUMAN_GATES.contains(gate);
            case GUIDED -> !GUIDED_HUMAN_GATES.contains(gate);
        };
    }

    public boolean isAuto(VideoJob job) {
        return job.getAutonomy() == Autonomy.AUTO;
    }
}

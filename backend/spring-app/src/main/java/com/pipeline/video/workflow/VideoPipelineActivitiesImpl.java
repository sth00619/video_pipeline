package com.pipeline.video.workflow;

import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.repository.VideoJobRepository;
import com.pipeline.video.service.ImagesService;
import com.pipeline.video.service.JobService;
import com.pipeline.video.service.LongformService;
import com.pipeline.video.service.ScriptService;
import com.pipeline.video.service.TtsService;
import io.temporal.spring.boot.ActivityImpl;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

/**
 * VideoPipelineActivities 구현체.
 *
 * 각 Activity는 기존 Spring 서비스 메서드를 그대로 위임 호출합니다.
 * 비즈니스 로직은 전혀 건드리지 않습니다.
 *
 * Temporal이 Activity를 관리하므로:
 * - 실패 시 자동 재시도 (RetryPolicy는 Workflow에서 설정)
 * - 완료된 Activity는 Temporal 이력에 기록되어 재시작 후 건너뜀
 * - Heartbeat를 통해 장시간 실행 Activity의 진행상황을 추적 가능
 */
@Component
@ActivityImpl(taskQueues = "video-pipeline-queue")
@Slf4j
@RequiredArgsConstructor
public class VideoPipelineActivitiesImpl implements VideoPipelineActivities {

    private final ScriptService scriptService;
    private final TtsService ttsService;
    private final ImagesService imagesService;
    private final LongformService longformService;
    private final JobService jobService;
    private final VideoJobRepository jobRepository;

    @Override
    public void generateScript(Long jobId) {
        log.info("[Temporal Activity] 스크립트 생성 시작: jobId={}", jobId);
        scriptService.generate(jobId, "AUTO");
        log.info("[Temporal Activity] 스크립트 생성 완료: jobId={}", jobId);
    }

    @Override
    public String generateScriptV2(Long jobId) {
        log.info("[Temporal Activity] script generation v2 started: jobId={}", jobId);
        String result = scriptService.generateRecoverably(jobId, "AUTO");
        log.info("[Temporal Activity] script generation v2 completed: jobId={}, result={}", jobId, result);
        return result;
    }

    @Override
    public boolean isGuided(Long jobId) {
        return jobRepository.findById(jobId)
                .map(job -> job.getAutonomy() == com.pipeline.video.domain.Autonomy.GUIDED
                        || job.getAutonomy() == com.pipeline.video.domain.Autonomy.MANUAL)
                .orElse(false);
    }

    @Override
    public void generateTts(Long jobId) {
        log.info("[Temporal Activity] TTS 생성 시작: jobId={}", jobId);
        ttsService.generate(jobId, "gtts_whisper_ko", "AUTO");
        log.info("[Temporal Activity] TTS 생성 완료: jobId={}", jobId);
    }

    @Override
    public void generateImages(Long jobId) {
        log.info("[Temporal Activity] 이미지 생성 시작: jobId={}", jobId);
        imagesService.generate(jobId, "AUTO");
        log.info("[Temporal Activity] 이미지 생성 완료: jobId={}", jobId);
    }

    @Override
    public void assembleLongform(Long jobId) {
        log.info("[Temporal Activity] 롱폼 조립 시작: jobId={}", jobId);
        longformService.generate(jobId, "AUTO");
        log.info("[Temporal Activity] 롱폼 조립 완료: jobId={}", jobId);
    }

    @Override
    public void publishVideo(Long jobId) {
        log.info("[Temporal Activity] YouTube 업로드 시작: jobId={}", jobId);
        jobService.publishVideo(jobId);
        log.info("[Temporal Activity] YouTube 업로드 완료: jobId={}", jobId);
    }

    @Override
    public void markJobFailed(Long jobId, String reason) {
        log.error("[Temporal Activity] Job FAILED 처리: jobId={}, reason={}", jobId, reason);
        VideoJob job = jobRepository.findById(jobId).orElse(null);
        if (job != null) {
            if (job.getStatus() == JobStatus.IMAGES_RETRY_REQUIRED) {
                log.warn("[Temporal Activity] 이미지 공급자 복구 대기 상태 유지: jobId={}", jobId);
                return;
            }
            job.setStatus(JobStatus.FAILED);
            jobRepository.save(job);
        }
    }
}

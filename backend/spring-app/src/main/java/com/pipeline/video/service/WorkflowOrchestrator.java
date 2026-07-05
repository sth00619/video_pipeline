package com.pipeline.video.service;

import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import org.springframework.context.annotation.Lazy;

/**
 * AUTO 모드 워크플로우 오케스트레이터
 *
 * GateService에서 상태가 전이된 후, AUTO 모드일 때
 * 다음 단계를 백그라운드 스레드에서 자동 실행한다.
 *
 * 브라우저 독립적 — 프론트엔드 없이도 파이프라인이 끝까지 완주한다.
 */
@Service
@Slf4j
public class WorkflowOrchestrator {

    private final VideoJobRepository jobRepository;
    private final ScriptService scriptService;
    private final TtsService ttsService;
    private final ImagesService imagesService;
    private final LongformService longformService;

    public WorkflowOrchestrator(
            VideoJobRepository jobRepository,
            @Lazy ScriptService scriptService,
            @Lazy TtsService ttsService,
            @Lazy ImagesService imagesService,
            @Lazy LongformService longformService) {
        this.jobRepository = jobRepository;
        this.scriptService = scriptService;
        this.ttsService = ttsService;
        this.imagesService = imagesService;
        this.longformService = longformService;
    }

    /**
     * 상태 전이 후 호출: AUTO 모드이면 다음 단계 비동기 실행
     */
    @Async("workflowExecutor")
    public void triggerNextStepAsync(Long jobId, JobStatus newStatus) {
        try {
            // DB에서 최신 상태 재조회 (트랜잭션 커밋 이후)
            Thread.sleep(500); // 트랜잭션 커밋 대기
            VideoJob job = jobRepository.findById(jobId).orElse(null);
            if (job == null) {
                log.warn("WorkflowOrchestrator: Job {} 미발견", jobId);
                return;
            }
            if (job.getAutonomy() == null || job.getAutonomy() != com.pipeline.video.domain.Autonomy.AUTO) {
                log.info("WorkflowOrchestrator: Job {} AUTO 아님 ({}), 스킵", jobId, job.getAutonomy());
                return;
            }

            log.info("WorkflowOrchestrator: Job {} → {} 자동 실행 시작", jobId, newStatus);

            switch (newStatus) {
                case SCRIPT_PENDING -> {
                    log.info(">>> 스크립트 생성 자동 시작: jobId={}", jobId);
                    scriptService.generate(jobId, "AUTO");
                }
                case TTS_PENDING -> {
                    log.info(">>> TTS 생성 자동 시작: jobId={}", jobId);
                    ttsService.generate(jobId, "gtts_whisper_ko", "AUTO");
                }
                case IMAGES_PENDING -> {
                    log.info(">>> 이미지 생성 자동 시작: jobId={}", jobId);
                    imagesService.generate(jobId, "AUTO");
                }
                case ASSEMBLING -> {
                    log.info(">>> 롱폼 조립 자동 시작: jobId={}", jobId);
                    longformService.generate(jobId, "AUTO");
                }
                default -> log.info("WorkflowOrchestrator: {} 단계 자동 실행 대상 아님", newStatus);
            }

            log.info("WorkflowOrchestrator: Job {} → {} 자동 실행 완료", jobId, newStatus);

        } catch (Exception e) {
            log.error("WorkflowOrchestrator 오류: jobId={}, status={}, error={}", jobId, newStatus, e.getMessage(), e);
            // 오류 발생 시 Job 상태를 FAILED로 변경
            try {
                VideoJob job = jobRepository.findById(jobId).orElse(null);
                if (job != null) {
                    job.setStatus(JobStatus.FAILED);
                    jobRepository.save(job);
                    log.info("WorkflowOrchestrator: Job {} → FAILED 전환", jobId);
                }
            } catch (Exception ex) {
                log.error("FAILED 전환 실패: {}", ex.getMessage());
            }
        }
    }
}

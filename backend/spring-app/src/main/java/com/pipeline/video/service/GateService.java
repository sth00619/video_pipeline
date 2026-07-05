package com.pipeline.video.service;

import com.pipeline.video.domain.*;
import com.pipeline.video.repository.ApprovalRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;

/**
 * 7개 게이트의 승인/거부 처리 + 자율성 다이얼 통합.
 *
 *  - approve(): 게이트 승인 + 다음 상태로 전이
 *               다음 게이트가 자율성 정책상 "자동 승인" 대상이면 즉시 연쇄 승인 (재귀)
 *  - reject():  거부 → FAILED (단순화. 나중에 재생성 로직 가능)
 *
 * Phase 2-A에서는 SHORTS_SEGMENTS / SHORTS_PREVIEW 게이트만 실전 워커 보유.
 * Phase 2-B에서는 자율성 분기 로직이 모든 게이트에 적용됨.
 * Phase 3에서 워커가 추가되면 자동 진행이 더 풍부해짐.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class GateService {

    private final VideoJobRepository jobRepository;
    private final ApprovalRepository approvalRepository;
    private final AutonomyService autonomyService;
    private final WorkflowOrchestrator workflowOrchestrator;

    // 게이트 승인 후 다음 상태 (PENDING)
    private static final Map<GateName, JobStatus> NEXT_STATUS_ON_APPROVE = Map.of(
            GateName.KEYWORD, JobStatus.SCRIPT_PENDING,
            GateName.SCRIPT, JobStatus.TTS_PENDING,
            GateName.TTS, JobStatus.IMAGES_PENDING,
            GateName.IMAGES, JobStatus.ASSEMBLING,
            GateName.PREVIEW, JobStatus.SHORTS_SEGMENTS_PENDING,
            GateName.SHORTS_SEGMENTS, JobStatus.SHORTS_GENERATING,
            GateName.SHORTS_PREVIEW, JobStatus.READY
    );

    // 각 게이트의 진입 상태
    private static final Map<GateName, JobStatus> EXPECTED_STATUS = Map.of(
            GateName.KEYWORD, JobStatus.KEYWORD_PENDING,
            GateName.SCRIPT, JobStatus.SCRIPT_PENDING,
            GateName.TTS, JobStatus.TTS_PENDING,
            GateName.IMAGES, JobStatus.IMAGES_PENDING,
            GateName.PREVIEW, JobStatus.PREVIEW_PENDING,
            GateName.SHORTS_SEGMENTS, JobStatus.SHORTS_SEGMENTS_PENDING,
            GateName.SHORTS_PREVIEW, JobStatus.SHORTS_PREVIEW_PENDING
    );

    // 다음 게이트의 PENDING 상태 → 게이트 매핑 (자동 승인 연쇄에 사용)
    private static final Map<JobStatus, GateName> STATUS_TO_GATE = Map.of(
            JobStatus.KEYWORD_PENDING, GateName.KEYWORD,
            JobStatus.SCRIPT_PENDING, GateName.SCRIPT,
            JobStatus.TTS_PENDING, GateName.TTS,
            JobStatus.IMAGES_PENDING, GateName.IMAGES,
            JobStatus.PREVIEW_PENDING, GateName.PREVIEW,
            JobStatus.SHORTS_SEGMENTS_PENDING, GateName.SHORTS_SEGMENTS,
            JobStatus.SHORTS_PREVIEW_PENDING, GateName.SHORTS_PREVIEW
    );

    @Transactional
    public Approval approve(Long jobId, GateName gate, String approvedBy, String comment) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        JobStatus expected = EXPECTED_STATUS.get(gate);
        if (expected == null || job.getStatus() != expected) {
            throw new IllegalStateException(String.format(
                    "Gate %s는 상태 %s에서만 승인 가능. 현재 상태: %s",
                    gate, expected, job.getStatus()));
        }

        // 자동 승인 판정 (자율성 정책)
        boolean isAuto = "AUTO".equals(approvedBy) || autonomyService.shouldAutoApprove(job, gate);
        String result = isAuto ? "AUTO_APPROVED" : "APPROVED";

        Approval approval = Approval.builder()
                .jobId(jobId)
                .gate(gate)
                .result(result)
                .approvedBy(approvedBy)
                .comment(comment)
                .build();
        approvalRepository.save(approval);

        // 상태 전이
        JobStatus next = NEXT_STATUS_ON_APPROVE.get(gate);
        job.setStatus(next);
        jobRepository.save(job);
        log.info("Gate {} {}: job={} → {}", gate, result, jobId, next);

        // AUTO 모드: 다음 단계 백그라운드 자동 실행
        if (autonomyService.isAuto(job)) {
            workflowOrchestrator.triggerNextStepAsync(jobId, next);
        }

        return approval;
    }

    @Transactional
    public Approval reject(Long jobId, GateName gate, String approvedBy, String comment) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        Approval approval = Approval.builder()
                .jobId(jobId)
                .gate(gate)
                .result("REJECTED")
                .approvedBy(approvedBy)
                .comment(comment)
                .build();
        approvalRepository.save(approval);

        job.setStatus(JobStatus.FAILED);
        jobRepository.save(job);
        log.info("Gate {} 거부: job={} → FAILED", gate, jobId);

        return approval;
    }

    /**
     * 자율성 정책상 현재 상태에서 자동 진행이 가능한지 확인하고
     * 가능하면 게이트를 자동 승인한다. 외부 워커(ShortsService 등)에서 호출.
     * 단, 실제 다음 워커는 호출자가 직접 실행해야 한다.
     */
    @Transactional
    public boolean tryAutoApproveAtCurrentStatus(Long jobId) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        GateName currentGate = STATUS_TO_GATE.get(job.getStatus());
        if (currentGate == null) return false;
        if (!autonomyService.shouldAutoApprove(job, currentGate)) return false;
        approve(jobId, currentGate, "AUTO", "자율성 정책에 의한 자동 승인");
        return true;
    }

    public List<Approval> getApprovals(Long jobId) {
        return approvalRepository.findByJobIdOrderByCreatedAtAsc(jobId);
    }
}

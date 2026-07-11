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
 * Phase 1 변경사항:
 *   approve() 메서드가 DB 상태 전이 후 Temporal Workflow에 Signal을 전송합니다.
 *   Signal을 받은 Workflow는 대기 상태에서 깨어나 다음 Activity를 실행합니다.
 *
 *   이전 방식: workflowOrchestrator.triggerNextStepAsync()로 다음 단계 직접 실행
 *   → 서버 재시작 시 유실, 상태 불일치 가능성
 *
 *   새 방식: workflowOrchestrator.sendApproveSignal()로 Signal 전송
 *   → Temporal Workflow가 다음 단계를 안전하게 실행, 재시작에도 보존
 *
 * 나머지 로직(게이트 상태 검증, 자율성 정책 판정, Approval 기록)은 그대로 유지.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class GateService {

    private final VideoJobRepository jobRepository;
    private final ApprovalRepository approvalRepository;
    private final AutonomyService autonomyService;
    private final WorkflowOrchestrator workflowOrchestrator;

    private static final Map<GateName, JobStatus> NEXT_STATUS_ON_APPROVE = Map.of(
            GateName.KEYWORD, JobStatus.SCRIPT_PENDING,
            GateName.SCRIPT, JobStatus.TTS_PENDING,
            GateName.TTS, JobStatus.IMAGES_PENDING,
            GateName.IMAGES, JobStatus.ASSEMBLING,
            GateName.PREVIEW, JobStatus.SHORTS_SEGMENTS_PENDING,
            GateName.SHORTS_SEGMENTS, JobStatus.SHORTS_GENERATING,
            GateName.SHORTS_PREVIEW, JobStatus.READY
    );

    private static final Map<GateName, JobStatus> EXPECTED_STATUS = Map.of(
            GateName.KEYWORD, JobStatus.KEYWORD_PENDING,
            GateName.SCRIPT, JobStatus.SCRIPT_PENDING,
            GateName.TTS, JobStatus.TTS_PENDING,
            GateName.IMAGES, JobStatus.IMAGES_PENDING,
            GateName.PREVIEW, JobStatus.PREVIEW_PENDING,
            GateName.SHORTS_SEGMENTS, JobStatus.SHORTS_SEGMENTS_PENDING,
            GateName.SHORTS_PREVIEW, JobStatus.SHORTS_PREVIEW_PENDING
    );

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

        JobStatus next = NEXT_STATUS_ON_APPROVE.get(gate);
        job.setStatus(next);
        jobRepository.save(job);
        log.info("Gate {} {}: job={} → {}", gate, result, jobId, next);

        // [Phase 1 변경] 기존 triggerNextStepAsync() 대신 Temporal Signal 전송
        //
        // KEYWORD 게이트 승인 시: Workflow를 새로 시작하고 KEYWORD Signal 전송
        // 나머지 게이트 승인 시: 이미 실행 중인 Workflow에 Signal만 전송
        //
        // AUTO 모드가 아니어도 Signal은 항상 전송합니다.
        // Workflow는 Signal을 받아야 다음 단계로 진행하기 때문입니다.
        // MANUAL/GUIDED 모드에서 사람이 승인 → GateController → 이 메서드 →
        // Signal 전송 → Workflow 재개 흐름입니다.
        if (gate == GateName.KEYWORD) {
            // 첫 번째 게이트: Workflow 시작 후 Signal
            workflowOrchestrator.startPipeline(jobId);
            try { Thread.sleep(300); } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            workflowOrchestrator.sendApproveSignal(jobId, gate.name());
        } else {
            // 이후 게이트: 이미 실행 중인 Workflow에 Signal만 전송
            workflowOrchestrator.sendApproveSignal(jobId, gate.name());
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

        // [Phase 1 변경] 거부 Signal 전송 → Workflow 즉시 종료
        workflowOrchestrator.sendRejectSignal(jobId, gate.name());

        return approval;
    }

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

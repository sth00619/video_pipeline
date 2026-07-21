package com.pipeline.video.service;

import com.pipeline.video.domain.*;
import com.pipeline.video.repository.ApprovalRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

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
        boolean keywordResearchRecovery = gate == GateName.KEYWORD
                && job.getStatus() == JobStatus.TOPIC_EVIDENCE_REQUIRED;
        if (expected == null || (job.getStatus() != expected && !keywordResearchRecovery)) {
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

        // [긴급 버그 수정] 기존에는 이 시점에서 바로 Signal을 보냈는데, 이 메서드가
        // @Transactional이라 실제 DB 커밋은 approve()가 리턴된 "이후"에 일어납니다.
        // Signal을 받은 Temporal Workflow가 바로 다음 Activity(예: 이미지 생성)를
        // 실행하면서 DB 상태를 다시 읽으면, 아직 커밋 전이라 이전 상태(TTS_PENDING
        // 등)로 보여서 그 Activity 내부의 상태 가드 체크에 걸려 실패하는 경합
        // 조건이 있었습니다.
        //
        // KEYWORD 게이트에만 Thread.sleep(300)으로 임시 땜빵을 해뒀었는데, 그건
        // "운 좋게 타이밍이 맞은" 것일 뿐 근본 해결책이 아니었고, SCRIPT/TTS/IMAGES
        // 게이트에서는 그 방편조차 없어서 그대로 실패했습니다.
        //
        // 제대로 된 수정: TransactionSynchronizationManager로 "이 트랜잭션이 실제로
        // 커밋된 직후"에만 Signal이 나가도록 등록합니다. sleep 같은 임의의 대기
        // 시간에 의존하지 않고, DB 커밋과 Signal 전송의 순서를 확정적으로 보장합니다.
        registerSignalAfterCommit(jobId, gate);

        return approval;
    }

    /**
     * 현재 트랜잭션이 커밋된 직후에만 Temporal Signal을 전송하도록 등록합니다.
     * 트랜잭션 동기화가 활성화되어 있지 않은 예외적 상황(테스트 등)에서는
     * 안전하게 즉시 전송합니다.
     */
    private void registerSignalAfterCommit(Long jobId, GateName gate) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            sendSignalForGate(jobId, gate);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                sendSignalForGate(jobId, gate);
            }
        });
    }

    private void sendSignalForGate(Long jobId, GateName gate) {
        if (gate == GateName.KEYWORD) {
            // 첫 번째 게이트: Workflow를 먼저 시작한 뒤 Signal 전송
            workflowOrchestrator.startPipeline(jobId);
            workflowOrchestrator.sendApproveSignal(jobId, gate.name());
        } else {
            workflowOrchestrator.sendApproveSignal(jobId, gate.name());
        }
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

        // [버그 수정] approve()와 동일한 이유로 커밋 이후 전송
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    workflowOrchestrator.sendRejectSignal(jobId, gate.name());
                }
            });
        } else {
            workflowOrchestrator.sendRejectSignal(jobId, gate.name());
        }

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

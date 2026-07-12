package com.pipeline.video.service;

import com.pipeline.video.workflow.VideoPipelineWorkflow;
import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowOptions;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/**
 * 비디오 파이프라인 오케스트레이터 — Temporal 기반으로 교체.
 *
 * 변경 전 (@Async 방식):
 *   각 단계를 @Async 메서드로 직접 실행. 서버 재시작 시 진행 중이던
 *   단계가 유실되고 Job이 *_PENDING 상태로 영원히 멈춤.
 *
 * 변경 후 (Temporal 방식):
 *   WorkflowClient로 VideoPipelineWorkflow를 시작하면 Temporal 서버가
 *   실행 이력을 관리. 컨테이너가 죽어도 재시작 시 마지막 완료 단계부터
 *   자동 재개. 게이트 대기 상태도 Temporal이 보존함.
 *
 * Workflow ID 규칙:
 *   "video-pipeline-{jobId}" 형태의 고유 ID 사용.
 *   같은 jobId로 이미 Workflow가 실행 중이면 중복 실행되지 않음
 *   (WorkflowIdConflictPolicy 기본값: REJECT_DUPLICATE).
 *   Temporal UI에서 이 ID로 특정 Job의 실행 이력을 추적할 수 있음.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class WorkflowOrchestrator {

    private final WorkflowClient workflowClient;

    /**
     * 파이프라인 Workflow를 시작합니다.
     *
     * GateService.approve()의 첫 번째 게이트(KEYWORD) 승인 시 호출되거나,
     * KeywordService가 키워드 생성 완료 후 직접 호출합니다.
     * 이미 실행 중인 Workflow가 있으면 무시됩니다.
     */
    public void startPipeline(Long jobId) {
        String workflowId = "video-pipeline-" + jobId;
        log.info("Temporal Workflow 시작: workflowId={}", workflowId);

        try {
            VideoPipelineWorkflow workflow = workflowClient.newWorkflowStub(
                    VideoPipelineWorkflow.class,
                    WorkflowOptions.newBuilder()
                            .setTaskQueue("video-pipeline-queue")
                            .setWorkflowId(workflowId)
                            // 같은 jobId로 중복 실행 방지
                            .setWorkflowIdConflictPolicy(
                                    io.temporal.api.enums.v1.WorkflowIdConflictPolicy
                                            .WORKFLOW_ID_CONFLICT_POLICY_USE_EXISTING)
                            .build()
            );
            // 비동기 시작 — Workflow가 백그라운드에서 실행됨
            WorkflowClient.start(workflow::run, jobId);
            log.info("Temporal Workflow 시작 완료: workflowId={}", workflowId);

        } catch (Exception e) {
            log.error("Temporal Workflow 시작 실패: workflowId={}, error={}", workflowId, e.getMessage(), e);
            throw new RuntimeException("파이프라인 시작 실패: " + e.getMessage(), e);
        }
    }

    /**
     * 게이트 승인 Signal을 실행 중인 Workflow에 전송합니다.
     * GateService.approve()에서 호출됩니다.
     */
    public void sendApproveSignal(Long jobId, String gateName) {
        String workflowId = "video-pipeline-" + jobId;
        log.info("게이트 승인 Signal 전송: workflowId={}, gate={}", workflowId, gateName);
        try {
            VideoPipelineWorkflow workflow = workflowClient.newWorkflowStub(
                    VideoPipelineWorkflow.class, workflowId);
            workflow.approveGate(gateName);
        } catch (Exception e) {
            log.error("Signal 전송 실패: workflowId={}, gate={}, error={}",
                    workflowId, gateName, e.getMessage(), e);
            // Signal 전송 실패는 기존 gate 승인 흐름을 막으면 안 됨
            // (DB 상태 전이는 GateService가 이미 완료했으므로 로그만 남김)
        }
    }

    /**
     * 게이트 거부 Signal을 실행 중인 Workflow에 전송합니다.
     * GateService.reject()에서 호출됩니다.
     */
    public void sendRejectSignal(Long jobId, String gateName) {
        String workflowId = "video-pipeline-" + jobId;
        log.info("게이트 거부 Signal 전송: workflowId={}, gate={}", workflowId, gateName);
        try {
            VideoPipelineWorkflow workflow = workflowClient.newWorkflowStub(
                    VideoPipelineWorkflow.class, workflowId);
            workflow.rejectGate(gateName);
        } catch (Exception e) {
            log.error("Reject Signal 전송 실패: workflowId={}, gate={}, error={}",
                    workflowId, gateName, e.getMessage(), e);
        }
    }

    /**
     * 실행 중인 Workflow를 취소합니다. Job 정지 버튼과 연결됩니다.
     *
     * [긴급 추가] 정지 버튼을 눌러도 실제로 안 멈추던 문제 수정.
     * 기존 정지 기능(Phase A)은 FastAPI의 process_manager만 알고 있었고,
     * Temporal이 실행을 담당하게 된 지금은 Temporal Workflow 자체를
     * 취소해야 실제로 멈춥니다. cancel()은 현재 실행 중인 Activity에도
     * 취소 신호를 전파합니다 (Activity 구현체가 InterruptedException을
     * 확인하지 않으면 진행 중인 API 호출 자체는 끝까지 갈 수 있지만,
     * 최소한 다음 단계로는 절대 진행하지 않습니다).
     */
    public void cancelPipeline(Long jobId) {
        String workflowId = "video-pipeline-" + jobId;
        log.info("Temporal Workflow 취소 요청: workflowId={}", workflowId);
        try {
            io.temporal.client.WorkflowStub stub =
                    workflowClient.newUntypedWorkflowStub(workflowId);
            stub.cancel();
            log.info("Temporal Workflow 취소 완료: workflowId={}", workflowId);
        } catch (Exception e) {
            log.warn("Temporal Workflow 취소 실패 (이미 종료됐거나 존재하지 않을 수 있음): workflowId={}, error={}",
                    workflowId, e.getMessage());
            // Workflow가 아직 시작 안 됐거나 이미 끝난 경우일 수 있으므로
            // 예외를 던지지 않고 로그만 남김 — 정지 버튼 자체는 항상 성공해야 함
        }
    }

    /**
     * 기존 @Async triggerNextStepAsync와 호환되는 메서드.
     *
     * KeywordService 외의 서비스들이 이 메서드를 호출하던 곳이 있다면
     * startPipeline() 또는 sendApproveSignal()로 점진적으로 교체하면 됩니다.
     * 지금은 KEYWORD 단계 이후에는 Signal로 처리되므로 이 메서드는
     * 초기 Workflow 시작 용도로만 사용합니다.
     *
     * @deprecated sendApproveSignal() 또는 startPipeline()을 직접 사용하세요.
     */
    @Deprecated
    public void triggerNextStepAsync(Long jobId,
            com.pipeline.video.domain.JobStatus newStatus) {
        // 첫 진입점: 키워드 확정 후 전체 파이프라인 Workflow를 시작
        // 이후 단계 전환은 Workflow 내부에서 Signal로 처리됨
        log.info("triggerNextStepAsync 호환 호출 → Workflow 시작: jobId={}, status={}",
                jobId, newStatus);
        if (newStatus == com.pipeline.video.domain.JobStatus.SCRIPT_PENDING) {
            // 키워드 게이트 승인 후 첫 호출 — Workflow 시작 + 즉시 KEYWORD Signal
            startPipeline(jobId);
            // Workflow가 시작되면 즉시 KEYWORD 게이트 Signal 전송
            // (AUTO 모드에서 GateService가 이미 상태 전이를 완료했으므로)
            try {
                Thread.sleep(500); // Workflow 등록 대기
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            sendApproveSignal(jobId, "KEYWORD");
        }
    }
}

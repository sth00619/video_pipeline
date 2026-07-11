package com.pipeline.video.workflow;

import io.temporal.workflow.SignalMethod;
import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

/**
 * 롱폼 영상 생성 파이프라인 Temporal Workflow.
 *
 * 기존 WorkflowOrchestrator(@Async)를 대체합니다.
 *
 * 핵심 차이:
 *   @Async 방식: 서버가 어느 단계에서 죽으면 그 Job은 *_PENDING 상태로
 *   영원히 멈춤. 사람이 수동으로 재시작해야 함.
 *
 *   Temporal 방식: Workflow 실행 이력이 Temporal 서버에 저장되어 있어서,
 *   Spring Boot 컨테이너가 재시작되면 마지막으로 완료된 Activity 다음부터
 *   자동으로 재개됨. DB의 Job 상태값과도 동기화됨.
 *
 * Signal 메서드:
 *   MANUAL/GUIDED 게이트에서 사람이 승인하면 GateService가 approveGate()
 *   Signal을 보냄. Workflow는 이 Signal을 받을 때까지 대기 상태를 유지함.
 *   이 대기 중에 서버가 재시작돼도 Workflow는 Signal을 기다리는 상태로 복원됨.
 */
@WorkflowInterface
public interface VideoPipelineWorkflow {

    @WorkflowMethod
    void run(Long jobId);

    /**
     * MANUAL/GUIDED 모드에서 게이트 승인 시 GateService가 호출합니다.
     * Signal은 비동기적으로 전달되며, Workflow가 대기 중이면 즉시 깨어납니다.
     */
    @SignalMethod
    void approveGate(String gateName);

    /**
     * 게이트 거부 시 GateService가 호출합니다. Workflow를 즉시 종료합니다.
     */
    @SignalMethod
    void rejectGate(String gateName);
}

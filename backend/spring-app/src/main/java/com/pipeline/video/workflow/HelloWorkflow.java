package com.pipeline.video.workflow;

import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

/**
 * Phase 0 스모크 테스트용 워크플로우.
 *
 * 이 워크플로우가 정상 실행되면 Spring Boot ↔ Temporal 서버 연결이
 * 제대로 됐다는 뜻입니다. Phase 1에서 실제 롱폼 파이프라인 워크플로우로
 * 교체/추가할 예정이며, 이 파일은 연결 검증이 끝나면 지워도 됩니다.
 */
@WorkflowInterface
public interface HelloWorkflow {

    @WorkflowMethod
    String sayHello(String name);
}

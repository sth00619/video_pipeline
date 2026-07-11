package com.pipeline.video.workflow;

import io.temporal.activity.ActivityOptions;
import io.temporal.spring.boot.WorkflowImpl;
import io.temporal.workflow.Workflow;

import java.time.Duration;

/**
 * [주의] taskQueues 값 "video-pipeline-queue"는 Phase 1부터 실제 롱폼 파이프라인
 * 워크플로우들도 공유하게 될 이름입니다. 이름 자체를 바꾸고 싶으면 여기와
 * HelloActivitiesImpl 양쪽의 taskQueues 값을 함께 바꿔야 합니다.
 */
@WorkflowImpl(taskQueues = "video-pipeline-queue")
public class HelloWorkflowImpl implements HelloWorkflow {

    private final HelloActivities activities = Workflow.newActivityStub(
            HelloActivities.class,
            ActivityOptions.newBuilder()
                    .setStartToCloseTimeout(Duration.ofSeconds(10))
                    .build()
    );

    @Override
    public String sayHello(String name) {
        return activities.greet(name);
    }
}

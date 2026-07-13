package com.pipeline.video.controller;

import com.pipeline.video.workflow.HelloWorkflow;
import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowOptions;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Phase 0 스모크 테스트 전용 컨트롤러.
 *
 * JWT 인증이 필요한 일반 /api/** 라우트와 동일하게 인증이 걸려 있습니다
 * (SecurityConfig를 따로 안 건드렸음). 로그인해서 받은 토큰으로 호출하세요:
 *
 *   curl -H "Authorization: Bearer <토큰>" \
 *        "http://localhost:8080/api/temporal-test/hello?name=송"
 *
 * 정상이라면 HelloActivitiesImpl.greet()의 메시지가 그대로 응답으로 오고,
 * http://localhost:8233 (Temporal UI)에서 방금 실행된 워크플로우가
 * "Completed" 상태로 보여야 합니다.
 *
 * 연결 확인이 끝나면 이 컨트롤러와 workflow/Hello*.java 4개 파일은
 * 지워도 됩니다 (Phase 1에서 실제 파이프라인 워크플로우로 대체 예정).
 */
@RestController
@RequestMapping("/api/temporal-test")
@RequiredArgsConstructor
public class TemporalTestController {

    private final WorkflowClient workflowClient;

    private final com.pipeline.video.service.LongformService longformService;

    @GetMapping("/trigger-retry")
    public String triggerRetry(@RequestParam Long jobId) {
        new Thread(() -> {
            try {
                longformService.generate(jobId, "AUTO");
            } catch (Exception e) {
                e.printStackTrace();
            }
        }).start();
        return "Triggered video assembly for Job " + jobId;
    }

    @GetMapping("/hello")
    public String hello(@RequestParam(defaultValue = "송") String name) {
        HelloWorkflow workflow = workflowClient.newWorkflowStub(
                HelloWorkflow.class,
                WorkflowOptions.newBuilder()
                        .setTaskQueue("video-pipeline-queue")
                        .setWorkflowId("hello-smoke-test-" + System.currentTimeMillis())
                        .build()
        );
        return workflow.sayHello(name);
    }
}

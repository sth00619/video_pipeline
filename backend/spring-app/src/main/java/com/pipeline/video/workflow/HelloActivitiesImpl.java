package com.pipeline.video.workflow;

import io.temporal.spring.boot.ActivityImpl;
import org.springframework.stereotype.Component;

@Component
@ActivityImpl(taskQueues = "video-pipeline-queue")
public class HelloActivitiesImpl implements HelloActivities {

    @Override
    public String greet(String name) {
        return "Temporal 연결 성공! 안녕, " + name + " — 이 메시지가 보이면 Phase 0 인프라가 정상 동작 중입니다.";
    }
}

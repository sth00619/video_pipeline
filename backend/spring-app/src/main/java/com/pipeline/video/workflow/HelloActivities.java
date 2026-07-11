package com.pipeline.video.workflow;

import io.temporal.activity.ActivityInterface;
import io.temporal.activity.ActivityMethod;

@ActivityInterface
public interface HelloActivities {

    @ActivityMethod
    String greet(String name);
}

package com.pipeline.video.dto;

import lombok.Data;

@Data
public class TtsGenerateRequest {
    private String voiceId = "default_ko";
    private Double speed = 1.0;
}

package com.pipeline.video.controller;

import com.pipeline.video.service.FastApiClient;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/pipeline")
@RequiredArgsConstructor
public class PipelineConfigController {

    private final FastApiClient fastApiClient;

    /** 편집 화면에서 사용할 초반 Kling 범위만 프록시한다. */
    @GetMapping("/motion-policy")
    public ResponseEntity<Map<String, Object>> getKlingMotionPolicy() {
        return ResponseEntity.ok(fastApiClient.getKlingMotionPolicy());
    }
}

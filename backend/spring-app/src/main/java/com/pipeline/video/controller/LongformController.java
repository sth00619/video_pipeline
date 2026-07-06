package com.pipeline.video.controller;

import com.pipeline.video.dto.LongformConfirmRequest;
import com.pipeline.video.dto.LongformGenerateResponse;
import com.pipeline.video.service.LongformService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Phase 3-5A 롱폼 조립 API
 *
 * 1. POST /api/jobs/{id}/longform/generate — 이미지+TTS → MP4 생성
 * 2. POST /api/jobs/{id}/longform/confirm  — 게이트 통과 → READY 또는 SHORTS 단계
 */
@RestController
@RequestMapping("/api/jobs/{jobId}/longform")
@RequiredArgsConstructor
public class LongformController {

    private final LongformService longformService;

    @PostMapping("/generate")
    public ResponseEntity<LongformGenerateResponse> generate(
            @PathVariable Long jobId,
            @AuthenticationPrincipal String username) {
        return ResponseEntity.ok(longformService.generate(jobId, username));
    }

    @PostMapping("/confirm")
    public ResponseEntity<Map<String, String>> confirm(
            @PathVariable Long jobId,
            @RequestBody(required = false) LongformConfirmRequest request,
            @AuthenticationPrincipal String username) {
        longformService.confirm(jobId, username);
        return ResponseEntity.ok(Map.of("status", "OK"));
    }

    @PostMapping("/rebuild")
    public ResponseEntity<LongformGenerateResponse> rebuild(
            @PathVariable Long jobId,
            @AuthenticationPrincipal String username) {
        return ResponseEntity.ok(longformService.rebuild(jobId, username));
    }
}

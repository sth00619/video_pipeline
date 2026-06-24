package com.pipeline.video.controller;

import com.pipeline.video.domain.Asset;
import com.pipeline.video.dto.ShortClipInfo;
import com.pipeline.video.dto.ShortsAnalyzeResponse;
import com.pipeline.video.dto.ShortsConfirmRequest;
import com.pipeline.video.service.ShortsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.List;

/**
 * Phase 2-A 핵심: 쇼츠 구간 게이트
 *
 * 흐름:
 *   1. POST /api/jobs/{id}/shorts/analyze   ─ 영상 업로드, Whisper 분석, 제안 구간 반환
 *      → 상태 SHORTS_SEGMENTS_PENDING
 *   2. (관리자 검토) ─ 응답의 suggestedSegments를 보고 수정/승인
 *   3. POST /api/jobs/{id}/shorts/confirm   ─ 확정된 구간으로 자르기
 *      → 상태 SHORTS_PREVIEW_PENDING
 *   4. POST /api/jobs/{id}/gates/SHORTS_PREVIEW/approve ─ 미리보기 승인
 *      → 상태 READY
 */
@RestController
@RequestMapping("/api/jobs/{jobId}/shorts")
@RequiredArgsConstructor
public class ShortsController {

    private final ShortsService shortsService;

    @PostMapping(value = "/analyze", consumes = "multipart/form-data")
    public ResponseEntity<ShortsAnalyzeResponse> analyze(
            @PathVariable Long jobId,
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "shortsCount", defaultValue = "3") int shortsCount,
            @AuthenticationPrincipal String username) throws IOException {
        return ResponseEntity.ok(shortsService.analyze(jobId, file, shortsCount, username));
    }

    @PostMapping("/confirm")
    public ResponseEntity<List<ShortClipInfo>> confirm(
            @PathVariable Long jobId,
            @RequestBody ShortsConfirmRequest request,
            @AuthenticationPrincipal String username) {
        return ResponseEntity.ok(shortsService.confirm(jobId, request, username));
    }

    @GetMapping("/assets")
    public ResponseEntity<List<Asset>> getAssets(@PathVariable Long jobId) {
        return ResponseEntity.ok(shortsService.getShortsAssets(jobId));
    }
}

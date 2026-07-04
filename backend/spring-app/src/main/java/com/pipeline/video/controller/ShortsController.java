package com.pipeline.video.controller;

import com.pipeline.video.dto.ShortClipInfo;
import com.pipeline.video.dto.ShortsAnalyzeResponse;
import com.pipeline.video.dto.ShortsConfirmRequest;
import com.pipeline.video.service.ShortsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@RestController
@RequestMapping("/api/jobs/{jobId}/shorts")
@RequiredArgsConstructor
public class ShortsController {

    private final ShortsService shortsService;

    /**
     * AUTO/GUIDED: Whisper 분석 → 추천 구간 반환
     * Job 상태: DRAFT 또는 SHORTS_SEGMENTS_PENDING 모두 허용
     */
    @PostMapping("/analyze")
    public ResponseEntity<ShortsAnalyzeResponse> analyze(
            @PathVariable Long jobId,
            @RequestParam(defaultValue = "3") int shortsCount,
            @RequestPart("file") MultipartFile file,
            @AuthenticationPrincipal String username) throws Exception {
        return ResponseEntity.ok(shortsService.analyze(jobId, file, shortsCount, username));
    }

    /**
     * MANUAL: Whisper 분석 없이 직접 구간으로 쇼츠 생성
     * - file: 원본 영상
     * - segments: JSON 문자열 [{index,label,start,end}, ...]
     */
    @PostMapping("/cut-direct")
    public ResponseEntity<List<ShortClipInfo>> cutDirect(
            @PathVariable Long jobId,
            @RequestPart("file") MultipartFile file,
            @RequestPart("segments") String segmentsJson,
            @AuthenticationPrincipal String username) throws Exception {
        return ResponseEntity.ok(shortsService.cutDirect(jobId, file, segmentsJson, username));
    }

    /**
     * AUTO/GUIDED: 분석 후 구간 확정 → MP4 생성
     */
    @PostMapping("/confirm")
    public ResponseEntity<List<ShortClipInfo>> confirm(
            @PathVariable Long jobId,
            @RequestBody ShortsConfirmRequest request,
            @AuthenticationPrincipal String username) {
        return ResponseEntity.ok(shortsService.confirm(jobId, request, username));
    }
}

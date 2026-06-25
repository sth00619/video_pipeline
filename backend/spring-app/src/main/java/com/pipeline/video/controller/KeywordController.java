package com.pipeline.video.controller;

import com.pipeline.video.dto.KeywordConfirmRequest;
import com.pipeline.video.dto.KeywordSearchRequest;
import com.pipeline.video.dto.KeywordSearchResponse;
import com.pipeline.video.service.KeywordService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Phase 3-1 키워드 탐색 API
 *
 * 1. POST /api/jobs/{id}/keyword/search   — seed 키워드 → 후보 N개
 * 2. POST /api/jobs/{id}/keyword/confirm  — 선택된 키워드 확정 → SCRIPT_PENDING
 */
@RestController
@RequestMapping("/api/jobs/{jobId}/keyword")
@RequiredArgsConstructor
public class KeywordController {

    private final KeywordService keywordService;

    @PostMapping("/search")
    public ResponseEntity<KeywordSearchResponse> search(
            @PathVariable Long jobId,
            @RequestBody KeywordSearchRequest request,
            @AuthenticationPrincipal String username) {
        int limit = request.getLimit() != null ? request.getLimit() : 5;
        return ResponseEntity.ok(keywordService.search(jobId, request.getSeedKeyword(), limit, username));
    }

    @PostMapping("/confirm")
    public ResponseEntity<Map<String, String>> confirm(
            @PathVariable Long jobId,
            @RequestBody KeywordConfirmRequest request,
            @AuthenticationPrincipal String username) {
        keywordService.confirm(jobId, request.getSelectedKeyword(), username);
        return ResponseEntity.ok(Map.of(
                "status", "OK",
                "selected", request.getSelectedKeyword()
        ));
    }
}

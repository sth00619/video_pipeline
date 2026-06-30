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
        return ResponseEntity.ok(keywordService.search(
                jobId,
                request.getSeedKeyword(),
                limit,
                request.getCategory(),
                username
        ));
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

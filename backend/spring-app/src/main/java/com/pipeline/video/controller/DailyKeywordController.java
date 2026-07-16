package com.pipeline.video.controller;

import com.pipeline.video.service.DailyKeywordService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController
@RequestMapping("/api/keywords")
@RequiredArgsConstructor
public class DailyKeywordController {
    private final DailyKeywordService service;

    @GetMapping("/daily")
    public ResponseEntity<Map<String, Object>> daily() {
        return ResponseEntity.ok(Map.of("timezone", "Asia/Seoul", "cutoff", "08:00", "refresh", "09:00", "youtubeConfigured", service.youtubeConfigured(), "items", service.getToday()));
    }

    @PostMapping("/refresh")
    public ResponseEntity<Map<String, Object>> refresh() { return ResponseEntity.ok(Map.of("items", service.refreshToday())); }

    @PostMapping("/manual")
    public ResponseEntity<Map<String, Object>> manual(@RequestBody Map<String, String> request) {
        String keyword = request.getOrDefault("keyword", "").trim();
        if (keyword.isBlank()) return ResponseEntity.badRequest().build();
        return ResponseEntity.ok(service.addManual(keyword, request.get("category"), request.get("note")));
    }
}

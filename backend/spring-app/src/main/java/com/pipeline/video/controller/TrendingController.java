package com.pipeline.video.controller;

import com.pipeline.video.dto.TrendingVideoDto;
import com.pipeline.video.service.FastApiClient;
import com.pipeline.video.service.TrendingService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class TrendingController {

    private final TrendingService trendingService;
    private final FastApiClient fastApiClient;

    @GetMapping("/api/trending/youtube")
    public ResponseEntity<List<TrendingVideoDto>> getTrendingYoutube(
            @RequestParam(required = false, defaultValue = "") String keyword,
            @RequestParam(required = false, defaultValue = "evidence") String ranking,
            @RequestParam(required = false) Long minSubscribers) {
        return ResponseEntity.ok(trendingService.getTrendingVideos(keyword, ranking, minSubscribers));
    }

    @GetMapping({"/api/youtube/channels/benchmark", "/api/trending/youtube/channels/benchmark"})
    public ResponseEntity<Object> channelBenchmark(
            @RequestParam(required = false) String channelIds) {
        return ResponseEntity.ok(fastApiClient.getChannelBenchmarks(channelIds));
    }
}

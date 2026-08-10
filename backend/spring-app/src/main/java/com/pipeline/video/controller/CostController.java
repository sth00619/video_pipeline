package com.pipeline.video.controller;

import com.pipeline.video.domain.CostLedger;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.dto.CostEstimateDto;
import com.pipeline.video.repository.VideoJobRepository;
import com.pipeline.video.service.CostService;
import com.pipeline.video.service.FastApiClient;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/jobs/{jobId}/costs")
@RequiredArgsConstructor
public class CostController {

    private final CostService costService;
    private final VideoJobRepository jobRepository;
    private final FastApiClient fastApiClient;

    /** 작업의 모든 비용 항목 조회 */
    @GetMapping
    public ResponseEntity<List<CostLedger>> getLedger(@PathVariable Long jobId) {
        return ResponseEntity.ok(costService.getLedger(jobId));
    }

    /**
     * 작업의 현재 비용 요약 (누적, 예산, 잔여, provider별 breakdown 및 통합 개별 호출 내역).
     */
    @GetMapping("/summary")
    public ResponseEntity<CostEstimateDto> getSummary(@PathVariable Long jobId) {
        return ResponseEntity.ok(costService.getSummaryDto(jobId));
    }
}

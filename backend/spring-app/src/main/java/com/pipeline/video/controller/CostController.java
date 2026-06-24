package com.pipeline.video.controller;

import com.pipeline.video.domain.CostLedger;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.dto.CostEstimateDto;
import com.pipeline.video.repository.VideoJobRepository;
import com.pipeline.video.service.CostService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.List;

@RestController
@RequestMapping("/api/jobs/{jobId}/costs")
@RequiredArgsConstructor
public class CostController {

    private final CostService costService;
    private final VideoJobRepository jobRepository;

    /** 작업의 모든 비용 항목 조회 */
    @GetMapping
    public ResponseEntity<List<CostLedger>> getLedger(@PathVariable Long jobId) {
        return ResponseEntity.ok(costService.getLedger(jobId));
    }

    /** 작업의 현재 비용 요약 (누적, 예산, 잔여) */
    @GetMapping("/summary")
    public ResponseEntity<CostEstimateDto> getSummary(@PathVariable Long jobId) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        BigDecimal current = job.getCostAccumulated() != null ? job.getCostAccumulated() : BigDecimal.ZERO;
        BigDecimal cap = job.getBudgetCap();
        BigDecimal remaining = cap != null ? cap.subtract(current) : null;
        return ResponseEntity.ok(new CostEstimateDto(
                jobId, current, cap, remaining, job.getStatus().name()
        ));
    }
}

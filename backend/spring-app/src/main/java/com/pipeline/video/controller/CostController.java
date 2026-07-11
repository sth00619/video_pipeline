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

    /**
     * 작업의 현재 비용 요약 (누적, 예산, 잔여, provider별 breakdown).
     *
     * items 필드가 새로 채워집니다:
     *   프론트엔드가 이미 costs.items[]를 기대하고 있었지만 서버가 반환하지 않아
     *   비용 상세 breakdown이 표시되지 않았습니다. CostLedger에서 가장 최근 순으로
     *   최대 20개까지 함께 반환합니다 (너무 많으면 UI가 지저분해지므로 상한).
     */
    @GetMapping("/summary")
    public ResponseEntity<CostEstimateDto> getSummary(@PathVariable Long jobId) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));
        BigDecimal current = job.getCostAccumulated() != null ? job.getCostAccumulated() : BigDecimal.ZERO;
        BigDecimal cap = job.getBudgetCap();
        BigDecimal remaining = cap != null ? cap.subtract(current) : null;

        List<CostEstimateDto.CostItemDto> items = costService.getLedger(jobId).stream()
                .limit(20)
                .map(l -> new CostEstimateDto.CostItemDto(
                        l.getCategory(),
                        l.getAmount(),
                        l.getCurrency(),
                        l.getNote()))
                .toList();

        return ResponseEntity.ok(CostEstimateDto.builder()
                .jobId(jobId)
                .currentTotal(current)
                .budgetCap(cap)
                .remaining(remaining)
                .status(job.getStatus().name())
                .items(items)
                .build());
    }
}

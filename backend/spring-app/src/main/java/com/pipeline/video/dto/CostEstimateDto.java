package com.pipeline.video.dto;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.math.BigDecimal;

@Data
@AllArgsConstructor
public class CostEstimateDto {
    private Long jobId;
    private BigDecimal currentTotal;
    private BigDecimal budgetCap;
    private BigDecimal remaining;
    private String status;
}

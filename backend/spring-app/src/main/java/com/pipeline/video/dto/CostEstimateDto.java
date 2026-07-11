package com.pipeline.video.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

/**
 * 비용 요약 응답 DTO.
 *
 * items 필드가 새로 추가되었습니다:
 *   프론트엔드의 JobDetail.jsx (line 1229~)가 costs.items[].{provider, amount}를
 *   기대하지만 기존 DTO에는 items가 없어서 provider별 breakdown이 표시되지
 *   않았습니다. Nullable로 두어 기존 API 사용처와의 호환성은 유지됩니다.
 */
@Data
@AllArgsConstructor
@NoArgsConstructor
@Builder
public class CostEstimateDto {
    private Long jobId;
    private BigDecimal currentTotal;
    private BigDecimal budgetCap;
    private BigDecimal remaining;
    private String status;
    /** provider별 breakdown. summary 엔드포인트에서만 채워지고 그 외엔 null. */
    private List<CostItemDto> items;

    @Data
    @AllArgsConstructor
    @NoArgsConstructor
    public static class CostItemDto {
        private String provider;
        private BigDecimal amount;
        private String currency;
        private String note;
    }
}

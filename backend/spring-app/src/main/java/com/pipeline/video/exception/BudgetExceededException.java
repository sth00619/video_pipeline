package com.pipeline.video.exception;

import java.math.BigDecimal;

public class BudgetExceededException extends RuntimeException {
    private final Long jobId;
    private final BigDecimal currentCost;
    private final BigDecimal attemptedAdd;
    private final BigDecimal budgetCap;

    public BudgetExceededException(Long jobId, BigDecimal currentCost,
                                   BigDecimal attemptedAdd, BigDecimal budgetCap) {
        super(String.format(
                "예산 초과: jobId=%d, 현재 비용=%s, 추가 시도=%s, 예산 상한=%s",
                jobId, currentCost, attemptedAdd, budgetCap
        ));
        this.jobId = jobId;
        this.currentCost = currentCost;
        this.attemptedAdd = attemptedAdd;
        this.budgetCap = budgetCap;
    }

    public Long getJobId() { return jobId; }
    public BigDecimal getCurrentCost() { return currentCost; }
    public BigDecimal getAttemptedAdd() { return attemptedAdd; }
    public BigDecimal getBudgetCap() { return budgetCap; }
}

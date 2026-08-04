package com.pipeline.video.service;

import com.pipeline.video.domain.CostLedger;
import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.config.PricingConfig;
import com.pipeline.video.exception.BudgetExceededException;
import com.pipeline.video.repository.CostLedgerRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Locale;

/**
 * 비용 원장 기록 + 누적 + 예산 가드 통합 서비스.
 *
 *  - record(): 워커가 비용을 발생시킨 후 호출. 예산 초과 시 BUDGET_BLOCKED 전이 + 예외.
 *  - precheck(): 워커가 비용을 발생시키기 전에 호출 (선택). 예산 초과 예상이면 즉시 차단.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class CostService {

    private final VideoJobRepository jobRepository;
    private final CostLedgerRepository ledgerRepository;

    /**
     * 비용 발생 후 기록. 누적 비용 업데이트. 예산 초과 시 BUDGET_BLOCKED 전이.
     */
    @Transactional
    public BigDecimal record(Long jobId, String category, BigDecimal amount, String currency, String note) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        BigDecimal current = totalInBudgetKrw(jobId);
        BigDecimal budgetAmount = toBudgetKrw(amount, currency);
        BigDecimal newTotal = current.add(budgetAmount);

        // 예산 가드
        if (job.getBudgetCap() != null && newTotal.compareTo(job.getBudgetCap()) > 0) {
            job.setStatus(JobStatus.BUDGET_BLOCKED);
            jobRepository.save(job);
            log.warn("예산 초과로 BUDGET_BLOCKED 전이: jobId={}, new={}, cap={}",
                    jobId, newTotal, job.getBudgetCap());
            throw new BudgetExceededException(jobId, current, budgetAmount, job.getBudgetCap());
        }

        // 원장 기록
        CostLedger ledger = CostLedger.builder()
                .jobId(jobId)
                .category(category)
                .amount(amount)
                .currency(currency != null ? currency : "USD")
                .note(note)
                .build();
        ledgerRepository.save(ledger);

        // 누적 업데이트
        // VideoJob.costAccumulated와 budgetCap은 모두 KRW로 비교한다.
        job.setCostAccumulated(newTotal);
        jobRepository.save(job);

        log.info("비용 기록: jobId={}, {}={}, 누적={}", jobId, category, amount, newTotal);
        return newTotal;
    }

    /**
     * 비용 발생 전 사전 체크. 추정 비용이 예산을 넘으면 BUDGET_BLOCKED 전이 + 예외.
     */
    @Transactional
    public void precheck(Long jobId, BigDecimal estimatedCost) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getBudgetCap() == null) return;
        if (estimatedCost == null || estimatedCost.compareTo(BigDecimal.ZERO) <= 0) return;

        BigDecimal current = totalInBudgetKrw(jobId);
        BigDecimal projected = current.add(estimatedCost);

        if (projected.compareTo(job.getBudgetCap()) > 0) {
            job.setStatus(JobStatus.BUDGET_BLOCKED);
            jobRepository.save(job);
            log.warn("예산 사전체크 실패로 BUDGET_BLOCKED 전이: jobId={}, projected={}, cap={}",
                    jobId, projected, job.getBudgetCap());
            throw new BudgetExceededException(jobId, current, estimatedCost, job.getBudgetCap());
        }
    }

    public List<CostLedger> getLedger(Long jobId) {
        return ledgerRepository.findByJobIdOrderByCreatedAtDesc(jobId);
    }

    public BigDecimal getTotal(Long jobId) {
        return ledgerRepository.findByJobIdOrderByCreatedAtDesc(jobId).stream()
                .map(ledger -> toBudgetKrw(ledger.getAmount(), ledger.getCurrency()))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    private BigDecimal totalInBudgetKrw(Long jobId) {
        return ledgerRepository.findByJobIdOrderByCreatedAtDesc(jobId).stream()
                .map(ledger -> toBudgetKrw(ledger.getAmount(), ledger.getCurrency()))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    private BigDecimal toBudgetKrw(BigDecimal amount, String currency) {
        BigDecimal safeAmount = amount == null ? BigDecimal.ZERO : amount;
        String normalized = currency == null ? "USD" : currency.trim().toUpperCase(Locale.ROOT);
        return switch (normalized) {
            case "KRW" -> safeAmount;
            case "USD" -> safeAmount.multiply(PricingConfig.USD_TO_KRW_BUDGET_RATE)
                    .setScale(0, RoundingMode.HALF_UP);
            default -> throw new IllegalArgumentException("지원하지 않는 비용 통화: " + currency);
        };
    }
}

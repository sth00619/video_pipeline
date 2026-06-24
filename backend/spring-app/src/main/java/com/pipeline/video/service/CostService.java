package com.pipeline.video.service;

import com.pipeline.video.domain.CostLedger;
import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.exception.BudgetExceededException;
import com.pipeline.video.repository.CostLedgerRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;

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

        BigDecimal current = job.getCostAccumulated() != null ? job.getCostAccumulated() : BigDecimal.ZERO;
        BigDecimal newTotal = current.add(amount);

        // 예산 가드
        if (job.getBudgetCap() != null && newTotal.compareTo(job.getBudgetCap()) > 0) {
            job.setStatus(JobStatus.BUDGET_BLOCKED);
            jobRepository.save(job);
            log.warn("예산 초과로 BUDGET_BLOCKED 전이: jobId={}, new={}, cap={}",
                    jobId, newTotal, job.getBudgetCap());
            throw new BudgetExceededException(jobId, current, amount, job.getBudgetCap());
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

        BigDecimal current = job.getCostAccumulated() != null ? job.getCostAccumulated() : BigDecimal.ZERO;
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
                .map(CostLedger::getAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}

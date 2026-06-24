package com.pipeline.video.repository;

import com.pipeline.video.domain.CostLedger;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface CostLedgerRepository extends JpaRepository<CostLedger, Long> {
    List<CostLedger> findByJobIdOrderByCreatedAtDesc(Long jobId);
}

package com.pipeline.video.repository;

import com.pipeline.video.domain.Approval;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ApprovalRepository extends JpaRepository<Approval, Long> {
    List<Approval> findByJobIdOrderByCreatedAtAsc(Long jobId);
}

package com.pipeline.video.repository;

import com.pipeline.video.domain.ShortsJob;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ShortsJobRepository extends JpaRepository<ShortsJob, Long> {
    List<ShortsJob> findByCreatedByOrderByUpdatedAtDesc(String createdBy);
    List<ShortsJob> findByParentJobIdOrderByUpdatedAtDesc(Long parentJobId);
}

package com.pipeline.video.repository;

import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.VideoJob;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface VideoJobRepository extends JpaRepository<VideoJob, Long> {
    List<VideoJob> findByCreatedByOrderByCreatedAtDesc(String createdBy);
    List<VideoJob> findByStatusOrderByCreatedAtDesc(JobStatus status);
}

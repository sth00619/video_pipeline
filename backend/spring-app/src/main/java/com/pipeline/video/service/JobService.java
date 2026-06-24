package com.pipeline.video.service;

import com.pipeline.video.domain.JobStatus;
import com.pipeline.video.domain.VideoJob;
import com.pipeline.video.dto.CreateJobRequest;
import com.pipeline.video.dto.JobResponse;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class JobService {

    private final VideoJobRepository jobRepository;

    @Transactional
    public JobResponse createJob(CreateJobRequest request, String username) {
        VideoJob job = VideoJob.builder()
                .title(request.getTitle())
                .keyword(request.getKeyword())
                .status(JobStatus.DRAFT)
                .autonomy(request.getAutonomy())
                .format(request.getFormat())
                .renderProfile(request.getRenderProfile())
                .makeShorts(request.isMakeShorts())
                .shortsCount(request.getShortsCount())
                .longformTargetMinutes(request.getLongformTargetMinutes())
                .budgetCap(request.getBudgetCap())
                .costAccumulated(BigDecimal.ZERO)
                .policyJson(request.getPolicyJson())
                .createdBy(username)
                .build();

        return JobResponse.from(jobRepository.save(job));
    }

    public List<JobResponse> getMyJobs(String username) {
        return jobRepository.findByCreatedByOrderByCreatedAtDesc(username)
                .stream().map(JobResponse::from).collect(Collectors.toList());
    }

    public JobResponse getJob(Long id) {
        return jobRepository.findById(id)
                .map(JobResponse::from)
                .orElseThrow(() -> new RuntimeException("Job not found: " + id));
    }

    public List<JobResponse> getAllJobs() {
        return jobRepository.findAll()
                .stream().map(JobResponse::from).collect(Collectors.toList());
    }
}

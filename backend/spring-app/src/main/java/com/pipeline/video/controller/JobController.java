package com.pipeline.video.controller;

import com.pipeline.video.dto.CreateJobRequest;
import com.pipeline.video.dto.JobResponse;
import com.pipeline.video.service.JobService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/jobs")
@RequiredArgsConstructor
public class JobController {

    private final JobService jobService;

    @PostMapping
    public ResponseEntity<JobResponse> createJob(
            @RequestBody CreateJobRequest request,
            @AuthenticationPrincipal String username) {
        return ResponseEntity.ok(jobService.createJob(request, username));
    }

    @GetMapping("/my")
    public ResponseEntity<List<JobResponse>> getMyJobs(
            @AuthenticationPrincipal String username) {
        return ResponseEntity.ok(jobService.getMyJobs(username));
    }

    @GetMapping("/{id}")
    public ResponseEntity<JobResponse> getJob(@PathVariable Long id) {
        return ResponseEntity.ok(jobService.getJob(id));
    }

    @GetMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<List<JobResponse>> getAllJobs() {
        return ResponseEntity.ok(jobService.getAllJobs());
    }
}

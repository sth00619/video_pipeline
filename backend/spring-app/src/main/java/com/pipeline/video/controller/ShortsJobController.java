package com.pipeline.video.controller;

import com.pipeline.video.domain.ShortsJob;
import com.pipeline.video.repository.ShortsJobRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.nio.file.Files;
import java.nio.file.Path;

/** Read API for durable Shorts projects, independent of their longform parent. */
@RestController
@RequestMapping("/api/shorts")
@RequiredArgsConstructor
public class ShortsJobController {

    private final ShortsJobRepository shortsJobRepository;

    @GetMapping
    public ResponseEntity<List<ShortsJob>> list(@AuthenticationPrincipal String username) {
        List<ShortsJob> projects = shortsJobRepository.findByCreatedByOrderByUpdatedAtDesc(username);
        projects.forEach(this::setDownloadReady);
        return ResponseEntity.ok(projects);
    }

    @GetMapping("/{shortsJobId}")
    public ResponseEntity<ShortsJob> get(@PathVariable Long shortsJobId,
                                          @AuthenticationPrincipal String username) {
        return shortsJobRepository.findById(shortsJobId)
                .filter(job -> username != null && username.equals(job.getCreatedBy()))
                .map(job -> {
                    setDownloadReady(job);
                    return ResponseEntity.ok(job);
                })
                .orElse(ResponseEntity.notFound().build());
    }

    private void setDownloadReady(ShortsJob job) {
        try {
            job.setDownloadReady(job.getOutputPath() != null
                    && Files.isRegularFile(Path.of(job.getOutputPath()))
                    && Files.size(Path.of(job.getOutputPath())) > 0);
        } catch (Exception ignored) {
            job.setDownloadReady(false);
        }
    }
}

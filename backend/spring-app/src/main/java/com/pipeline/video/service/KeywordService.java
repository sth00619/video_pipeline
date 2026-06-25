package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.KeywordSearchResponse;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.Map;

/**
 * Phase 3-1 — 키워드 탐색 서비스
 *
 *  - search(): seed 키워드로 후보 N개 조회 + KEYWORD_PENDING 전이
 *  - confirm(): 선택된 키워드 저장 + KEYWORD 게이트 통과 → SCRIPT_PENDING
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class KeywordService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public KeywordSearchResponse search(Long jobId, String seedKeyword, int limit, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.DRAFT && job.getStatus() != JobStatus.KEYWORD_PENDING) {
            throw new IllegalStateException("키워드 탐색은 DRAFT/KEYWORD_PENDING 에서만 가능. 현재: " + job.getStatus());
        }

        log.info("키워드 탐색 시작: jobId={}, seed={}, autonomy={}", jobId, seedKeyword, job.getAutonomy());

        // FastAPI 호출
        KeywordSearchResponse result = fastApiClient.searchKeywords(seedKeyword, limit, jobId);

        // 비용 기록 (Mock $0)
        costService.record(jobId, "KEYWORD_TOOL", BigDecimal.ZERO, "USD", "키워드 탐색");

        // Asset 저장 (후보 리스트 전체)
        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.KEYWORD)
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(asset);

        // 상태 전이
        job.setStatus(JobStatus.KEYWORD_PENDING);
        jobRepository.save(job);

        // AUTO 모드: 첫 번째 후보 자동 선택 + confirm
        if (autonomyService.isAuto(job) && result.getCandidates() != null
                && !result.getCandidates().isEmpty()) {
            String firstCandidate = result.getCandidates().get(0).getKeyword();
            log.info("AUTO 모드 — 첫 번째 후보 자동 선택: {}", firstCandidate);
            confirm(jobId, firstCandidate, "AUTO");
        }

        return result;
    }

    @Transactional
    public void confirm(Long jobId, String selectedKeyword, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.KEYWORD_PENDING) {
            throw new IllegalStateException("키워드 확정은 KEYWORD_PENDING 에서만 가능. 현재: " + job.getStatus());
        }
        if (selectedKeyword == null || selectedKeyword.isBlank()) {
            throw new IllegalStateException("선택된 키워드가 비어있습니다.");
        }

        // 선택 키워드 저장
        job.setKeyword(selectedKeyword);
        jobRepository.save(job);

        // 선택 결과 별도 Asset으로 기록
        Asset selectedAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.KEYWORD)
                .metaJson(safeJson(Map.of("selected", selectedKeyword, "final", true)))
                .build();
        assetRepository.save(selectedAsset);

        // 게이트 통과 → SCRIPT_PENDING
        gateService.approve(jobId, GateName.KEYWORD, username, "선택: " + selectedKeyword);
        log.info("키워드 확정 완료: jobId={}, keyword={}", jobId, selectedKeyword);
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}

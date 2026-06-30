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
 * Phase 3-1 — 키워드 탐색 (주식 콘텐츠 특화)
 *
 *  outperformer 표시 정책:
 *   - AUTO 모드: 1위 후보만 outperformer (자동 선택될 후보)
 *   - MANUAL/GUIDED: 상위 3위까지 outperformer (관리자 비교 편의)
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
    public KeywordSearchResponse search(Long jobId, String seedKeyword, int limit,
                                        Category category, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.DRAFT && job.getStatus() != JobStatus.KEYWORD_PENDING) {
            throw new IllegalStateException("키워드 탐색은 DRAFT/KEYWORD_PENDING 에서만 가능. 현재: " + job.getStatus());
        }

        // category 우선순위: 요청 > job 저장값 > CUSTOM
        Category effectiveCategory = category != null ? category
                : (job.getCategory() != null ? job.getCategory() : Category.CUSTOM);

        // outperformer 개수: AUTO=1, MANUAL/GUIDED=3
        int outperformerCount = autonomyService.isAuto(job) ? 1 : 3;

        log.info("키워드 탐색: jobId={}, category={}, seed={}, autonomy={}, outperformerCount={}",
                jobId, effectiveCategory, seedKeyword, job.getAutonomy(), outperformerCount);

        // FastAPI 호출
        KeywordSearchResponse result = fastApiClient.searchKeywords(
                seedKeyword, limit, effectiveCategory.name(), outperformerCount, jobId);

        // 비용 기록 (Mock $0)
        costService.record(jobId, "YOUTUBE_API", BigDecimal.ZERO, "USD", "키워드 트렌드 분석");

        // category를 Job에 저장
        job.setCategory(effectiveCategory);

        // Asset 저장
        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.KEYWORD)
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(asset);

        // 상태 전이
        job.setStatus(JobStatus.KEYWORD_PENDING);
        jobRepository.save(job);

        // AUTO 모드: 1위 후보 자동 confirm
        if (autonomyService.isAuto(job) && result.getCandidates() != null
                && !result.getCandidates().isEmpty()) {
            String topCandidate = result.getCandidates().get(0).getKeyword();
            log.info("AUTO 모드 — 1위 후보 자동 선택: {}", topCandidate);
            confirm(jobId, topCandidate, "AUTO");
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

        job.setKeyword(selectedKeyword);
        jobRepository.save(job);

        Asset selectedAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.KEYWORD)
                .metaJson(safeJson(Map.of("selected", selectedKeyword, "final", true)))
                .build();
        assetRepository.save(selectedAsset);

        gateService.approve(jobId, GateName.KEYWORD, username, "선택: " + selectedKeyword);
        log.info("키워드 확정: jobId={}, keyword={}", jobId, selectedKeyword);
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}

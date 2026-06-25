package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.ScriptGenerateResponse;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.Map;

/**
 * Phase 3-2 — 스크립트 생성 서비스
 *
 *  - generate(): 키워드 + 목표 분량으로 스크립트 + 시놉시스 생성
 *  - confirm(): 최종 스크립트(수정본 가능) 저장 + SCRIPT 게이트 통과 → TTS_PENDING
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class ScriptService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public ScriptGenerateResponse generate(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.SCRIPT_PENDING) {
            throw new IllegalStateException("스크립트 생성은 SCRIPT_PENDING 에서만 가능. 현재: " + job.getStatus());
        }
        if (job.getKeyword() == null || job.getKeyword().isBlank()) {
            throw new IllegalStateException("키워드가 선택되지 않음. 키워드 확정을 먼저 진행하세요.");
        }

        int targetMinutes = job.getLongformTargetMinutes() != null
                ? job.getLongformTargetMinutes() : 20;

        log.info("스크립트 생성 시작: jobId={}, keyword={}, target={}분, autonomy={}",
                jobId, job.getKeyword(), targetMinutes, job.getAutonomy());

        // FastAPI 호출
        ScriptGenerateResponse result = fastApiClient.generateScript(jobId, job.getKeyword(), targetMinutes);

        // 비용 기록
        costService.record(jobId, "CLAUDE_LLM", BigDecimal.ZERO, "USD", "스크립트 생성");

        // Asset 저장 (초안)
        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.SCRIPT)
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(asset);

        // AUTO 모드: 즉시 confirm (초안 그대로 사용)
        if (autonomyService.isAuto(job)) {
            log.info("AUTO 모드 — 스크립트 초안 자동 확정");
            confirm(jobId, result.getScript(), "AUTO");
        }

        return result;
    }

    @Transactional
    public void confirm(Long jobId, String finalScript, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.SCRIPT_PENDING) {
            throw new IllegalStateException("스크립트 확정은 SCRIPT_PENDING 에서만 가능. 현재: " + job.getStatus());
        }
        if (finalScript == null || finalScript.isBlank()) {
            throw new IllegalStateException("최종 스크립트가 비어있습니다.");
        }

        // 최종 스크립트 저장 (수정본 반영)
        Asset finalAsset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.SCRIPT)
                .metaJson(safeJson(Map.of(
                        "script", finalScript,
                        "final", true,
                        "char_count", finalScript.length()
                )))
                .build();
        assetRepository.save(finalAsset);

        // 게이트 통과 → TTS_PENDING
        gateService.approve(jobId, GateName.SCRIPT, username, "스크립트 확정");
        log.info("스크립트 확정 완료: jobId={}, length={}자", jobId, finalScript.length());
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}

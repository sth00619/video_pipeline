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
            throw new IllegalStateException("키워드가 선택되지 않음.");
        }

        int targetMinutes = job.getLongformTargetMinutes() != null
                ? job.getLongformTargetMinutes() : 20;
        String categoryName = job.getCategory() != null ? job.getCategory().name() : "CUSTOM";

        log.info("스크립트 생성: jobId={}, keyword={}, target={}분, category={}",
                jobId, job.getKeyword(), targetMinutes, categoryName);

        String marketSnapshotJson = null;
        try {
            // 해당 jobId의 KEYWORD 에셋 조회
            java.util.List<Asset> keywordAssets = assetRepository.findByJobIdAndAssetType(jobId, AssetType.KEYWORD);
            for (Asset a : keywordAssets) {
                if (a.getMetaJson() != null && a.getMetaJson().contains("market_snapshot")) {
                    Map<String, Object> metaMap = objectMapper.readValue(a.getMetaJson(), Map.class);
                    if (metaMap.containsKey("market_snapshot")) {
                        marketSnapshotJson = objectMapper.writeValueAsString(metaMap.get("market_snapshot"));
                        log.info("KEYWORD 에셋에서 market_snapshot 추출 성공");
                        break;
                    }
                }
            }
        } catch (Exception ex) {
            log.warn("KEYWORD 에셋에서 market_snapshot 추출 오류: {}", ex.getMessage());
        }

        ScriptGenerateResponse result = fastApiClient.generateScript(
                jobId, job.getKeyword(), targetMinutes, categoryName, marketSnapshotJson);

        costService.record(jobId, "CLAUDE_LLM", BigDecimal.ZERO, "USD",
                String.format("스크립트 %d분 %d자", targetMinutes,
                        result.getCharCount() != null ? result.getCharCount() : 0));

        Asset asset = Asset.builder()
                .jobId(jobId)
                .assetType(AssetType.SCRIPT)
                .metaJson(safeJson(result))
                .build();
        assetRepository.save(asset);

        if (autonomyService.isAuto(job)) {
            log.info("AUTO 모드 — 스크립트 자동 확정");
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

        gateService.approve(jobId, GateName.SCRIPT, username, "스크립트 확정");
        log.info("스크립트 확정: jobId={}, length={}자", jobId, finalScript.length());
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}

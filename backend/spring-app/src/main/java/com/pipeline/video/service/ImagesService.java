package com.pipeline.video.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pipeline.video.domain.*;
import com.pipeline.video.dto.GifClipDto;
import com.pipeline.video.dto.ImagesGenerateResponse;
import com.pipeline.video.dto.SceneImageDto;
import com.pipeline.video.repository.AssetRepository;
import com.pipeline.video.repository.VideoJobRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.Map;

/**
 * Phase 3-4 — 이미지 + GIF 생성 서비스
 *
 *  - generate(): TTS chunks 기반 씬 이미지 + 섹션 전환점 GIF 생성
 *  - confirm(): IMAGES 게이트 통과 → ASSEMBLING
 *
 *  산출물은 Phase 3-5 롱폼 조립에서 직접 참조됨.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class ImagesService {

    private final VideoJobRepository jobRepository;
    private final AssetRepository assetRepository;
    private final FastApiClient fastApiClient;
    private final GateService gateService;
    private final AutonomyService autonomyService;
    private final CostService costService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Transactional
    public ImagesGenerateResponse generate(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.IMAGES_PENDING) {
            throw new IllegalStateException("이미지 생성은 IMAGES_PENDING 에서만 가능. 현재: " + job.getStatus());
        }

        // TTS chunks 로드
        String ttsMetaJson = loadAssetMeta(jobId, AssetType.TTS_AUDIO);
        // 스크립트 로드
        String scriptMetaJson = loadAssetMeta(jobId, AssetType.SCRIPT);

        log.info("이미지 생성 시작: jobId={}, autonomy={}", jobId, job.getAutonomy());

        // FastAPI 호출
        ImagesGenerateResponse result = fastApiClient.generateImages(jobId, ttsMetaJson, scriptMetaJson);

        // 비용 기록 (Mock $0, 실제 Nano Banana Pro $0.03~0.05/장)
        BigDecimal imgCost = BigDecimal.ZERO;
        costService.record(jobId, "NANO_BANANA_PRO", imgCost, "USD",
                String.format("씬 이미지 %d장 + GIF %d개",
                        result.getSceneCount(), result.getGifCount()));

        // Asset 저장 — 씬 이미지
        if (result.getScenes() != null) {
            for (SceneImageDto scene : result.getScenes()) {
                Asset asset = Asset.builder()
                        .jobId(jobId)
                        .assetType(AssetType.SCENE_IMAGE)
                        .localPath(scene.getImagePath())
                        .metaJson(safeJson(scene))
                        .build();
                assetRepository.save(asset);
            }
        }

        // Asset 저장 — GIF 클립
        if (result.getGifs() != null) {
            for (GifClipDto gif : result.getGifs()) {
                Asset asset = Asset.builder()
                        .jobId(jobId)
                        .assetType(AssetType.GIF_CLIP)
                        .localPath(gif.getGifPath())
                        .metaJson(safeJson(gif))
                        .build();
                assetRepository.save(asset);
            }
        }

        // AUTO 모드: 자동 confirm → ASSEMBLING
        if (autonomyService.isAuto(job)) {
            log.info("AUTO 모드 — 이미지 자동 확정");
            confirm(jobId, "AUTO");
        }

        return result;
    }

    @Transactional
    public void confirm(Long jobId, String username) {
        VideoJob job = jobRepository.findById(jobId)
                .orElseThrow(() -> new RuntimeException("Job not found: " + jobId));

        if (job.getStatus() != JobStatus.IMAGES_PENDING) {
            throw new IllegalStateException("이미지 확정은 IMAGES_PENDING 에서만 가능. 현재: " + job.getStatus());
        }

        gateService.approve(jobId, GateName.IMAGES, username, "이미지/GIF 확정");
        log.info("이미지 확정 완료: jobId={}", jobId);
    }

    // ============================
    // helpers
    // ============================
    private String loadAssetMeta(Long jobId, AssetType type) {
        return assetRepository
                .findTopByJobIdAndAssetTypeOrderByCreatedAtDesc(jobId, type)
                .map(Asset::getMetaJson)
                .orElseThrow(() -> new RuntimeException(type + " Asset이 없습니다: " + jobId));
    }

    private String safeJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}
